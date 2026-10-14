import json,time,hashlib
from pathlib import Path
import httpx
f=json.loads(Path('/tmp/wiavoice-auth-fixture.json').read_text())
origin='https://axforwork.wia.co.kr'
root=Path('/data/wiavoice/sessions')
with httpx.Client(base_url=origin,headers={'Origin':origin,'X-AX-Request':'1'},trust_env=False,timeout=30) as c:
    r=c.post('/api/auth/login',json={k:f[k] for k in ['employee_id','password']});r.raise_for_status()
    directory=root/hashlib.sha256(c.cookies.get('ax_platform_session').encode()).hexdigest()
    r=c.post('/wiavoice/api/jobs',json={'model':'qwen','text':'안녕하세요. 세션 저장 기능을 확인하고 있습니다.','voice':'Sohee','emotion':'calm'});r.raise_for_status();job=r.json()
    assert (directory/'jobs'/f'{job["id"]}.json').exists()
    print('Generation metadata stored in session directory',flush=True)
    for i in range(240):
        r=c.get('/wiavoice/api/jobs/'+job['id']);r.raise_for_status();job=r.json()
        if job['status'] in ['completed','failed']:break
        time.sleep(2)
    assert job['status']=='completed',job.get('message')
    audio=directory/'outputs'/f'{job["id"]}.wav'
    assert audio.read_bytes().startswith(b'RIFF')
    assert not (Path('/data/wiavoice/outputs')/audio.name).exists()
    assert c.get('/wiavoice/api/jobs/'+job['id']+'/audio').status_code==200
    assert len(c.get('/wiavoice/api/jobs').json())==1
    print('Real TTS output, playback, and session history verified',flush=True)
    r=c.post('/api/auth/logout');r.raise_for_status()
    for i in range(45):
        if not directory.exists():break
        time.sleep(1)
    assert not directory.exists(),'Reaper did not remove revoked platform session'
    print('Platform logout automatically deleted session folder',flush=True)
    r=c.post('/api/auth/login',json={k:f[k] for k in ['employee_id','password']});r.raise_for_status()
    assert c.get('/wiavoice/api/jobs').json()==[]
    assert c.get('/wiavoice/api/jobs/'+job['id']).status_code==404
    directory=root/hashlib.sha256(c.cookies.get('ax_platform_session').encode()).hexdigest()
    directory.mkdir(mode=0o700);(directory/'cleanup-probe').write_text('temporary test artifact')
    r=c.post('/wiavoice/api/auth/logout');r.raise_for_status()
    assert not directory.exists()
    print('New login has empty history; WiaVoice logout deletes immediately',flush=True)
