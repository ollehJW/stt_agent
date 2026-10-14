from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.auth import database
with database() as db:
    db.execute((Path(__file__).resolve().parents[1]/'backend/sql/merge_action.sql').read_text())
print('wiavoice.merge_action schema ready')
