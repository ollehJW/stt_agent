import io
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient
from backend import main

def wav(seconds=4, format='WAV'):
    b=io.BytesIO()
    sf.write(b, .1*np.sin(np.arange(24000*seconds)*.05), 24000, format=format)
    return b.getvalue()

class FakeEngine:
    model=None
    state='idle'
    last_used=0
    async def ensure(self, model): self.model=model
    async def generate(self, payload): return wav()
    async def stop(self): self.model=None

class APITest(unittest.TestCase):
    def setUp(self):
        def user(request: main.Request):
            request.state.user = {'user_id': 'test-user'}
            request.state.session_key = 'a'*64
        main.app.dependency_overrides[main.authorize] = user
        self.addCleanup(main.app.dependency_overrides.clear)
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.data=Path(temp.name)
        self.enterContext(patch.object(main,'DATA',self.data))
        self.enterContext(patch.object(main,'Engine',lambda data: FakeEngine()))
        self.enterContext(patch.object(main,'active_session_keys',lambda keys: set(keys)))
        async def idle_merge(data,stop): await stop.wait()
        self.enterContext(patch.object(main.merger,'worker',idle_merge))
        self.enterContext(patch.object(main.telemetry,'worker',idle_merge))
        self.client=self.enterContext(TestClient(main.app))
        for lang in ['ko','en']:
            (self.data/'voices'/f'Sohee_{lang}.wav').write_bytes(wav())

    def test_model_mapping_and_validation(self):
        base=dict(text='안녕하세요.',model='qwen',languages=['ko'],instructions='Speak gently.',emotion='calm')
        payload=main.make_payload(main.Generation(**base))
        self.assertEqual(payload['language'],'Auto')
        self.assertIn('Speak gently.',payload['instructions'])
        base['languages']=['ko','en']
        self.assertEqual(main.make_payload(main.Generation(**base))['language'],'Auto')
        base.update(model='fish',languages=['en'],instructions='broadcast tone',emotion='excited')
        payload=main.make_payload(main.Generation(**base))
        self.assertTrue(payload['input'].startswith('[excited][broadcast tone]'))
        self.assertTrue(payload['references'][0]['audio_path'].endswith('_en.wav'))
        base.update(model='higgs',instructions='',emotion='enthusiasm')
        self.assertTrue(main.make_payload(main.Generation(**base))['input'].startswith('<|emotion:enthusiasm|>'))
        for changes in [{'languages':[]},{'text':' '},{'voice':'unknown'},{'model':'higgs','instructions':'unsupported'},{'model':'higgs','emotion':'calm'},{'voice':'custom'}]:
            request={**dict(text='안녕하세요.',model='qwen',languages=['ko']),**changes}
            self.assertEqual(self.client.post('/api/jobs',json=request).status_code,422)

    def test_separate_language_fields(self):
        for language, expected in [('auto','Auto'),('ko','Auto'),('en','Auto')]:
            spec=main.Generation(text='Hello',model='qwen',language=language)
            self.assertEqual(main.make_payload(spec)['language'],expected)
        for model in ['fish','higgs']:
            spec=main.Generation(text='Hello',model=model,language='ko',reference_language='en')
            payload=main.make_payload(spec)
            self.assertNotIn('language',payload)
            self.assertTrue(payload['references'][0]['audio_path'].endswith('_en.wav'))
        spec=main.Generation(text='Hello',model='qwen',languages=['ko','en'])
        self.assertEqual(spec.language,'auto')
        self.assertNotIn('languages',spec.model_dump())
        for field in ['language','reference_language']:
            result=self.client.post('/api/jobs',json={'text':'Hello','model':'qwen',field:'invalid'})
            self.assertEqual(result.status_code,422)

    def test_combination_previews(self):
        from backend.previews import preview_key
        key=preview_key('fish','Sohee','excited')
        (self.data/'previews'/f'{key}.wav').write_bytes(wav())
        catalog=self.client.get('/api/catalog').json()
        url=catalog['previews']['fish']['Sohee']['excited']
        self.assertNotIn('calm',catalog['previews']['fish']['Sohee'])
        self.assertNotIn('qwen',catalog['previews'])
        self.assertTrue(self.client.get(url.removeprefix('/wiavoice')).content.startswith(b'RIFF'))
        self.assertEqual(self.client.get('/api/previews/'+'a'*24).status_code,404)
        self.assertEqual(self.client.get('/api/previews/invalid').status_code,404)

    def test_higgs_delivery_controls(self):
        base=dict(text='안녕하세요. Welcome!\n함께해요.', model='higgs')
        self.assertEqual(main.make_payload(main.Generation(**base,higgs_options={}))['input'],base['text'])
        options=dict(speed='slow',pitch='low',expression='high',style='whispering')
        payload=main.make_payload(main.Generation(**base,emotion='affection',higgs_options=options))
        prefix='<|emotion:affection|><|prosody:speed_slow|><|prosody:pitch_low|><|prosody:expressive_high|><|style:whispering|>'
        self.assertEqual(payload['input'],prefix+'안녕하세요. '+prefix+'Welcome!\n'+prefix+'함께해요.')
        for field,values in {'speed':['very_slow','slow','fast','very_fast'],'pitch':['low','high'],'expression':['low','high'],'style':['whispering','shouting','singing']}.items():
            for value in values:
                spec=main.Generation(text='Hello',model='higgs',higgs_options={field:value})
                category='style' if field=='style' else 'prosody'
                tag=value if field=='style' else ('expressive' if field=='expression' else field)+'_'+value
                self.assertEqual(main.make_payload(spec)['input'],f'<|{category}:{tag}|>Hello')
        for options in [{'speed':'1.2'}, {'style':'invalid'}, {'unknown':'high'}]:
            self.assertEqual(self.client.post('/api/jobs',json={**base,'higgs_options':options}).status_code,422)
        for model in ['qwen','fish']:
            self.assertEqual(self.client.post('/api/jobs',json={**base,'model':model,'higgs_options':{'speed':'slow'}}).status_code,422)

    def test_removed_effects_are_not_applied(self):
        base=dict(text='안녕하세요.',model='higgs',higgs_options={'speed':'slow'})
        response=self.client.post('/api/jobs',json={**base,'higgs_effects':[dict(sentence=0,word=0,kind='crying')]})
        self.assertEqual(response.status_code,422)
        self.assertIn('쉼·소리 연출 기능이 제거',response.text)
        spec=main.Generation(**base,higgs_effects=[])
        self.assertNotIn('higgs_effects',spec.model_dump())
        self.assertEqual(main.make_payload(spec)['input'],'<|prosody:speed_slow|>안녕하세요.')
        self.assertNotIn('effects',self.client.get('/api/catalog').json()['models']['higgs'])

    def test_audio_formats_and_invalid_files(self):
        for fmt in ['WAV','FLAC','OGG','MP3']:
            response=self.client.post('/api/uploads',files={'file':('sample.'+fmt.lower(),wav(format=fmt),'application/octet-stream')})
            self.assertEqual(response.status_code,201,response.text)
            normalized=self.data/'uploads'/f'{response.json()["id"]}.wav'
            self.assertEqual(sf.info(normalized).channels,1)
        for name,raw in [('test.m4a',b'x'),('test.wav',b'garbage'),('test.wav',wav(seconds=1))]:
            self.assertEqual(self.client.post('/api/uploads',files={'file':(name,raw)}).status_code,400)

    def test_custom_upload_job_and_download(self):
        upload=self.client.post('/api/uploads',files={'file':('voice.wav',wav())}).json()
        spec=dict(text='안녕하세요.',languages=['ko'],model='fish',voice='custom',upload_id=upload['id'])
        payload=main.make_payload(main.Generation(**spec))
        self.assertEqual(payload['references'][0]['text'],'')
        result=self.client.post('/api/jobs',json=spec)
        self.assertEqual(result.status_code,202,result.text)
        key=result.json()['id']
        for _ in range(100):
            job=self.client.get('/api/jobs/'+key).json()
            if job['status'] in ['completed','failed']:break
            time.sleep(.01)
        self.assertEqual(job['status'],'completed',job)
        response=self.client.get('/api/jobs/'+key+'/audio?download=true')
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.content.startswith(b'RIFF'))
        self.assertIn('attachment',response.headers['content-disposition'])
        self.assertEqual(self.client.get('/api/jobs/unknown').status_code,404)
        self.assertEqual(self.client.get('/api/uploads/bad/audio').status_code,404)
        spec['upload_id']='a'*32
        self.assertEqual(self.client.post('/api/jobs',json=spec).status_code,404)

if __name__=='__main__': unittest.main()
