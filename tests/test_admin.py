import json
from pathlib import Path
from unittest.mock import patch
from backend import main,auth,telemetry,marketplace
from test_marketplace import MarketplaceTest

class AdminTest(MarketplaceTest):
    def remove_user(self):
        with auth.database() as db:
            db.execute('DELETE FROM wiavoice.admin_audit WHERE actor_id=%s',(self.uid,))
        super().remove_user()

    def identity(self,admin=False):
        def user(request:main.Request):
            request.state.user={'user_id':self.uid,'is_admin':admin}
            request.state.session_key='a'*64
        main.app.dependency_overrides[main.authorize]=user

    def test_admin_authorization_every_route(self):
        self.identity(False)
        for path in ['/api/admin/options','/api/admin/operations','/api/admin/voices',
                     '/api/admin/voices/generation/unknown','/api/admin/marketplace',
                     '/api/admin/marketplace/unknown','/api/admin/marketplace/unknown/sample',
                     '/api/admin/saved/unknown/audio']:
            self.assertEqual(self.client.get(path).status_code,403,path)
        self.assertEqual(self.client.post('/api/admin/marketplace/unknown/actions',json={'action':'hide','reason':'test'}).status_code,403)

    def test_durable_generation_stats_and_period_validation(self):
        job=self.completed_job()
        pending=list((self.data/'telemetry'/'pending').glob('*.json'))
        self.assertTrue(pending)
        self.assertEqual(json.loads(pending[0].read_text())['text'],job['request']['text'])
        with patch.object(telemetry,'database',side_effect=RuntimeError('unavailable')):
            with self.assertRaises(RuntimeError):telemetry.flush(self.data)
        self.assertTrue(list((self.data/'telemetry'/'pending').glob('*.json')))
        telemetry.flush(self.data)
        self.assertFalse(list((self.data/'telemetry'/'pending').glob('*.json')))
        self.client.portal.call(main.remove_session,'a'*64)
        self.identity(True)
        response=self.client.get('/api/admin/operations',params={'user_id':self.uid})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['summary']['completed'],1)
        self.assertEqual(response.json()['summary']['audio_seconds'],4)
        record=self.client.get('/api/admin/voices/generation/'+job['id']).json()
        self.assertEqual(record['status'],'completed');self.assertIsNotNone(record['completed_at'])
        self.assertEqual(record['text'],job['request']['text'])
        rows=self.client.get('/api/admin/voices',params={'user_id':self.uid}).json()
        self.assertEqual(rows['total'],1)
        self.assertNotIn('text',rows['items'][0])
        self.identity(False)
        self.assertEqual(self.client.get('/api/admin/voices/generation/'+job['id']).status_code,403)
        self.identity(True)
        self.assertEqual(self.client.get('/api/admin/operations?start=2026-10-15&end=2026-10-14').status_code,422)
        self.assertEqual(self.client.get('/api/admin/operations?start=2020-01-01&end=2026-10-14').status_code,422)
        self.assertEqual(self.client.get('/api/admin/options').status_code,200)

    def test_market_moderation_and_audit(self):
        job=self.preview();voice=self.publish(job).json();key=voice['voice_id'];endpoint='/api/admin/marketplace/'+key
        self.client.put('/api/marketplace/'+key+'/favorite',json={'enabled':True})
        self.identity(True)
        self.assertEqual(self.client.get('/api/admin/marketplace',params={'user_id':self.uid}).json()['total'],1)
        for body in [{'action':'hide','reason':''},{'action':'hide','reason':'  '},{'action':'edit','reason':'missing fields'}]:
            self.assertEqual(self.client.post(endpoint+'/actions',json=body).status_code,422)
        r=self.client.post(endpoint+'/actions',json={'action':'edit','name':'Renamed','description':'Updated description','gender':'female','reason':'정보 수정 검증'})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.client.post(endpoint+'/actions',json={'action':'hide','reason':'공개 중지 검증'}).status_code,200)
        self.assertEqual(self.client.get(endpoint+'/sample').status_code,200)
        self.identity(False)
        self.assertEqual(self.client.get('/api/marketplace?mine=true').json()['total'],0)
        self.assertEqual(self.client.get('/api/marketplace?favorites=true').json()['total'],0)
        for suffix in ['/sample','/reference']:
            self.assertEqual(self.client.get('/api/marketplace/'+key+suffix).status_code,404)
        self.assertEqual(self.client.put('/api/marketplace/'+key+'/favorite',json={'enabled':True}).status_code,404)
        self.identity(True)
        self.assertEqual(self.client.post(endpoint+'/actions',json={'action':'publish','reason':'재공개 검증'}).status_code,200)
        self.assertEqual(self.client.get('/api/marketplace?favorites=true').json()['total'],1)
        detail=self.client.get(endpoint).json();self.assertEqual(detail['voice']['name'],'Renamed')
        self.assertEqual(detail['voice']['consent_text'],marketplace.CONSENT_TEXT)
        self.assertEqual([r['action'] for r in detail['history']],['publish','hide','edit'])
        self.assertTrue(all(r['reason'] for r in detail['history']))
        self.assertEqual(self.client.post(endpoint+'/actions',json={'action':'delete','reason':'삭제 검증'}).status_code,200)
        self.assertFalse(marketplace.directory(self.data,key).exists())
        self.assertEqual(self.client.get(endpoint+'/sample').status_code,404)
        self.assertEqual(self.client.get(endpoint).json()['history'][0]['action'],'delete')
        self.assertEqual(self.client.get('/api/admin/marketplace',params={'user_id':self.uid,'state':'deleted'}).json()['total'],1)

    def test_saved_audio_not_audited_and_download_events(self):
        job=self.completed_job();voice=self.client.post('/api/jobs/'+job['id']+'/save',json={'name':'Saved'}).json()
        sample=self.publish(self.preview()).json()
        self.client.get('/api/marketplace/'+sample['voice_id']+'/reference')
        self.identity(True)
        self.assertEqual(self.client.get('/api/admin/voices',params={'kind':'saved','user_id':self.uid}).json()['total'],1)
        self.assertEqual(self.client.get('/api/admin/voices/saved/'+voice['voice_id']).status_code,200)
        self.assertEqual(self.client.get('/api/admin/saved/'+voice['voice_id']+'/audio').status_code,200)
        with auth.database() as db:
            self.assertEqual(db.execute('SELECT count(*) AS n FROM wiavoice.admin_audit WHERE actor_id=%s AND action=%s',(self.uid,'listen_saved')).fetchone()['n'],0)
            self.assertEqual(db.execute('SELECT count(*) AS n FROM wiavoice.download_events WHERE user_id=%s',(self.uid,)).fetchone()['n'],1)
