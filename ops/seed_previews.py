"""Generate resumable, real model/voice/emotion previews through the service queue."""
import json
import os
from pathlib import Path
import sys
import time
import httpx
import soundfile as sf
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.previews import PREVIEW_TEXT, combinations, preview_key

DATA = Path(os.getenv('WIAVOICE_DATA', '/data/wiavoice'))
DEST = DATA / 'previews'
DEST.mkdir(parents=True, exist_ok=True)
client = httpx.Client(base_url='http://127.0.0.1:1015/api', timeout=30)
items = list(combinations())
failures = []
for index, (model, voice, emotion) in enumerate(items, 1):
    key = preview_key(model, voice, emotion)
    path = DEST / f'{key}.wav'
    metadata = DEST / f'{key}.json'
    if path.exists() and metadata.exists():
        continue
    for attempt in range(3):
        try:
            response = client.post('/jobs', json=dict(text=PREVIEW_TEXT, model=model, voice=voice, emotion=emotion, language='auto', reference_language='ko'))
            response.raise_for_status()
            job = response.json()
            deadline = time.monotonic() + 1200
            while job['status'] not in ['completed', 'failed']:
                if time.monotonic() > deadline: raise RuntimeError('job timeout')
                time.sleep(.5)
                response = client.get('/jobs/' + job['id'])
                response.raise_for_status()
                job = response.json()
            if job['status'] != 'completed': raise RuntimeError(job['message'])
            source = DATA / 'outputs' / f'{job["id"]}.wav'
            info = sf.info(source)
            if info.duration < 1 or info.duration > 45: raise RuntimeError(f'unexpected duration {info.duration}')
            temp = path.with_suffix('.tmp')
            temp.write_bytes(source.read_bytes())
            temp.replace(path)
            metadata.write_text(json.dumps(dict(model=model, voice=voice, emotion=emotion, text=PREVIEW_TEXT, seconds=round(info.duration,2), job_id=job['id']), ensure_ascii=False))
            print(f'{index}/{len(items)} {model} {voice} {emotion}: {info.duration:.2f}s', flush=True)
            break
        except Exception as exc:
            print(f'RETRY {model} {voice} {emotion} attempt={attempt+1}: {exc}', flush=True)
            time.sleep(3)
    else:
        failures.append((model,voice,emotion))
print(json.dumps({'completed':len(list(DEST.glob('*.wav'))),'expected':len(items),'failures':failures}), flush=True)
sys.exit(bool(failures))
