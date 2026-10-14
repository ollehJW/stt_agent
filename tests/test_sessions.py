import asyncio
import threading
import time
from unittest.mock import patch
from fastapi import HTTPException
from backend import main
import test_api
from test_api import wav


class SessionTest(test_api.APITest):
    def finished_job(self):
        r=self.client.post('/api/jobs',json={'text':'Hello','model':'qwen'})
        self.assertEqual(r.status_code,202,r.text)
        job=r.json()
        for _ in range(100):
            job=self.client.get('/api/jobs/'+job['id']).json()
            if job['status']=='completed': return job
            time.sleep(.01)
        self.fail('Generation did not finish')

    def test_storage_and_same_user_session_isolation(self):
        job=self.finished_job()
        directory=self.data/'sessions'/('a'*64)
        self.assertTrue((directory/'jobs'/f'{job["id"]}.json').is_file())
        self.assertTrue((directory/'outputs'/f'{job["id"]}.wav').is_file())
        self.assertFalse((self.data/'outputs'/f'{job["id"]}.wav').exists())
        def other_session(request: main.Request):
            request.state.user={'user_id':'test-user'}
            request.state.session_key='b'*64
        main.app.dependency_overrides[main.authorize]=other_session
        self.assertEqual(self.client.get('/api/jobs').json(),[])
        self.assertEqual(self.client.get('/api/jobs/'+job['id']).status_code,404)
        self.assertEqual(self.client.get('/api/jobs/'+job['id']+'/audio').status_code,404)

    def test_cleanup_preserves_active_and_retries_db_failure(self):
        job=self.finished_job()
        expired=self.data/'sessions'/('b'*64)
        expired.mkdir();(expired/'artifact.wav').write_bytes(b'audio')
        with patch.object(main,'active_session_keys',side_effect=HTTPException(503,'unavailable')):
            with self.assertRaises(HTTPException): self.client.portal.call(main.cleanup_sessions)
        self.assertTrue(expired.exists())
        with patch.object(main,'active_session_keys',return_value={'a'*64}):
            self.client.portal.call(main.cleanup_sessions)
        self.assertFalse(expired.exists())
        self.assertEqual(self.client.get('/api/jobs/'+job['id']).status_code,200)
        with patch.object(main,'active_session_keys',return_value=set()):
            self.client.portal.call(main.cleanup_sessions)
        self.assertFalse((self.data/'sessions'/('a'*64)).exists())
        self.assertEqual(self.client.get('/api/jobs').json(),[])
        self.assertTrue((self.data/'voices'/'Sohee_ko.wav').exists())

    def test_cleanup_during_generation_cannot_recreate_folder(self):
        started=threading.Event();release=threading.Event()
        class SlowEngine(test_api.FakeEngine):
            async def generate(self,payload):
                started.set()
                while not release.is_set(): await asyncio.sleep(.01)
                return wav()
        main.app.state.engine=SlowEngine()
        first=self.client.post('/api/jobs',json={'text':'first','model':'qwen'}).json()
        self.assertTrue(started.wait(2))
        second=self.client.post('/api/jobs',json={'text':'queued','model':'qwen'}).json()
        with patch.object(main,'active_session_keys',return_value=set()):
            self.client.portal.call(main.cleanup_sessions)
        release.set()
        self.client.portal.call(main.app.state.queue.join)
        self.assertFalse((self.data/'sessions'/('a'*64)).exists())
        self.assertNotIn(first['id'],main.app.state.jobs)
        self.assertNotIn(second['id'],main.app.state.jobs)
        # Worker is still usable after it skips deleted queue entries.
        self.finished_job()

    def test_restart_restores_only_session_jobs(self):
        # Test the loader in a separate FastAPI instance after pausing its worker.
        job=self.finished_job()
        old_dir=self.data/'jobs';old_dir.mkdir()
        (old_dir/'legacy.json').write_text('{"id":"legacy","status":"completed"}')
        from fastapi import FastAPI
        async def restart():
            isolated=FastAPI()
            async with main.lifespan(isolated):
                return dict(isolated.state.jobs)
        restored=self.client.portal.call(restart)
        self.assertIn(job['id'],restored)
        self.assertNotIn('legacy',restored)
