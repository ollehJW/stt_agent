"""Add only WiaVoice to the existing supervisor and gateway; preserve other services."""
from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import yaml

home = Path.home()
stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
data = Path('/data/wiavoice')
(data / 'logs').mkdir(parents=True, exist_ok=True)
(data / 'backups').mkdir(exist_ok=True)
config = Path('/data/ax_for_works/supervisord.conf')
contents = config.read_text()
for component in ['backend', 'frontend']:
    name = f'wiavoice-{component}'
    if f'[program:{name}]' in contents:
        continue
    command = f'/bin/bash {home}/wiavoice/ops/backend.sh' if component == 'backend' else f'{home}/.nvm/versions/node/v24.20.0/bin/node {home}/wiavoice/frontend/server.mjs'
    contents += f'''\n[program:{name}]
command={command}
directory={home}/wiavoice
autostart=true
autorestart=unexpected
startsecs=3
startretries=3
stopsignal=TERM
stopasgroup=true
killasgroup=true
stopwaitsecs=50
redirect_stderr=true
stdout_logfile={data}/logs/{component}.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=3
'''
if contents != config.read_text():
    shutil.copy2(config, data / 'backups' / f'supervisord-{stamp}.conf')
    config.write_text(contents)
ctl = [str(home/'ax_for_works/.venv/bin/supervisorctl'), '-c', str(config)]
subprocess.run(ctl+['reread'], check=True)
subprocess.run(ctl+['update', 'wiavoice-backend', 'wiavoice-frontend'], check=True)

gateway = Path('/data/ax_for_works/config/config.yaml')
source = gateway.read_text()
parsed = yaml.safe_load(source)
existing = [r for r in parsed['gateways'] if r['prefix'] == '/wiavoice']
if not existing:
    addition = '''
  # WiaVoice: desktop voice generation, shared platform login
  - prefix: /wiavoice
    upstream: http://127.0.0.1:1005
    enabled: true
    require_login: true
    redirect_hosts:
      - 127.0.0.1:1015
    read_timeout_seconds: 660
'''
    updated = source + addition
    yaml.safe_load(updated)
    shutil.copy2(gateway, data / 'backups' / f'gateway-{stamp}.yaml')
    temp = gateway.with_suffix('.wiavoice.tmp')
    temp.write_text(updated)
    temp.replace(gateway)
elif existing[0]['upstream'] != 'http://127.0.0.1:1005':
    raise RuntimeError('Existing WiaVoice route differs; inspect before replacing')
print('WiaVoice runtime and gateway configured.')
