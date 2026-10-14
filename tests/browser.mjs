import {chromium, expect} from '../frontend/node_modules/@playwright/test/index.mjs';
import {writeFileSync, readFileSync} from 'node:fs';
const base='https://axforwork.wia.co.kr/wiavoice';
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1600,height:1100},acceptDownloads:true});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
const results=[];
async function finish(key){
 for(let i=0;i<240;i++){
  const r=await page.request.get(base+'/api/jobs/'+key);const job=await r.json();
  if(job.status==='failed')throw new Error(JSON.stringify(job));
  if(job.status==='completed'){
   const audio=await page.request.get('https://axforwork.wia.co.kr'+job.audio_url);
   const bytes=await audio.body();expect(bytes.subarray(0,4).toString()).toBe('RIFF');expect(job.seconds).toBeGreaterThan(1);
   results.push({id:job.id,model:job.request.model,voice:job.request.voice,language:job.request.language,reference_language:job.request.reference_language,seconds:job.seconds});
   console.log('GENERATED',JSON.stringify(results.at(-1)));return job;
  }
  await page.waitForTimeout(2000);
 }
 throw new Error('Generation timed out');
}
async function generateAPI(spec){
 const response=await page.request.post(base+'/api/jobs',{data:spec});
 expect(response.status(),await response.text()).toBe(202);
 return finish((await response.json()).id);
}
try{
 await page.goto(base+'/',{waitUntil:'networkidle'});
 await expect(page.getByRole('heading',{name:'Voice 생성',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Voice 생성하기',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('문장을 입력');
 await page.getByRole('button',{name:'오류 닫기'}).click();
 await page.locator('.audition-panel audio').evaluate(a=>a.play());
 await page.waitForFunction(()=>document.querySelector('.audition-panel audio')?.readyState>=2);
 await page.locator('.audition-panel audio').evaluate(a=>a.pause());
 await page.getByRole('button',{name:/Higgs V3 21가지/}).click();
 await expect(page.locator('#instructions')).toHaveCount(0);
 expect(await page.locator('.mood-card').count()).toBe(22);
 await page.getByRole('button',{name:/Custom Voice 내 목소리 샘플 첨부/}).click();
 await expect(page.locator('#reference-transcript')).toHaveCount(0);
 await page.getByRole('button',{name:/Fish S2 Pro 자유로운/}).click();
 await expect(page.locator('#instructions')).toBeVisible();
 await page.screenshot({path:'test-results/wiavoice-custom.png',fullPage:true});
 await page.getByRole('button',{name:/Qwen3 9가지/}).click();
 await expect(page.getByRole('button',{name:/Custom Voice 내 목소리 샘플 첨부/})).toHaveCount(0);
 await page.locator('#speech-text').fill('안녕하세요. Welcome to WiaVoice. 당신의 이야기를 목소리로 전합니다.');
 await expect(page.getByRole('radio')).toHaveCount(0);
 await page.getByRole('button',{name:'Sohee · 차분함 선택',exact:true}).click();
 await page.locator('#instructions').fill('Speak clearly and warmly.');
 const submitted=page.waitForResponse(r=>r.url().endsWith('/api/jobs')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Voice 생성하기',exact:true}).click();
 const response=await submitted;expect(response.status()).toBe(202);const first=await response.json();
 await finish(first.id);
 await expect(page.getByRole('link',{name:'음성 다운로드'})).toBeVisible({timeout:10000});
 await page.locator('.result-audio').evaluate(a=>a.play());
 await page.waitForFunction(()=>document.querySelector('.result-audio')?.currentTime>0);
 const downloadPromise=page.waitForEvent('download');await page.getByRole('link',{name:'음성 다운로드'}).click();
 const download=await downloadPromise;await download.saveAs('test-results/browser-qwen.wav');
 await page.screenshot({path:'test-results/wiavoice-generated.png',fullPage:true});
 await page.reload();await expect(page.locator('.history-item')).toHaveCount(1);await expect(page.locator('.result-audio')).toBeVisible();
 await generateAPI({model:'qwen',text:'Welcome to WiaVoice. Turn your ideas into a voice that feels like you.',language:'en',voice:'Aiden',emotion:'happy',instructions:'Speak with clear pronunciation.'});
 const upload=await page.request.post(base+'/api/uploads',{multipart:{file:{name:'serena.wav',mimeType:'audio/wav',buffer:readFileSync('samples/qwen_serena_excited.wav')}}});
 expect(upload.status()).toBe(201);const uploaded=await upload.json();
 const custom={voice:'custom',upload_id:uploaded.id};
 for(const model of ['higgs','fish']){
  await generateAPI({model,text:'Hello. Welcome to WiaVoice. This is a new voice made for your next story.',reference_language:'en',voice:'Ryan',emotion:model==='higgs'?'affection':'calm'});
  await generateAPI({model,text:'안녕하세요. 위아보이스입니다. 원하는 목소리로 새로운 이야기를 만들어 보세요.',...custom,emotion:model==='higgs'?'enthusiasm':'excited',instructions:model==='fish'?'clear pronunciation':''});
 }
 expect(errors).toEqual([]);
 writeFileSync('test-results/live-generation.json',JSON.stringify({results,browserErrors:errors},null,2));
 console.log('PASS: model UI, preview, custom upload, real generation, playback, download, history reload');
}finally{await browser.close();}
