"""Run on the target server before starting WiaVoice. Creates 18 neutral references."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.catalog import VOICES, REFERENCE_TEXTS

root = Path('/home/jongwook/wiatts')
out = Path('/data/wiavoice/voices')
out.mkdir(parents=True, exist_ok=True)
with (out / 'seed.log').open('a') as log:
    process = subprocess.Popen([str(root / 'launch_model.sh'), 'qwen'], cwd=root,
        stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        for _ in range(240):
            if process.poll() is not None: raise RuntimeError('Qwen startup failed')
            try:
                if urllib.request.urlopen('http://127.0.0.1:18180/health', timeout=2).status == 200: break
            except OSError: time.sleep(3)
        else: raise TimeoutError('Qwen startup timeout')
        for voice in VOICES:
            for language, text in REFERENCE_TEXTS.items():
                file = out / f'{voice["id"]}_{language}.wav'
                if file.exists(): continue
                payload = {'input': text, 'voice': voice['id'], 'language': 'Korean' if language == 'ko' else 'English',
                    'instructions': 'Speak naturally and clearly in a neutral, friendly tone.',
                    'response_format': 'wav', 'stream': False, 'max_new_tokens': 2048}
                request = urllib.request.Request('http://127.0.0.1:18180/v1/audio/speech', data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(request, timeout=900) as r: data = r.read()
                if not data.startswith(b'RIFF'): raise RuntimeError('Invalid audio')
                file.write_bytes(data)
                file.with_suffix('.json').write_text(json.dumps({'text':text, 'request':payload}, ensure_ascii=False, indent=2))
                print(file.name, len(data), flush=True)
    finally:
        try: os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError: pass
        try: process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
