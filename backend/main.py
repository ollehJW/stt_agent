import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
import io
import json
import logging
import os
from pathlib import Path
import re
import shutil
import time
from typing import Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile, Query
from fastapi.responses import FileResponse
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator
import soundfile as sf
from starlette.concurrency import run_in_threadpool

from . import library, merger, marketplace, telemetry
from .admin import router as admin_router
from .auth import authorize, revoke_session, COOKIE, token_hash, active_session_keys
from .catalog import MODELS, VOICES, QWEN_PROMPTS, REFERENCE_TEXTS
from .engine import Engine
from .audio_processing import trim_trailing_silence
from .previews import PREVIEW_TEXT, combinations, preview_key

DATA = Path(os.getenv('WIAVOICE_DATA', '/data/wiavoice'))
MAX_UPLOAD = 20 * 1024 * 1024
EXTENSIONS = {'.wav', '.mp3', '.flac', '.ogg'}
VOICE_IDS = {v['id'] for v in VOICES}
logger = logging.getLogger('wiavoice')


class HiggsOptions(BaseModel):
    model_config = ConfigDict(extra='forbid')
    speed: Literal['default', 'very_slow', 'slow', 'fast', 'very_fast'] = 'default'
    pitch: Literal['default', 'low', 'high'] = 'default'
    expression: Literal['default', 'low', 'high'] = 'default'
    style: Literal['default', 'whispering', 'shouting', 'singing'] = 'default'


class Generation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=500)
    model: Literal['qwen', 'fish', 'higgs']
    language: Literal['auto', 'ko', 'en'] = 'auto'
    reference_language: Literal['ko', 'en'] = 'ko'
    voice: str = 'Sohee'
    emotion: str = 'neutral'
    instructions: str = Field(default='', max_length=1000)
    upload_id: str | None = None
    higgs_options: HiggsOptions | None = None
    # Accept legacy browser requests, but never use or persist their transcript.
    reference_text: str = Field(default='', max_length=2000, exclude=True)

    @model_validator(mode='before')
    @classmethod
    def removed_effects(cls, values):
        if isinstance(values, dict) and 'higgs_effects' in values:
            values = dict(values)
            if values.pop('higgs_effects') != []:
                raise ValueError('쉼·소리 연출 기능이 제거되었습니다. 새로고침한 뒤 다시 생성해 주세요.')
        return values

    @model_validator(mode='before')
    @classmethod
    def legacy_languages(cls, values):
        # Preserve old browser requests and persisted jobs.
        if isinstance(values, dict) and 'languages' in values:
            values = dict(values)
            languages = values.pop('languages')
            if not isinstance(languages, list) or not 1 <= len(languages) <= 2:
                raise ValueError('언어 선택을 확인해 주세요.')
            if any(x not in ['ko', 'en'] for x in languages) or len(set(languages)) != len(languages):
                raise ValueError('언어 선택을 확인해 주세요.')
            values.setdefault('language', languages[0] if len(languages) == 1 else 'auto')
            values.setdefault('reference_language', 'en' if languages == ['en'] else 'ko')
        return values

    @model_validator(mode='after')
    def validate_options(self):
        self.language = 'auto'
        self.text = self.text.strip()
        self.instructions = self.instructions.strip()
        if not self.text: raise ValueError('읽을 문장을 입력해 주세요.')
        if self.voice not in VOICE_IDS | {'custom'}: raise ValueError('지원하지 않는 목소리입니다.')
        if self.emotion not in {e['id'] for e in MODELS[self.model]['emotions']}:
            raise ValueError('해당 모델에서 지원하지 않는 감정입니다.')
        if self.model != 'higgs' and self.higgs_options is not None:
            raise ValueError('이 추가 설정은 Higgs에서만 지원합니다.')
        if self.model == 'higgs' and self.instructions:
            raise ValueError('Higgs는 자유 형식 추가 지시를 지원하지 않습니다.')
        if self.voice == 'custom':
            if self.model == 'qwen': raise ValueError('현재 Qwen CustomVoice는 샘플 업로드를 지원하지 않습니다.')
            if not self.upload_id or not re.fullmatch(r'[a-f0-9]{32}', self.upload_id):
                raise ValueError('참조 음성을 먼저 첨부해 주세요.')
        return self


