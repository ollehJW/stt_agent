import time
from contextlib import contextmanager
from unittest.mock import patch
from fastapi import HTTPException
from backend import auth, main
import test_api
from test_api import wav

class AuthTest(test_api.APITest):
    def setUp(self):
        super().setUp()
        main.app.dependency_overrides.clear()
        self.user = dict(user_id='alice',full_name='Test',employee_id='test',is_admin=False,
                         must_change_password=False,team_name='Test',expires_at=time.time()+3600)
        outer=self
        class DB:
            def execute(self,sql,args):
                self.sql=sql
                if sql.startswith('DELETE'): outer.user=None
                return self
            def fetchone(self): return outer.user
        @contextmanager
        def database(): yield DB()
        self.enterContext(patch.object(auth,'database',database))
        self.client.cookies.set(auth.COOKIE,'test-token')

    # Inherited behavior tests run against the real authentication dependency too.
    def test_session_validation(self):
        self.assertEqual(self.client.get('/api/auth/me').status_code,200)
        self.user=None
        self.assertEqual(self.client.get('/api/catalog').status_code,401)
        self.client.cookies.clear()
        for path in ['/api/jobs','/api/previews/'+'a'*24,'/api/voices/Sohee/ko','/api/uploads/'+'a'*32+'/audio']:
            self.assertEqual(self.client.get(path).status_code,401)
        self.assertEqual(self.client.post('/api/jobs',json={'text':'Hello','model':'qwen'}).status_code,401)

    def test_password_change_and_database_failure(self):
        self.user['must_change_password']=True
        self.assertEqual(self.client.get('/api/auth/me').status_code,403)
        with patch.object(auth,'current_user',side_effect=HTTPException(503,'unavailable')):
            self.assertEqual(self.client.get('/api/catalog').status_code,503)

    def test_ownership(self):
        upload=self.client.post('/api/uploads',files={'file':('voice.wav',wav(),'audio/wav')}).json()
        job=self.client.post('/api/jobs',json={'text':'Hello','model':'qwen'}).json()
        self.assertEqual(job['owner_id'],'alice')
        self.assertEqual(len(self.client.get('/api/jobs').json()),1)
        self.user['user_id']='bob'
        self.assertEqual(self.client.get('/api/jobs').json(),[])
        self.assertEqual(self.client.get('/api/jobs/'+job['id']).status_code,404)
        self.assertEqual(self.client.get('/api/jobs/'+job['id']+'/audio').status_code,404)
        self.assertEqual(self.client.get(upload['audio_url'].replace('/wiavoice','')).status_code,404)
        self.assertEqual(self.client.post('/api/jobs',json={'text':'Hello','model':'fish','voice':'custom','upload_id':upload['id']}).status_code,404)
        main.app.state.jobs[job['id']].pop('owner_id')
        self.user['user_id']='alice'
        self.assertEqual(self.client.get('/api/jobs/'+job['id']).status_code,404)

    def test_csrf_and_logout(self):
        self.assertEqual(self.client.post('/api/auth/logout',headers={'Origin':'https://evil.example'}).status_code,403)
        job=self.client.post('/api/jobs',json={'text':'logout cleanup','model':'qwen'}).json()
        directory=main.session_directory(auth.token_hash('test-token'))
        self.assertTrue(directory.exists())
        response=self.client.post('/api/auth/logout',headers={'Origin':auth.PLATFORM_ORIGIN})
        self.assertFalse(directory.exists())
        self.assertNotIn(job['id'],main.app.state.jobs)
        self.assertEqual(response.status_code,200)
        self.assertIn('Max-Age=0',response.headers['set-cookie'])
        self.assertIn('no-store',response.headers['cache-control'])
        self.assertEqual(self.client.get('/api/auth/me').status_code,401)
