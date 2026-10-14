"""Read every generated preview and verify its model/voice/emotion provenance."""
import json
import os
from pathlib import Path
import sys
import hashlib
import numpy as np
import soundfile as sf
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.previews import PREVIEW_TEXT, combinations, preview_key

def audit():
    data=Path(os.getenv('WIAVOICE_DATA','/data/wiavoice'))
    report={}
    hashes=set()
    for model,voice,emotion in combinations():
        key=preview_key(model,voice,emotion)
        path=data/'previews'/f'{key}.wav'
        metadata=json.loads(path.with_suffix('.json').read_text())
        assert (metadata['model'],metadata['voice'],metadata['emotion'])==(model,voice,emotion)
        assert metadata['text']==PREVIEW_TEXT
        job=json.loads((data/'jobs'/f'{metadata["job_id"]}.json').read_text())
        assert job['status']=='completed'
        for field,value in [('model',model),('voice',voice),('emotion',emotion),('text',PREVIEW_TEXT),('language','auto')]:
            assert job['request'][field]==value, (key,field)
        audio,sr=sf.read(path,dtype='float32')
        assert len(audio)>sr and np.isfinite(audio).all()
        assert np.max(np.abs(audio))>.0001
        assert len(audio)/sr<45
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest not in hashes, f'duplicate sample: {key}'
        hashes.add(digest)
        stats=report.setdefault(model,{'count':0,'min_seconds':100,'max_seconds':0,'sample_rates':set()})
        stats['count']+=1
        stats['min_seconds']=min(stats['min_seconds'],round(len(audio)/sr,2))
        stats['max_seconds']=max(stats['max_seconds'],round(len(audio)/sr,2))
        stats['sample_rates'].add(sr)
    for stats in report.values():stats['sample_rates']=sorted(stats['sample_rates'])
    return {'status':'PASS','total':len(hashes),'models':report}

if __name__=='__main__':print(json.dumps(audit(),ensure_ascii=False,indent=2))