def make_payload(spec: Generation):
    payload = {'input': spec.text, 'response_format': 'wav', 'stream': False, 'max_new_tokens': 4096}
    if spec.model == 'qwen':
        language = 'Auto'
        payload.update(voice=spec.voice, language=language,
                       instructions=' '.join(filter(None, [QWEN_PROMPTS[spec.emotion], spec.instructions])))
    else:
        lang = spec.reference_language
        if spec.voice == 'custom':
            path, transcript = DATA / 'uploads' / f'{spec.upload_id}.wav', ''
        else:
            path, transcript = DATA / 'voices' / f'{spec.voice}_{lang}.wav', REFERENCE_TEXTS[lang]
        if not path.is_file(): raise ValueError('참조 음성을 찾을 수 없습니다. 다시 첨부하거나 다른 목소리를 선택해 주세요.')
        payload.update(references=[{'audio_path': str(path), 'text': transcript}], temperature=0.7)
        prefix = ''
        if spec.emotion != 'neutral':
            prefix = f'[{spec.emotion}]' if spec.model == 'fish' else f'<|emotion:{spec.emotion}|>'
        if spec.model == 'fish' and spec.instructions:
            instruction = re.sub(r'[\[\]\r\n]', ' ', spec.instructions).strip()
            prefix += f'[{instruction}]'
        if spec.model == 'higgs' and spec.higgs_options:
            options = spec.higgs_options
            for field, tag in [('speed', 'speed'), ('pitch', 'pitch'), ('expression', 'expressive')]:
                value = getattr(options, field)
                if value != 'default': prefix += f'<|prosody:{tag}_{value}|>'
            if options.style != 'default': prefix += f'<|style:{options.style}|>'
        if spec.model == 'higgs' and prefix:
            # Higgs control tags are sentence-level; repeat after sentence/newline boundaries.
            parts = re.split(r'((?<=[.!?。！？])\s+|\n+)', spec.text)
            payload['input'] = ''.join((prefix + part) if part.strip() else part for part in parts)
        else:
            payload['input'] = prefix + spec.text
    return payload


def session_directory(key):
    if not re.fullmatch(r'[a-f0-9]{64}', key):
        raise ValueError('Invalid session storage key')
    return DATA / 'sessions' / key


def job_path(job, folder, suffix):
    return session_directory(job['session_key']) / folder / f'{job["id"]}.{suffix}'


def save_job(job):
    # Cleanup must never be undone by a queued or in-flight generation.
    if job.get('_discarded'):
        return
    path = job_path(job, 'jobs', 'json')
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(job, ensure_ascii=False, indent=2))
    temp.replace(path)
    telemetry.record(DATA, job)


def remove_session(key):
    path = session_directory(key)
    for job_id, job in list(app.state.jobs.items()):
        if job.get('session_key') == key:
            if job['status'] not in ['completed','failed']:
                job.update(status='cancelled',message='로그인 세션이 종료되었습니다.',completed_at=datetime.now(timezone.utc).isoformat())
                telemetry.record(DATA,job)
            job['_discarded'] = True
            del app.state.jobs[job_id]
    if path.exists():
        shutil.rmtree(path)


async def cleanup_sessions():
    keys = {p.name for p in (DATA / 'sessions').iterdir()
            if p.is_dir() and not p.is_symlink() and re.fullmatch(r'[a-f0-9]{64}', p.name)}
    active = await run_in_threadpool(active_session_keys, keys)
    for key in keys - active:
        remove_session(key)


async def session_reaper():
    while True:
        try:
            await cleanup_sessions()
            await run_in_threadpool(library.recover_deletions, DATA)
            await run_in_threadpool(marketplace.cleanup, DATA)
        except Exception:
            # Keep files when the database is unavailable; retry without killing cleanup.
            logger.exception('Session cleanup failed; will retry in 30 seconds')
        await asyncio.sleep(30)


