"""CPU-only durable merge queue, independent of TTS models and login sessions."""
import asyncio
import hashlib
import json
import logging
import shutil
from uuid import uuid4
import numpy as np
import soundfile as sf
import soxr
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from psycopg.types.json import Jsonb
from starlette.concurrency import run_in_threadpool
from .auth import database
from .library import voice_directory

RATE = 48000
MAX_SECONDS = 1800
logger = logging.getLogger('wiavoice.merge')

class MergeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1,max_length=100)
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    voice_ids: list[str] = Field(min_length=2,max_length=20)
    gaps_seconds: list[float] = Field(min_length=1,max_length=19)

    @model_validator(mode='after')
    def validate_sequence(self):
        import re, math
        if any(not re.fullmatch(r'[a-f0-9]{32}', key) for key in self.voice_ids):
            raise ValueError('음성 선택을 확인해 주세요.')
        if len(self.gaps_seconds)!=len(self.voice_ids)-1 or any(not math.isfinite(g) or not 0<=g<=30 for g in self.gaps_seconds):
            raise ValueError('각 음성 사이에 0~30초의 공백을 지정해 주세요.')
        return self


def public_action(row):
    return {k:v for k,v in row.items() if k not in {'user_id','request_hash','request_id'}}


def submit(data,user_id,spec):
    signature=hashlib.sha256(json.dumps(spec.model_dump(exclude={'request_id'}),sort_keys=True).encode()).hexdigest()
    with database() as db:
        db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',('merge:'+user_id,))
        existing=db.execute('SELECT * FROM wiavoice.merge_action WHERE user_id=%s AND request_id=%s',(user_id,spec.request_id)).fetchone()
        if existing:
            if existing['request_hash']!=signature: raise HTTPException(409,'변경된 설정으로 다시 병합해 주세요.')
            return public_action(existing)
        rows=db.execute('SELECT * FROM wiavoice.voices WHERE user_id=%s AND voice_id=ANY(%s)',(user_id,spec.voice_ids)).fetchall()
        sources={row['voice_id']:row for row in rows}
        if any(key not in sources for key in spec.voice_ids):raise HTTPException(404,'선택한 음성을 찾을 수 없습니다.')
        inputs=[];duration=sum(spec.gaps_seconds)
        for key in spec.voice_ids:
            row=sources[key]
            path=voice_directory(data,user_id,key)/'audio.wav'
            if not path.is_file():raise HTTPException(404,'선택한 음성 파일을 찾을 수 없습니다.')
            try:info=sf.info(path)
            except (RuntimeError,OSError):raise HTTPException(400,'읽을 수 없는 음성 파일이 포함되어 있습니다.') from None
            if info.frames<=0 or info.channels>2:raise HTTPException(400,'지원하지 않는 음성 파일입니다.')
            duration+=info.duration
            snapshot={k:row[k] for k in ['voice_id','name','model','speaker','emotion','text','instructions','generation_options']}
            if row['model']=='merged':
                snapshot['generation_options']={'merge_action_id':row['generation_options'].get('merge_action_id')}
            inputs.append(snapshot)
        if duration>MAX_SECONDS:raise HTTPException(400,'병합 음성은 공백을 포함해 최대 30분까지 만들 수 있습니다.')
        count=db.execute("SELECT count(*) AS n FROM wiavoice.merge_action WHERE user_id=%s AND status IN ('queued','running')",(user_id,)).fetchone()['n']
        if count>=3:raise HTTPException(429,'진행 중인 병합이 많습니다. 완료 후 다시 시도해 주세요.')
        row=db.execute('''INSERT INTO wiavoice.merge_action(action_id,user_id,request_id,request_hash,name,input_voices,gaps_seconds)
            VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *''',
            (uuid4().hex,user_id,spec.request_id,signature,spec.name,Jsonb(inputs),Jsonb(spec.gaps_seconds))).fetchone()
    return public_action(row)


def list_actions(user_id):
    with database() as db:
        rows=db.execute('SELECT * FROM wiavoice.merge_action WHERE user_id=%s ORDER BY created_at DESC LIMIT 10',(user_id,)).fetchall()
    return [public_action(row) for row in rows]


def claim():
    with database() as db:
        row=db.execute("""SELECT a.* FROM wiavoice.merge_action a JOIN platform.users u USING(user_id)
            WHERE a.status='queued' AND u.is_active=TRUE ORDER BY a.created_at
            LIMIT 1 FOR UPDATE OF a SKIP LOCKED""").fetchone()
        if row:
            db.execute("UPDATE wiavoice.merge_action SET status='running',started_at=now(),updated_at=now() WHERE action_id=%s",(row['action_id'],))
    return row


