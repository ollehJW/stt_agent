"""Opt-in PostgreSQL integration: isolated temporary user and filesystem."""
import os
import time
import unittest
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from unittest.mock import patch
from backend import main, library, auth
import test_api

@unittest.skipUnless(os.getenv('WIAVOICE_TEST_DB')=='1', 'requires explicit PostgreSQL integration opt-in')
class LibraryTest(test_api.APITest):
    def setUp(self):
        super().setUp()
        self.uid=str(uuid4())
        with auth.database() as db:
            db.execute('''INSERT INTO platform.users(user_id,employee_id,password_hash,full_name,is_active,created_at,updated_at)
                VALUES(%s,%s,'disabled-test-account','WiaVoice integration',FALSE,now(),now())''',(self.uid,'wvtest_'+uuid4().hex))
        self.addCleanup(self.remove_user)
        def user(request: main.Request):
            request.state.user={'user_id':self.uid}
            request.state.session_key='a'*64
        main.app.dependency_overrides[main.authorize]=user

    def remove_user(self):
        with auth.database() as db:
            db.execute('DELETE FROM wiavoice.merge_action WHERE user_id=%s',(self.uid,))
            db.execute('DELETE FROM wiavoice.voices WHERE user_id=%s',(self.uid,))
            db.execute('DELETE FROM platform.users WHERE user_id=%s',(self.uid,))

    def completed_job(self):
        job=self.client.post('/api/jobs',json={'text':'안녕하세요. 저장 테스트입니다.','model':'qwen'}).json()
        for _ in range(100):
            job=self.client.get('/api/jobs/'+job['id']).json()
            if job['status']=='completed':return job
            time.sleep(.01)
        self.fail('Generation failed')

    def test_save_survives_session_cleanup(self):
        job=self.completed_job()
        source=main.job_path(job,'outputs','wav').read_bytes()
        response=self.client.post('/api/jobs/'+job['id']+'/save',json={'name':'  소개 목소리  '})
        self.assertEqual(response.status_code,201,response.text)
        voice=response.json();self.assertEqual(voice['name'],'소개 목소리')
        path=self.data/'workspace'/self.uid/voice['voice_id']/'audio.wav'
        self.assertEqual(path.read_bytes(),source)
        self.client.portal.call(main.remove_session,'a'*64)
        self.assertTrue(path.exists())
        result=self.client.get('/api/my-voices?search=소개').json()
        self.assertEqual(result['total'],1)
        self.assertEqual(self.client.get(voice['audio_url'].replace('/wiavoice','')+'?download=true').content,source)
        self.assertEqual(self.client.get('/api/my-voices?search=missing').json()['total'],0)

    def test_private_access_and_validation(self):
        job=self.completed_job()
        for name in ['','   ','a'*101]:
            self.assertEqual(self.client.post('/api/jobs/'+job['id']+'/save',json={'name':name}).status_code,422)
        self.assertEqual(self.client.post('/api/jobs/'+job['id']+'/save',json={'name':'x','user_id':'other'}).status_code,422)
        voice=self.client.post('/api/jobs/'+job['id']+'/save',json={'name':'private'}).json()
        def other(request: main.Request):
            request.state.user={'user_id':'other-user'};request.state.session_key='b'*64
        main.app.dependency_overrides[main.authorize]=other
        self.assertEqual(self.client.get('/api/my-voices').json()['total'],0)
        self.assertEqual(self.client.get(voice['audio_url'].replace('/wiavoice','')).status_code,404)
        self.assertEqual(self.client.post('/api/jobs/'+job['id']+'/save',json={'name':'stolen'}).status_code,404)

    def test_concurrent_save_is_idempotent(self):
        job=self.completed_job();audio=main.job_path(job,'outputs','wav').read_bytes()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:library.save_voice(self.data,self.uid,job,'Repeated',audio),range(2)))
        self.assertEqual(results[0]['voice_id'],results[1]['voice_id'])
        self.assertEqual(self.client.get('/api/my-voices').json()['total'],1)
        self.assertEqual(len(list((self.data/'workspace'/self.uid).glob('*/audio.wav'))),1)

    def test_failed_transaction_cleans_up_file(self):
        job=self.completed_job();audio=main.job_path(job,'outputs','wav').read_bytes()
        @contextmanager
        def failed_commit():
            with auth.database() as db:
                yield db
                raise RuntimeError('simulated failure before commit')
        with patch.object(library,'database',failed_commit):
            with self.assertRaises(RuntimeError):library.save_voice(self.data,self.uid,job,'failure',audio)
        self.assertEqual(self.client.get('/api/my-voices').json()['total'],0)
        self.assertEqual(list((self.data/'workspace'/self.uid).glob('*/audio.wav')),[])
