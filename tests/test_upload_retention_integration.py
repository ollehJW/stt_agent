import asyncio
import os
import threading
import unittest
from backend import main
from backend.upload_cleanup import cleanup_uploads, protected_uploads, TTL_SECONDS
from test_api import APITest, FakeEngine, wav

class UploadRetentionIntegration(unittest.TestCase):
    setUp = APITest.setUp
    def test_logout_during_generation_preserves_reference_until_worker_finishes(self):
        started=threading.Event();release=threading.Event()
        class SlowEngine(FakeEngine):
            async def generate(self,payload):
                started.set()
                while not release.is_set():await asyncio.sleep(.01)
                return wav()
        main.app.state.engine=SlowEngine()
        upload=self.client.post('/api/uploads',files={'file':('sample.wav',wav(),'audio/wav')})
        self.assertEqual(upload.status_code,201)
        key=upload.json()['id']
        for suffix in ['.wav','.json']:os.utime(self.data/'uploads'/(key+suffix),(1,1))
        response=self.client.post('/api/jobs',json={'text':'test','model':'fish','voice':'custom','upload_id':key})
        self.assertEqual(response.status_code,202)
        try:
            self.assertTrue(started.wait(3))
            self.client.portal.call(main.remove_session,'a'*64)
            def sweep():return cleanup_uploads(self.data,protected_uploads(main.app.state.jobs.values(),main.app.state.running_uploads))
            self.assertEqual(self.client.portal.call(sweep),0)
            self.assertTrue((self.data/'uploads'/(key+'.wav')).exists())
        finally:release.set()
        self.client.portal.call(main.app.state.queue.join)
        self.assertEqual(self.client.portal.call(sweep),1)
        self.assertEqual(self.client.post('/api/jobs',json={'text':'test','model':'fish','voice':'custom','upload_id':key}).status_code,404)