async def worker(app):
    while True:
        try:
            job_id = await asyncio.wait_for(app.state.queue.get(), 30)
        except TimeoutError:
            if app.state.engine.model and time.monotonic() - app.state.engine.last_used > 600:
                await app.state.engine.stop()
            continue
        job = app.state.jobs.get(job_id)
        if job is None:
            app.state.queue.task_done()
            continue
        try:
            spec = Generation(**job['request'])
            payload = make_payload(spec)
            job.update(status='loading', started_at=datetime.now(timezone.utc).isoformat(), message='모델을 준비하고 있습니다. 모델 전환 시 1~3분 정도 걸릴 수 있습니다.')
            save_job(job)
            await app.state.engine.ensure(spec.model)
            if job.get('_discarded'): continue
            job.update(status='generating', message='목소리를 생성하고 있습니다.')
            save_job(job)
            started = time.monotonic()
            audio = await app.state.engine.generate(payload)
            if job.get('_discarded'): continue
            if spec.model == 'higgs':
                audio, trimmed = await run_in_threadpool(trim_trailing_silence, audio)
                if job.get('_discarded'): continue
                if trimmed:
                    job['trimmed_trailing_seconds'] = trimmed
                    logger.info('Removed %.3fs trailing silence from Higgs job %s', trimmed, job_id)
            info = sf.info(io.BytesIO(audio))
            if info.frames == 0: raise ValueError('생성된 음성이 비어 있습니다.')
            path = job_path(job, 'outputs', 'wav')
            path.write_bytes(audio)
            job.update(status='completed', completed_at=datetime.now(timezone.utc).isoformat(), message='음성 생성이 완료되었습니다.', seconds=round(info.duration, 2),
                       sample_rate=info.samplerate, generation_seconds=round(time.monotonic()-started, 2),
                       audio_url=f'/wiavoice/api/jobs/{job_id}/audio')
        except asyncio.CancelledError:
            job.update(status='failed', completed_at=datetime.now(timezone.utc).isoformat(), message='서비스가 재시작되었습니다. 다시 생성해 주세요.')
            save_job(job)
            raise
        except Exception as exc:
            logger.exception('Generation failed: %s', job_id)
            message = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else '음성 생성 중 오류가 발생했습니다. 다시 시도해 주세요.'
            job.update(status='failed', completed_at=datetime.now(timezone.utc).isoformat(), message=message)
            await app.state.engine.stop()
        finally:
            save_job(job)
            app.state.queue.task_done()


@asynccontextmanager
async def lifespan(app):
    app.state.data = DATA
    for folder in ['voices', 'uploads', 'sessions', 'logs', 'previews', 'workspace']:
        (DATA / folder).mkdir(mode=0o700, parents=True, exist_ok=True)
    app.state.jobs = {}
    for file in (DATA / 'sessions').glob('*/jobs/*.json'):
        try:
            job = json.loads(file.read_text())
            if (not re.fullmatch(r'[a-f0-9]{32}', job['id'])
                    or file != job_path(job, 'jobs', 'json')):
                raise ValueError('Invalid job storage path')
            if job['status'] not in ['completed', 'failed']:
                job.update(status='failed', completed_at=datetime.now(timezone.utc).isoformat(), message='서비스가 재시작되었습니다. 다시 생성해 주세요.')
                save_job(job)
            app.state.jobs[job['id']] = job
            telemetry.record(DATA,job)
        except (ValueError, KeyError):
            logger.warning('Skipping invalid job metadata: %s', file.name)
    app.state.queue = asyncio.Queue(maxsize=10)
    app.state.engine = Engine(DATA)
    telemetry_stop = asyncio.Event()
    telemetry_task = asyncio.create_task(telemetry.worker(DATA,telemetry_stop))
    task = asyncio.create_task(worker(app))
    reaper = asyncio.create_task(session_reaper())
    merge_stop = asyncio.Event()
    merge_task = asyncio.create_task(merger.worker(DATA, merge_stop))
    yield
    merge_stop.set()
    await merge_task
    reaper.cancel()
    with suppress(asyncio.CancelledError): await reaper
    task.cancel()
    with suppress(asyncio.CancelledError): await task
    await app.state.engine.stop()
    telemetry_stop.set()
    await telemetry_task


app = FastAPI(title='WiaVoice', version='1.0.0', lifespan=lifespan, dependencies=[Depends(authorize)], docs_url=None, redoc_url=None, openapi_url=None)


app.include_router(admin_router)


