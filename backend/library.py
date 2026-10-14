"""Durable user-owned audio. Session cleanup never touches workspace files."""
import hashlib
import re
import shutil
from uuid import uuid4
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from .auth import database


def voice_directory(data, user_id, voice_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', user_id) or not re.fullmatch(r'[a-f0-9]{32}', voice_id):
        raise HTTPException(404, '저장한 음성을 찾을 수 없습니다.')
    return data / 'workspace' / user_id / voice_id


def public_voice(row):
    result = dict(row)
    result.pop('user_id', None)
    result.pop('audio_sha256', None)
    result['audio_url'] = f'/wiavoice/api/my-voices/{row["voice_id"]}/audio'
    return result


def save_voice(data, user_id, job, name, audio):
    directory = None
    try:
        with database() as db:
            # A retry or double click saves only one copy of a generated result.
            db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))',
                       ('wiavoice:' + user_id + ':' + job['id'],))
            existing = db.execute('SELECT * FROM wiavoice.voices WHERE user_id=%s AND source_job_id=%s',
                                  (user_id, job['id'])).fetchone()
            if existing:
                return public_voice(existing)
            voice_id = uuid4().hex
            target = voice_directory(data, user_id, voice_id)
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            target.mkdir(mode=0o700)
            directory = target
            temporary = target / 'audio.tmp'
            temporary.write_bytes(audio)
            temporary.replace(target / 'audio.wav')
            spec = job['request']
            options = {key: spec[key] for key in ['language', 'reference_language', 'higgs_options'] if key in spec}
            row = db.execute('''INSERT INTO wiavoice.voices
                (voice_id,user_id,source_job_id,name,model,speaker,emotion,text,instructions,
                 generation_options,duration_seconds,sample_rate,file_size,audio_sha256)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *''',
                (voice_id,user_id,job['id'],name,spec['model'],spec['voice'],spec['emotion'],spec['text'],
                 spec.get('instructions',''),Jsonb(options),job['seconds'],job['sample_rate'],len(audio),
                 hashlib.sha256(audio).hexdigest())).fetchone()
        return public_voice(row)
    except BaseException:
        if directory is not None:
            shutil.rmtree(directory, ignore_errors=True)
        raise


def list_voices(user_id, search, offset, limit):
    where = "user_id=%s AND (%s='' OR strpos(lower(name),lower(%s))>0 OR strpos(lower(text),lower(%s))>0)"
    params = (user_id, search, search, search)
    with database() as db:
        total = db.execute('SELECT count(*) AS total FROM wiavoice.voices WHERE '+where, params).fetchone()['total']
        rows = db.execute('SELECT * FROM wiavoice.voices WHERE '+where+' ORDER BY created_at DESC, voice_id LIMIT %s OFFSET %s',
                          (*params, limit, offset)).fetchall()
    return {'items': [public_voice(row) for row in rows], 'total': total}


def get_voice(user_id, voice_id):
    with database() as db:
        row = db.execute('SELECT * FROM wiavoice.voices WHERE user_id=%s AND voice_id=%s', (user_id, voice_id)).fetchone()
    if not row:
        raise HTTPException(404, '저장한 음성을 찾을 수 없습니다.')
    return row


def delete_voice(data, user_id, voice_id):
    """Rename first so a failed DB transaction can restore the original audio."""
    target = voice_directory(data, user_id, voice_id)
    parked = None
    try:
        with database() as db:
            # Same lock as merge submission: a queued source cannot disappear.
            db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('merge:'+user_id,))
            row = db.execute('SELECT voice_id FROM wiavoice.voices WHERE user_id=%s AND voice_id=%s FOR UPDATE',
                             (user_id, voice_id)).fetchone()
            if not row: raise HTTPException(404, '저장한 음성을 찾을 수 없습니다.')
            active = db.execute("""SELECT 1 FROM wiavoice.merge_action WHERE user_id=%s
                AND status IN ('queued','running') AND input_voices @> %s LIMIT 1""",
                (user_id, Jsonb([{'voice_id':voice_id}]))).fetchone()
            if active: raise HTTPException(409, '병합 중인 음성입니다. 병합이 완료된 뒤 삭제해 주세요.')
            db.execute('UPDATE wiavoice.merge_action SET result_voice_id=NULL,updated_at=now() WHERE user_id=%s AND result_voice_id=%s', (user_id,voice_id))
            db.execute('DELETE FROM wiavoice.voices WHERE user_id=%s AND voice_id=%s', (user_id,voice_id))
            if target.exists():
                parked = target.with_name('.deleting-'+voice_id+'-'+uuid4().hex)
                target.rename(parked)
    except BaseException:
        if parked is not None and parked.exists(): parked.rename(target)
        raise
    if parked is not None:
        try: shutil.rmtree(parked)
        except OSError:
            # The periodic recovery loop retries physical cleanup after commit.
            import logging
            logging.getLogger('wiavoice').exception('Will retry deleted voice file cleanup')
    return {'ok':True, 'voice_id':voice_id}


def recover_deletions(data):
    """Finish committed deletions or restore a rename interrupted before commit."""
    for parked in (data/'workspace').glob('*/.deleting-*'):
        match = re.fullmatch(r'\.deleting-([a-f0-9]{32})-[a-f0-9]{32}',parked.name)
        if not match or not parked.is_dir() or parked.is_symlink(): continue
        user_id,voice_id = parked.parent.name,match[1]
        target = voice_directory(data,user_id,voice_id)
        with database() as db:
            db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',('merge:'+user_id,))
            if not parked.exists(): continue
            exists = db.execute('SELECT 1 FROM wiavoice.voices WHERE user_id=%s AND voice_id=%s',(user_id,voice_id)).fetchone()
            if exists:
                if not target.exists(): parked.rename(target)
            else: shutil.rmtree(parked)
