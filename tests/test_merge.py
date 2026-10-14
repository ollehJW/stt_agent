import io
from uuid import uuid4
import numpy as np
import soundfile as sf
from backend import merger,library,main,auth
import test_library

class MergeTest(test_library.LibraryTest):
    def sources(self):
        voices=[]
        for index,(rate,seconds,level,model) in enumerate([(24000,.1,.1,'qwen'),(48000,.2,.3,'fish'),(44100,.3,.5,'higgs')]):
            b=io.BytesIO();sf.write(b,np.full((round(rate*seconds),2),level,dtype='float32'),rate,format='WAV',subtype='PCM_16')
            job={'id':uuid4().hex,'seconds':seconds,'sample_rate':rate,'request':{'model':model,'voice':'Sohee' if index==0 else 'Ryan','emotion':'neutral' if index==0 else 'sad','text':f'text-{index}','instructions':'','language':'auto'}}
            voices.append(library.save_voice(self.data,self.uid,job,f'voice-{index}',b.getvalue()))
        return voices

    def action(self,voices):
        body={'request_id':uuid4().hex,'name':'병합 테스트','voice_ids':[v['voice_id'] for v in voices],'gaps_seconds':[.2,.4]}
        r=self.client.post('/api/merge-actions',json=body)
        self.assertEqual(r.status_code,202,r.text)
        with auth.database() as db:action=db.execute('SELECT * FROM wiavoice.merge_action WHERE action_id=%s',(r.json()['action_id'],)).fetchone()
        return body,action

    def test_audio_order_silence_metadata_and_persistence(self):
        voices=self.sources();body,action=self.action(list(reversed(voices)))
        merger.process(self.data,action)
        with auth.database() as db:
            row=db.execute('SELECT * FROM wiavoice.voices WHERE voice_id=%s',(action['action_id'],)).fetchone()
        self.assertEqual(row['text'],'text-2\n\ntext-1\n\ntext-0')
        self.assertEqual(row['model'],'merged');self.assertEqual(row['speaker'],'mixed')
        self.assertEqual(row['emotion'],'mixed');self.assertIsNone(row['source_job_id'])
        audio,rate=sf.read(library.voice_directory(self.data,self.uid,row['voice_id'])/'audio.wav')
        self.assertEqual(rate,48000);self.assertEqual(len(audio),57600)
        self.assertAlmostEqual(audio[1000:5000].mean(),.5,places=3)
        self.assertTrue((audio[14400:24000]==0).all())
        self.assertAlmostEqual(audio[25000:30000].mean(),.3,places=3)
        self.assertTrue((audio[33600:52800]==0).all())
        self.assertAlmostEqual(audio[54000:56000].mean(),.1,places=3)
        result=self.client.get('/api/merge-actions').json()[0]
        self.assertEqual(result['status'],'completed');self.assertEqual(result['progress'],100)
        self.client.portal.call(main.remove_session,'a'*64)
        self.assertEqual(self.client.get('/api/my-voices/'+row['voice_id']+'/audio').status_code,200)
        for voice in voices:self.assertTrue((library.voice_directory(self.data,self.uid,voice['voice_id'])/'audio.wav').exists())

    def test_idempotency_and_validation(self):
        voices=self.sources();body,action=self.action(voices)
        self.assertEqual(self.client.post('/api/merge-actions',json=body).json()['action_id'],action['action_id'])
        self.assertEqual(self.client.post('/api/merge-actions',json={**body,'name':'changed'}).status_code,409)
        for patch in [{'gaps_seconds':[-1,1]},{'gaps_seconds':[31,0]},{'gaps_seconds':[0]},{'voice_ids':[voices[0]['voice_id']]},{'name':' '}]:
            self.assertEqual(self.client.post('/api/merge-actions',json={**body,**patch}).status_code,422)
        def other(request:main.Request):request.state.user={'user_id':'other'};request.state.session_key='b'*64
        main.app.dependency_overrides[main.authorize]=other
        self.assertEqual(self.client.post('/api/merge-actions',json=body).status_code,404)
        self.assertEqual(self.client.get('/api/merge-actions').json(),[])

    def test_missing_source_marks_failed_without_output(self):
        voices=self.sources();_,action=self.action(voices)
        (library.voice_directory(self.data,self.uid,voices[0]['voice_id'])/'audio.wav').unlink()
        merger.process(self.data,action)
        self.assertEqual(self.client.get('/api/merge-actions').json()[0]['status'],'failed')
        self.assertFalse(library.voice_directory(self.data,self.uid,action['action_id']).exists())
        self.assertEqual(self.client.get('/api/my-voices').json()['total'],3)

    def test_interrupted_merge_recovery(self):
        _,action=self.action(self.sources())
        path=library.voice_directory(self.data,self.uid,action['action_id']);path.mkdir()
        (path/'audio.tmp').write_bytes(b'partial')
        with auth.database() as db:db.execute("UPDATE wiavoice.merge_action SET status='running' WHERE action_id=%s",(action['action_id'],))
        merger.recover(self.data,self.uid)
        self.assertFalse(path.exists())
        self.assertEqual(self.client.get('/api/merge-actions').json()[0]['status'],'failed')
