import asyncio
import os
from pathlib import Path
import signal
import time
import httpx


class Engine:
    """One GPU model at a time; owns only processes launched by WiaVoice."""
    ports = {'qwen': 18180, 'fish': 18181, 'higgs': 18182}

    def __init__(self, data: Path):
        self.data = data
        self.model = None
        self.process = None
        self.log = None
        self.state = 'idle'
        self.last_used = time.monotonic()

    async def stop(self):
        if self.process:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(self.process.wait(), 30)
            except TimeoutError:
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await self.process.wait()
        if self.log:
            self.log.close()
        self.process = self.log = self.model = None
        self.state = 'idle'

    async def ensure(self, model: str):
        if self.model == model and self.process and self.process.returncode is None:
            return
        await self.stop()
        self.state = 'loading'
        self.model = model
        root = Path(os.getenv('WIATTS_ROOT', '/home/jongwook/wiatts'))
        self.log = (self.data / 'logs' / f'engine-{model}.log').open('w')
        self.process = await asyncio.create_subprocess_exec(
            str(root / 'launch_model.sh'), model, cwd=root,
            stdout=self.log, stderr=self.log, start_new_session=True,
        )
        async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
            for _ in range(240):
                if self.process.returncode is not None:
                    raise RuntimeError('음성 모델을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.')
                try:
                    r = await client.get(f'http://127.0.0.1:{self.ports[model]}/health')
                    if r.status_code == 200:
                        self.state = 'ready'
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(3)
        raise RuntimeError('모델 준비 시간이 초과되었습니다. 다시 시도해 주세요.')

    async def generate(self, payload):
        self.state = 'generating'
        try:
            async with httpx.AsyncClient(timeout=900, trust_env=False) as client:
                r = await client.post(f'http://127.0.0.1:{self.ports[self.model]}/v1/audio/speech', json=payload)
                r.raise_for_status()
                if not r.content.startswith(b'RIFF'):
                    raise RuntimeError('올바른 음성 파일이 반환되지 않았습니다.')
                return r.content
        finally:
            self.last_used = time.monotonic()
            self.state = 'ready'
