"""Keep input text for admin details; recover only still-available originals."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.auth import database

with database() as db:
    db.execute('ALTER TABLE wiavoice.generation_runs ADD COLUMN IF NOT EXISTS text TEXT')
    saved = db.execute('''UPDATE wiavoice.generation_runs g SET text=v.text
        FROM wiavoice.voices v WHERE g.job_id=v.source_job_id AND g.user_id=v.user_id
        AND g.text IS NULL''').rowcount
    recovered = 0
    for path in Path('/data/wiavoice/sessions').glob('*/jobs/*.json'):
        try:
            job = json.loads(path.read_text())
            text = job['request']['text']
            if not isinstance(text, str):
                continue
            recovered += db.execute('''UPDATE wiavoice.generation_runs SET text=%s
                WHERE job_id=%s AND user_id=%s AND text IS NULL''',
                (text, job['id'], job['owner_id'])).rowcount
        except (OSError, ValueError, KeyError):
            continue
print(f'Generation text ready; recovered {saved + recovered} records')