@app.middleware('http')
async def private_responses(request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'private, no-store'
    return response


@app.get('/api/auth/me')
def me(request: Request):
    return {**request.state.user, 'session_id': request.state.session_key}


@app.post('/api/auth/logout')
async def logout(request: Request, response: Response):
    await run_in_threadpool(revoke_session, request)
    remove_session(token_hash(request.cookies.get(COOKIE, '')))
    response.delete_cookie(COOKIE, path='/', httponly=True, secure=True, samesite='strict')
    return {'ok': True}


@app.get('/api/health')
def health():
    return {'status': 'ok', 'service': 'WiaVoice', 'engine': app.state.engine.state,
            'active_model': app.state.engine.model, 'queued': app.state.queue.qsize()}


@app.get('/api/catalog')
def catalog():
    voices = [{**v, 'samples': {lang: f'/wiavoice/api/voices/{v["id"]}/{lang}'
                for lang in ['ko', 'en'] if (DATA / 'voices' / f'{v["id"]}_{lang}.wav').exists()}} for v in VOICES]
    previews = {}
    for model, voice, emotion in combinations():
        key = preview_key(model, voice, emotion)
        if (DATA / 'previews' / f'{key}.wav').is_file():
            previews.setdefault(model, {}).setdefault(voice, {})[emotion] = f'/wiavoice/api/previews/{key}'
    return {'models': MODELS, 'voices': voices, 'previews': previews, 'preview_text': PREVIEW_TEXT, 'upload_formats': ['WAV', 'MP3', 'FLAC', 'OGG'],
            'max_upload_mb': 20, 'reference_seconds': [3, 30], 'max_text_length': 500}


@app.get('/api/previews/{key}')
def combination_preview(key: str):
    if not re.fullmatch(r'[a-f0-9]{24}', key): raise HTTPException(404)
    path = DATA / 'previews' / f'{key}.wav'
    if not path.is_file(): raise HTTPException(404, '미리듣기를 준비 중입니다.')
    return FileResponse(path, media_type='audio/wav', headers={'Cache-Control': 'public, max-age=86400'})


@app.get('/api/voices/{voice}/{language}')
def voice_sample(voice: str, language: str):
    if voice not in VOICE_IDS or language not in ['ko', 'en']: raise HTTPException(404, '목소리를 찾을 수 없습니다.')
    path = DATA / 'voices' / f'{voice}_{language}.wav'
    if not path.exists(): raise HTTPException(404, '미리듣기를 준비 중입니다.')
    return FileResponse(path, media_type='audio/wav', headers={'Cache-Control': 'public, max-age=3600'})


def normalize_audio(raw):
    try:
        with sf.SoundFile(io.BytesIO(raw)) as f:
            duration = f.frames / f.samplerate
            if not 3 <= duration <= 30: raise ValueError('참조 음성은 3~30초 길이로 첨부해 주세요.')
            if f.channels > 2 or not 8000 <= f.samplerate <= 192000:
                raise ValueError('8~192 kHz의 모노 또는 스테레오 음성을 첨부해 주세요.')
            audio = f.read(dtype='float32', always_2d=True).mean(axis=1)
            if not np.isfinite(audio).all() or float(np.max(np.abs(audio))) < 0.0001:
                raise ValueError('소리가 있는 정상적인 음성 파일을 첨부해 주세요.')
            result = io.BytesIO()
            sf.write(result, np.clip(audio, -1, 1), f.samplerate, format='WAV', subtype='PCM_16')
            return result.getvalue(), round(duration, 2)
    except (sf.LibsndfileError, RuntimeError):
        raise ValueError('파일을 읽을 수 없습니다. WAV, MP3, FLAC, OGG 음성 파일인지 확인해 주세요.')


@app.post('/api/uploads', status_code=201)
async def upload(request: Request, file: UploadFile):
    try:
        if Path(file.filename or '').suffix.lower() not in EXTENSIONS:
            raise HTTPException(400, '지원 형식은 WAV, MP3, FLAC, OGG입니다.')
        raw = await file.read(MAX_UPLOAD + 1)
        if len(raw) > MAX_UPLOAD: raise HTTPException(413, '파일은 최대 20MB까지 첨부할 수 있습니다.')
        try:
            audio, duration = await run_in_threadpool(normalize_audio, raw)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        key = uuid4().hex
        (DATA / 'uploads' / f'{key}.wav').write_bytes(audio)
        (DATA / 'uploads' / f'{key}.json').write_text(json.dumps({'owner_id': request.state.user['user_id']}))
        return {'id': key, 'seconds': duration, 'filename': Path(file.filename).name,
                'audio_url': f'/wiavoice/api/uploads/{key}/audio'}
    finally:
        await file.close()


def require_upload_owner(key, user_id):
    if not re.fullmatch(r'[a-f0-9]{32}', key): raise HTTPException(404)
    try:
        owner = json.loads((DATA / 'uploads' / f'{key}.json').read_text()).get('owner_id')
    except (OSError, ValueError):
        owner = None
    if owner != user_id: raise HTTPException(404, '참조 음성을 찾을 수 없습니다.')


@app.get('/api/uploads/{key}/audio')
def uploaded_audio(key: str, request: Request):
    require_upload_owner(key, request.state.user['user_id'])
    if not re.fullmatch(r'[a-f0-9]{32}', key): raise HTTPException(404)
    path = DATA / 'uploads' / f'{key}.wav'
    if not path.exists(): raise HTTPException(404, '참조 음성을 찾을 수 없습니다.')
    return FileResponse(path, media_type='audio/wav')


@app.post('/api/jobs', status_code=202)
async def create_job(spec: Generation, request: Request):
    if spec.voice == 'custom': require_upload_owner(spec.upload_id, request.state.user['user_id'])
    if app.state.queue.full(): raise HTTPException(429, '생성 요청이 많습니다. 잠시 후 다시 시도해 주세요.')
    try: make_payload(spec)
    except ValueError as exc: raise HTTPException(400, str(exc))
    session_key = request.state.session_key
    session_directory(session_key).mkdir(mode=0o700, parents=True, exist_ok=True)
    for folder in ['jobs', 'outputs']:
        (session_directory(session_key) / folder).mkdir(mode=0o700, parents=True, exist_ok=True)
    job = {'session_key': session_key, 'owner_id': request.state.user['user_id'], 'id': uuid4().hex, 'status': 'queued', 'message': '생성 순서를 기다리고 있습니다.',
           'created_at': datetime.now(timezone.utc).isoformat(), 'request': spec.model_dump()}
    app.state.jobs[job['id']] = job
    save_job(job)
    app.state.queue.put_nowait(job['id'])
    return job


@app.get('/api/jobs')
async def recent_jobs(request: Request):
    jobs = [job for job in app.state.jobs.values() if job.get('owner_id') == request.state.user['user_id']
            and job.get('session_key') == request.state.session_key]
    return sorted(jobs, key=lambda job: job['created_at'], reverse=True)[:20]


@app.get('/api/jobs/{key}')
def get_job(key: str, request: Request):
    job = app.state.jobs.get(key)
    if (not job or job.get('owner_id') != request.state.user['user_id']
            or job.get('session_key') != request.state.session_key): raise HTTPException(404, '생성 결과를 찾을 수 없습니다.')
    return job


@app.get('/api/jobs/{key}/audio')
def get_audio(key: str, request: Request, download: bool = False):
    job = get_job(key, request)
    path = job_path(job, 'outputs', 'wav')
    if job['status'] != 'completed' or not path.exists(): raise HTTPException(404, '생성된 음성이 없습니다.')
    spec = job['request']
    name = f'WiaVoice_{spec["model"]}_{spec["voice"]}_{key[:8]}.wav' if download else None
    return FileResponse(path, media_type='audio/wav', filename=name)


class SaveVoice(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)


@app.post('/api/jobs/{key}/save', status_code=201)
async def save_to_my_voice(key: str, body: SaveVoice, request: Request):
    job = get_job(key, request)
    if job['status'] != 'completed':
        raise HTTPException(409, '생성이 완료된 음성만 저장할 수 있습니다.')
    # Snapshot before yielding: session cleanup cannot delete the file mid-copy.
    try:
        audio = job_path(job, 'outputs', 'wav').read_bytes()
    except FileNotFoundError:
        raise HTTPException(404, '생성된 음성을 찾을 수 없습니다.') from None
    return await run_in_threadpool(library.save_voice, DATA, request.state.user['user_id'],
                                   dict(job), body.name, audio)


@app.get('/api/my-voices')
def my_voices(request: Request, search: str = Query('', max_length=100),
              offset: int = Query(0, ge=0), limit: int = Query(6, ge=1, le=100)):
    return library.list_voices(request.state.user['user_id'], search.strip(), offset, limit)


@app.get('/api/my-voices/{voice_id}/audio')
def my_voice_audio(voice_id: str, request: Request, download: bool = False):
    user_id = request.state.user['user_id']
    path = library.voice_directory(DATA, user_id, voice_id) / 'audio.wav'
    row = library.get_voice(user_id, voice_id)
    if not path.is_file(): raise HTTPException(404, '음성 파일을 찾을 수 없습니다.')
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]', '_', row['name']).strip('. ') or 'WiaVoice'
    return FileResponse(path, media_type='audio/wav', filename=name+'.wav' if download else None)


