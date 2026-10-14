"""Durable metadata outbox; generation never depends on database availability."""
import asyncio
from datetime import datetime,timezone
import json
import logging
import time
from uuid import uuid4
from starlette.concurrency import run_in_threadpool
from .auth import database

logger=logging.getLogger('wiavoice')


def record(data,job):
    spec=job['request']
    row={'job_id':job['id'],'user_id':job['owner_id'],'model':spec['model'],
         'voice':spec['voice'],'emotion':spec['emotion'],'purpose':job.get('purpose') or 'generation',
         'text':spec['text'],'character_count':len(spec['text']),'status':job['status'],
         'audio_seconds':job.get('seconds'),'generation_seconds':job.get('generation_seconds'),
         'trimmed_seconds':job.get('trimmed_trailing_seconds',0),
         'error_message':job.get('message') if job['status'] in ['failed','cancelled'] else None,
         'created_at':job['created_at'],'started_at':job.get('started_at'),
         'completed_at':job.get('completed_at'),'recorded_at':datetime.now(timezone.utc).isoformat()}
    folder=data/'telemetry'/'pending';folder.mkdir(mode=0o700,parents=True,exist_ok=True)
    path=folder/f'{time.time_ns()}_{uuid4().hex}.json'
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(row,ensure_ascii=False));temp.replace(path)


def flush(data):
    folder=data/'telemetry'/'pending'
    files=sorted(folder.glob('*.json'))[:100]
    if not files:return
    with database() as db:
        for path in files:
            row=json.loads(path.read_text())
            keys=list(row)
            # No FK failure for a deleted platform account; its telemetry is discarded.
            db.execute('INSERT INTO wiavoice.generation_runs ('+','.join(keys)+') SELECT '+','.join(['%s']*len(keys))+
                ' WHERE EXISTS (SELECT 1 FROM platform.users WHERE user_id=%s) ON CONFLICT(job_id) DO UPDATE SET '+
                ','.join(f'{k}=EXCLUDED.{k}' for k in keys if k!='job_id')+
                ' WHERE EXCLUDED.recorded_at>=wiavoice.generation_runs.recorded_at',(*row.values(),row['user_id']))
    # Immutable outbox entries: new updates always have different filenames.
    for path in files:path.unlink(missing_ok=True)


async def worker(data,stop):
    while not stop.is_set():
        try:await run_in_threadpool(flush,data)
        except Exception:logger.exception('Generation telemetry will retry')
        try:await asyncio.wait_for(stop.wait(),3)
        except TimeoutError:pass
    try:await run_in_threadpool(flush,data)
    except Exception:logger.exception('Pending telemetry preserved for next startup')