def recover(data,user_id=None):
    with database() as db:
        rows=db.execute("""UPDATE wiavoice.merge_action SET status='failed',error_message='서비스가 재시작되었습니다. 다시 병합해 주세요.',
            completed_at=now(),updated_at=now() WHERE status='running'""" + (' AND user_id=%s' if user_id else '') + ' RETURNING action_id,user_id', (user_id,) if user_id else ()).fetchall()
    for row in rows:shutil.rmtree(voice_directory(data,row['user_id'],row['action_id']),ignore_errors=True)


def perform(data,action):
    key=action['action_id'];user_id=action['user_id'];directory=voice_directory(data,user_id,key)
    directory.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    directory.mkdir(mode=0o700)
    try:
        frames=0
        with sf.SoundFile(directory/'audio.tmp',mode='w',samplerate=RATE,channels=1,format='WAV',subtype='PCM_16') as output:
            def write(audio):
                nonlocal frames
                frames+=len(audio)
                if frames>RATE*MAX_SECONDS:raise ValueError('병합 음성은 최대 30분까지 만들 수 있습니다.')
                if not np.isfinite(audio).all():raise ValueError('정상적이지 않은 음성 파일이 포함되어 있습니다.')
                output.write(audio)
            for index,item in enumerate(action['input_voices']):
                with sf.SoundFile(voice_directory(data,user_id,item['voice_id'])/'audio.wav') as source:
                    resampler=soxr.ResampleStream(source.samplerate,RATE,1,dtype='float32',quality='HQ') if source.samplerate!=RATE else None
                    while source.tell()<len(source):
                        block=source.read(source.samplerate,dtype='float32',always_2d=True).mean(axis=1)
                        if resampler:block=resampler.resample_chunk(block,last=source.tell()==len(source))
                        write(block)
                if index<len(action['gaps_seconds']):write(np.zeros(round(action['gaps_seconds'][index]*RATE),dtype='float32'))
                with database() as db:db.execute('UPDATE wiavoice.merge_action SET progress=%s,updated_at=now() WHERE action_id=%s',
                                                (round((index+1)/len(action['input_voices'])*95),key))
        (directory/'audio.tmp').replace(directory/'audio.wav')
        path=directory/'audio.wav';digest=hashlib.sha256()
        with path.open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):digest.update(block)
        inputs=action['input_voices']
        def common(field):return inputs[0][field] if len({v[field] for v in inputs})==1 else 'mixed'
        text='\n\n'.join(v['text'] for v in inputs)
        instructions='\n\n'.join(v['instructions'] for v in inputs if v['instructions'])
        options={'merge_action_id':key,'input_voices':inputs,'gaps_seconds':action['gaps_seconds'],'format':'PCM_16','channels':1}
        with database() as db:
            db.execute('''INSERT INTO wiavoice.voices(voice_id,user_id,source_job_id,name,model,speaker,emotion,text,instructions,
                generation_options,duration_seconds,sample_rate,file_size,audio_sha256)
                VALUES(%s,%s,NULL,%s,'merged',%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (key,user_id,action['name'],common('speaker'),common('emotion'),text,instructions,Jsonb(options),frames/RATE,RATE,path.stat().st_size,digest.hexdigest()))
            db.execute("""UPDATE wiavoice.merge_action SET status='completed',progress=100,result_voice_id=%s,
                completed_at=now(),updated_at=now() WHERE action_id=%s""",(key,key))
    except Exception:
        shutil.rmtree(directory,ignore_errors=True)
        raise


def process(data,action):
    try:perform(data,action)
    except Exception as exc:
        logger.exception('Merge failed: %s',action['action_id'])
        message=str(exc) if isinstance(exc,ValueError) else '음성을 병합하지 못했습니다. 원본 음성을 확인한 뒤 다시 시도해 주세요.'
        with database() as db:
            db.execute("UPDATE wiavoice.merge_action SET status='failed',error_message=%s,completed_at=now(),updated_at=now() WHERE action_id=%s",(message,action['action_id']))


async def worker(data,stop):
    needs_recovery=True
    while not stop.is_set():
        try:
            if needs_recovery:
                await run_in_threadpool(recover,data);needs_recovery=False
            action=await run_in_threadpool(claim)
            if action:
                await run_in_threadpool(process,data,action)
                continue
        except Exception:
            logger.exception('Merge queue unavailable; retrying')
            needs_recovery=True
        try:await asyncio.wait_for(stop.wait(),2)
        except TimeoutError:pass
