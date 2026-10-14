import os
from pathlib import Path
import tempfile
import unittest
from backend.upload_cleanup import cleanup_uploads, protected_uploads, TTL_SECONDS

class UploadCleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.data=Path(self.tmp.name);(self.data/'uploads').mkdir();self.now=2000000000
    def pair(self,key,age,suffixes=('.wav','.json')):
        for suffix in suffixes:
            p=self.data/'uploads'/(key+suffix);p.write_bytes(b'test');os.utime(p,(self.now-age,self.now-age))
    def test_expiration_boundary_and_orphans(self):
        self.pair('a'*32,TTL_SECONDS);self.pair('b'*32,TTL_SECONDS-1)
        self.pair('c'*32,TTL_SECONDS+1,('.wav',));self.pair('d'*32,TTL_SECONDS+1,('.json',))
        self.assertEqual(cleanup_uploads(self.data,now=self.now),3)
        self.assertEqual(sorted(p.name for p in (self.data/'uploads').iterdir()),['b'*32+'.json','b'*32+'.wav'])
    def test_active_and_revoked_inflight_jobs_are_protected(self):
        jobs=[]
        for letter,status in zip('abcde',['queued','loading','generating','completed','failed']):
            self.pair(letter*32,TTL_SECONDS+100)
            jobs.append({'status':status,'request':{'voice':'custom','upload_id':letter*32}})
        self.pair('f'*32,TTL_SECONDS+100)
        protected=protected_uploads(jobs,{'f'*32}) # revoked session no longer in jobs
        self.assertEqual(cleanup_uploads(self.data,protected,now=self.now),2)
        for letter in 'abcf':self.assertTrue((self.data/'uploads'/(letter*32+'.wav')).exists())
        self.assertEqual(cleanup_uploads(self.data,now=self.now),4)
    def test_newer_pair_member_and_durable_files_preserved(self):
        self.pair('a'*32,TTL_SECONDS+50)
        p=self.data/'uploads'/('a'*32+'.json');os.utime(p,(self.now,self.now))
        for folder in ['workspace','marketplace','voices','sessions']:
            p=self.data/folder/('b'*32+'.wav');p.parent.mkdir();p.write_bytes(b'keep');os.utime(p,(1,1))
        self.assertEqual(cleanup_uploads(self.data,now=self.now),0)
        for folder in ['workspace','marketplace','voices','sessions']:self.assertTrue((self.data/folder/('b'*32+'.wav')).exists())
    def test_symlinks_and_unrecognized_files_untouched(self):
        outside=self.data/'saved.wav';outside.write_bytes(b'keep');os.utime(outside,(1,1))
        (self.data/'uploads'/('a'*32+'.wav')).symlink_to(outside)
        self.pair('a'*32,TTL_SECONDS+50,('.json',))
        (self.data/'uploads'/'unknown.wav').write_bytes(b'keep')
        self.assertEqual(cleanup_uploads(self.data,now=self.now),0)
        self.assertEqual(outside.read_bytes(),b'keep')

if __name__=='__main__':unittest.main()