@app.post('/api/merge-actions', status_code=202)
def merge_voices(body: merger.MergeRequest, request: Request):
    return merger.submit(DATA, request.state.user['user_id'], body)


@app.get('/api/merge-actions')
def merge_history(request: Request):
    return merger.list_actions(request.state.user['user_id'])


@app.delete('/api/my-voices/{voice_id}')
def delete_my_voice(voice_id: str, request: Request):
    return library.delete_voice(DATA, request.state.user['user_id'], voice_id)


class MarketPreview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    upload_id: str = Field(pattern=r'^[a-f0-9]{32}$')


class MarketPublish(BaseModel):
    model_config = ConfigDict(extra='forbid')
    job_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=300)
    gender: Literal['male','female']
    consent: Literal[True]
    consent_version: Literal[marketplace.CONSENT_VERSION]

    @model_validator(mode='after')
    def require_description(self):
        self.description = self.description.strip()
        if not self.description: raise ValueError('한 줄 소개를 입력해 주세요.')
        return self


class MarketFavorite(BaseModel):
    enabled: bool


@app.get('/api/marketplace/config')
def market_config():
    return {'sample_text':marketplace.SAMPLE_TEXT,'consent_text':marketplace.CONSENT_TEXT,
            'consent_version':marketplace.CONSENT_VERSION}


