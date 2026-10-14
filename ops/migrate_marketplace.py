from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.auth import database
with database() as db:
    db.execute((Path(__file__).resolve().parents[1]/'backend/sql/marketplace.sql').read_text())
print('Marketplace schema ready')
