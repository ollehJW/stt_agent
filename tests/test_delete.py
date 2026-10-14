from contextlib import contextmanager
from unittest.mock import patch
from uuid import uuid4
from backend import main,library,auth,merger
import test_library

class DeleteTest(test_library.LibraryTest):
    def saved(self):
        job=self.completed_job()
        return library.save_voice(self.data,self.uid,job,'삭제 테스트',main.job_path(job,'outputs','wav').read_bytes())

    def test_delete_files_row_and_foreign_access(self):
        voice=self.saved();path=library.voice_directory(self.data,self.uid,voice['voice_id'])
        with self.assertRaises(main.HTTPException) as error:library.delete_voice(self.data,'other',voice['voice_id'])
        self.assertEqual(error.exception.status_code,404);self.assertTrue(path.exists())
        r=self.client.delete('/api/my-voices/'+voice['voice_id']);self.assertEqual(r.status_code,200,r.text)
        self.assertFalse(path.exists());self.assertEqual(self.client.get('/api/my-voices').json()['total'],0)
        self.assertEqual(self.client.get(voice['audio_url'].replace('/wiavoice','')).status_code,404)
        self.assertEqual(self.client.delete('/api/my-voices/'+voice['voice_id']).status_code,404)

    def test_merge_in_use_and_output_history(self):
        a=self.saved();b=self.saved()
        spec=merger.MergeRequest(name='merged',request_id=uuid4().hex,voice_ids=[a['voice_id'],b['voice_id']],gaps_seconds=[0])
        action=merger.submit(self.data,self.uid,spec)
        self.assertEqual(self.client.delete('/api/my-voices/'+a['voice_id']).status_code,409)
        with auth.database() as db:row=db.execute('SELECT * FROM wiavoice.merge_action WHERE action_id=%s',(action['action_id'],)).fetchone()
        merger.process(self.data,row)
        self.assertEqual(self.client.delete('/api/my-voices/'+a['voice_id']).status_code,200)
        self.assertTrue((library.voice_directory(self.data,self.uid,action['action_id'])/'audio.wav').exists())
        self.assertEqual(self.client.delete('/api/my-voices/'+action['action_id']).status_code,200)
        history=self.client.get('/api/merge-actions').json()[0]
        self.assertEqual(history['status'],'completed');self.assertIsNone(history['result_voice_id'])

    def test_failed_transaction_restores_audio(self):
        voice=self.saved();path=library.voice_directory(self.data,self.uid,voice['voice_id'])
        @contextmanager
        def failure():
            with auth.database() as db:
                yield db
                raise RuntimeError('simulated commit failure')
        with patch.object(library,'database',failure):
            with self.assertRaises(RuntimeError):library.delete_voice(self.data,self.uid,voice['voice_id'])
        self.assertTrue((path/'audio.wav').exists())
        self.assertEqual(self.client.get('/api/my-voices').json()['total'],1)

    def test_crash_recovery_restores_or_removes(self):
        voice=self.saved();path=library.voice_directory(self.data,self.uid,voice['voice_id'])
        parked=path.with_name('.deleting-'+voice['voice_id']+'-'+uuid4().hex);path.rename(parked)
        library.recover_deletions(self.data)
        self.assertTrue(path.exists());self.assertFalse(parked.exists())
        path.rename(parked)
        with auth.database() as db:db.execute('DELETE FROM wiavoice.voices WHERE voice_id=%s',(voice['voice_id'],))
        library.recover_deletions(self.data)
        self.assertFalse(parked.exists());self.assertFalse(path.exists())

    def test_six_item_pagination(self):
        for _ in range(7):self.saved()
        first=self.client.get('/api/my-voices').json();second=self.client.get('/api/my-voices?limit=6&offset=6').json()
        self.assertEqual(first['total'],7);self.assertEqual(len(first['items']),6);self.assertEqual(len(second['items']),1)
        self.assertFalse({r['voice_id'] for r in first['items']} & {r['voice_id'] for r in second['items']})