@app.post('/api/marketplace/preview', status_code=202)
async def market_preview(spec: MarketPreview, request: Request):
    # The server fixes the model, mood, text and generation settings.
    job = await create_job(Generation(text=marketplace.SAMPLE_TEXT, model='higgs',
        voice='custom', emotion='neutral', upload_id=spec.upload_id), request)
    job['purpose'] = 'marketplace-preview'
    save_job(job)
    return job


@app.post('/api/marketplace', status_code=201)
async def market_publish(spec: MarketPublish, request: Request):
    name = spec.name.strip()
    if not name: raise HTTPException(422, '목소리 이름을 입력해 주세요.')
    job = get_job(spec.job_id, request)
    if job.get('purpose') != 'marketplace-preview' or job['status'] != 'completed':
        raise HTTPException(409, '마켓플레이스 샘플 생성이 완료된 뒤 등록해 주세요.')
    upload_id = job['request']['upload_id']
    require_upload_owner(upload_id, request.state.user['user_id'])
    try:
        reference = (DATA/'uploads'/f'{upload_id}.wav').read_bytes()
        audio = job_path(job, 'outputs', 'wav').read_bytes()
    except FileNotFoundError:
        raise HTTPException(409, '샘플이 만료되었습니다. 다시 업로드해 주세요.')
    seconds = sf.info(io.BytesIO(reference)).duration
    return await run_in_threadpool(marketplace.publish, DATA, request.state.user['user_id'],
        job, name, spec.description.strip(), reference, audio, seconds, spec.gender)


@app.get('/api/marketplace')
def market_list(request: Request, search: str = Query('',max_length=100), mine: bool=False,
                favorites: bool=False, offset: int=Query(0,ge=0), limit: int=Query(8,ge=1,le=100),
                sort: Literal['popular','latest']='popular'):
    return marketplace.list_voices(request.state.user['user_id'],search.strip(),mine,favorites,offset,limit,sort)


@app.get('/api/marketplace/{key}/{kind}')
def market_audio(key: str, kind: Literal['sample','reference'], request: Request):
    row=marketplace.get_voice(key)
    path=marketplace.directory(DATA,key)/('sample.wav' if kind=='sample' else 'reference.wav')
    if not path.is_file(): raise HTTPException(404,'음성 파일을 찾을 수 없습니다.')
    # Count explicit full reference downloads, not previews or range retries.
    if kind=='reference' and not request.headers.get('range'):
        marketplace.count_download(key,request.state.user['user_id'])
    filename = re.sub(r'[^\w가-힣 .-]','_',row['name'])[:80]+'.wav' if kind=='reference' else None
    return FileResponse(path,media_type='audio/wav',filename=filename)


@app.put('/api/marketplace/{key}/favorite')
def market_favorite(key: str, spec: MarketFavorite, request: Request):
    return marketplace.favorite(request.state.user['user_id'],key,spec.enabled)


@app.delete('/api/marketplace/{key}')
def market_delete(key: str, request: Request):
    return marketplace.delete_voice(DATA,request.state.user['user_id'],key)
