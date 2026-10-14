"""Real PostgreSQL ownership/consent/file lifecycle with a fake synthesis engine."""
import time
from contextlib import contextmanager
from unittest.mock import patch
from backend import main, marketplace, auth
from test_library import LibraryTest
from test_api import wav

class MarketplaceTest(LibraryTest):
    def remove_user(self):
        with auth.database() as db:
            db.execute('DELETE FROM wiavoice.market_favorites WHERE user_id=%s OR voice_id IN (SELECT voice_id FROM wiavoice.market_voices WHERE user_id=%s)',(self.uid,self.uid))
            db.execute('DELETE FROM wiavoice.market_voices WHERE user_id=%s',(self.uid,))
        super().remove_user()

    def preview(self):
        upload=self.client.post('/api/uploads',files={'file':('reference.wav',wav(),'audio/wav')}).json()
        response=self.client.post('/api/marketplace/preview',json={'upload_id':upload['id']})
        self.assertEqual(response.status_code,202,response.text)
        job=response.json()
        for _ in range(200):
            job=self.client.get('/api/jobs/'+job['id']).json()
            if job['status']=='completed':return job
            time.sleep(.01)
        self.fail(str(job))

    def publish(self,job):
        return self.client.post('/api/marketplace',json={'job_id':job['id'],'name':'  Test voice  ','description':'차분한 안내 목소리','gender':'male',
            'consent':True,'consent_version':marketplace.CONSENT_VERSION})

    def test_market_consent_and_fixed_preview(self):
        job=self.preview()
        self.assertEqual(job['request']['model'],'higgs')
        self.assertEqual(job['request']['emotion'],'neutral')
        self.assertEqual(job['request']['text'],marketplace.SAMPLE_TEXT)
        body={'job_id':job['id'],'name':'Voice','description':'차분한 안내 목소리','gender':'male','consent_version':marketplace.CONSENT_VERSION}
        for extra in [{},{'consent':False},{'consent':True,'consent_version':'invalid'},{'consent':True,'name':' '}]:
            self.assertEqual(self.client.post('/api/marketplace',json={**body,**extra}).status_code,422)
        for description in ['', '   ', None]:
            self.assertEqual(self.client.post('/api/marketplace',json={**body,'consent':True,'description':description}).status_code,422)
        missing={**body,'consent':True};missing.pop('description')
        self.assertEqual(self.client.post('/api/marketplace',json=missing).status_code,422)
        for gender in ['', 'invalid', None]:
            self.assertEqual(self.client.post('/api/marketplace',json={**body,'consent':True,'gender':gender}).status_code,422)
        missing_gender={**body,'consent':True};missing_gender.pop('gender')
        self.assertEqual(self.client.post('/api/marketplace',json=missing_gender).status_code,422)
        ordinary=self.completed_job()
        self.assertEqual(self.publish(ordinary).status_code,409)
        response=self.publish(job)
        self.assertEqual(response.status_code,201,response.text)
        voice=response.json();self.assertEqual(voice['name'],'Test voice');self.assertEqual(voice['gender'],'male')
        self.assertEqual(self.publish(job).json()['voice_id'],voice['voice_id'])
        with auth.database() as db:
            row=db.execute('SELECT * FROM wiavoice.market_voices WHERE voice_id=%s',(voice['voice_id'],)).fetchone()
        self.assertEqual(row['consent_text'],marketplace.CONSENT_TEXT)
        self.assertIsNotNone(row['consent_at'])
        self.client.portal.call(main.remove_session,'a'*64)
        self.assertEqual(self.client.get(voice['audio_url'].replace('/wiavoice','')).status_code,200)
        download=self.client.get(voice['download_url'].replace('/wiavoice',''))
        self.assertEqual(download.status_code,200)
        self.assertIn('attachment',download.headers['content-disposition'])

    def test_market_shared_access_owner_delete_and_favorites(self):
        job=self.preview();voice=self.publish(job).json();key=voice['voice_id']
        endpoint='/api/marketplace/'+key
        for _ in range(2):self.assertEqual(self.client.put(endpoint+'/favorite',json={'enabled':True}).status_code,200)
        favorites=self.client.get('/api/marketplace?favorites=true').json()
        self.assertEqual(favorites['total'],1)
        self.assertTrue(favorites['items'][0]['favorite'])
        self.assertEqual(self.client.get('/api/marketplace?mine=true').json()['total'],1)
        def other(request:main.Request):
            request.state.user={'user_id':'other-user'};request.state.session_key='b'*64
        main.app.dependency_overrides[main.authorize]=other
        self.assertEqual(self.client.get(endpoint+'/sample').status_code,200)
        self.assertEqual(self.client.get('/api/marketplace?mine=true').json()['total'],0)
        self.assertEqual(self.client.get('/api/marketplace?favorites=true').json()['total'],0)
        self.assertEqual(self.client.delete(endpoint).status_code,404)
        self.assertEqual(self.publish(job).status_code,404)
        def owner(request:main.Request):
            request.state.user={'user_id':self.uid};request.state.session_key='a'*64
        main.app.dependency_overrides[main.authorize]=owner
        self.assertEqual(self.client.delete(endpoint).status_code,200)
        self.assertFalse(marketplace.directory(self.data,key).exists())
        self.assertEqual(self.client.get(endpoint+'/sample').status_code,404)
        self.assertEqual(self.client.get(endpoint+'/reference').status_code,404)
        self.assertEqual(self.client.get('/api/marketplace?favorites=true').json()['total'],0)
        self.assertEqual(self.client.put(endpoint+'/favorite',json={'enabled':True}).status_code,404)
        self.assertEqual(self.publish(job).status_code,409)

    def test_market_failed_commit_removes_files(self):
        job=self.preview()
        @contextmanager
        def fail():
            with auth.database() as db:
                yield db
                raise RuntimeError('failed commit')
        with patch.object(marketplace,'database',fail):
            with self.assertRaises(RuntimeError):self.publish(job)
        self.assertEqual(list((self.data/'marketplace').iterdir()),[])
        self.assertEqual(self.client.get('/api/marketplace?mine=true').json()['total'],0)

    def test_market_pagination_and_search(self):
        job=self.preview()
        audio=main.job_path(job,'outputs','wav').read_bytes()
        ids=[]
        from uuid import uuid4
        for i in range(9):
            voice=marketplace.publish(self.data,self.uid,{**job,'id':uuid4().hex},f'Grid {i}','findable',wav(),audio,4,'female')
            ids.append(voice['voice_id'])
        first=self.client.get('/api/marketplace?mine=true').json()
        second=self.client.get('/api/marketplace?mine=true&offset=8').json()
        self.assertEqual(first['total'],9)
        self.assertEqual(len(first['items']),8)
        self.assertEqual(len(second['items']),1)
        self.assertEqual(len({v['voice_id'] for v in first['items']+second['items']}),9)
        self.assertEqual(self.client.get('/api/marketplace?mine=true&search=Grid%204').json()['total'],1)
        self.assertEqual(self.client.get('/api/marketplace?mine=true&search=findable').json()['total'],9)
        self.assertEqual(self.client.get('/api/marketplace?offset=-1').status_code,422)

    def test_download_counts_and_sorting(self):
        job=self.preview();audio=main.job_path(job,'outputs','wav').read_bytes()
        from uuid import uuid4
        from concurrent.futures import ThreadPoolExecutor
        older=marketplace.publish(self.data,self.uid,{**job,'id':uuid4().hex},'Popular','sample',wav(),audio,4,'male')
        newer=marketplace.publish(self.data,self.uid,{**job,'id':uuid4().hex},'Latest','sample',wav(),audio,4,'female')
        path='/api/marketplace/'+older['voice_id']
        def count():return marketplace.get_voice(older['voice_id'])['download_count']
        self.assertEqual(count(),0)
        self.assertEqual(self.client.get(path+'/sample').status_code,200)
        self.assertEqual(count(),0)
        self.assertEqual(self.client.get(path+'/reference',headers={'Range':'bytes=0-31'}).status_code,206)
        self.assertEqual(count(),0)
        self.assertEqual(self.client.get(path+'/reference').status_code,200)
        self.assertEqual(count(),1)
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _:marketplace.count_download(older['voice_id']),range(8)))
        self.assertEqual(count(),9)
        popular=self.client.get('/api/marketplace?mine=true').json()['items']
        latest=self.client.get('/api/marketplace?mine=true&sort=latest').json()['items']
        self.assertEqual(popular[0]['voice_id'],older['voice_id'])
        self.assertEqual(popular[0]['download_count'],9)
        self.assertEqual(latest[0]['voice_id'],newer['voice_id'])
        self.assertEqual(self.client.get('/api/marketplace?sort=invalid').status_code,422)
        (marketplace.directory(self.data,older['voice_id'])/'reference.wav').unlink()
        self.assertEqual(self.client.get(path+'/reference').status_code,404)
        self.assertEqual(count(),9)
