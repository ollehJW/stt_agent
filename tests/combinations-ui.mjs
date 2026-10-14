import {chromium,expect} from '../frontend/node_modules/@playwright/test/index.mjs';
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1440,height:1080}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
let sent;
await page.route('**/api/jobs',async route=>{
 if(route.request().method()!=='POST')return route.continue();
 sent=route.request().postDataJSON();
 await route.fulfill({status:422,contentType:'application/json',body:JSON.stringify({detail:'검증용 요청입니다.'})});
});
async function submit(){sent=null;await page.getByRole('button',{name:'Voice 생성하기',exact:true}).click();await expect(page.getByRole('alert')).toContainText('검증용 요청');return sent;}
try{
 await page.goto('https://axforwork.wia.co.kr/wiavoice/',{waitUntil:'networkidle'});
 const catalog=await page.evaluate(async()=>await(await fetch('/wiavoice/api/catalog')).json());
 if(process.env.REQUIRE_ALL_PREVIEWS==='1'){
  for(const [model,details] of Object.entries(catalog.models)){
   for(const voice of catalog.voices){
    expect(Object.keys(catalog.previews[model][voice.id]).sort()).toEqual(details.emotions.map(e=>e.id).sort());
   }
  }
 }
 await expect(page.getByRole('radio')).toHaveCount(0);
 await expect(page.getByRole('checkbox')).toHaveCount(0);
 await expect(page.getByText('출력 언어',{exact:true})).toHaveCount(0);
 await page.locator('#speech-text').fill('안녕하세요. Hello.');
 for(const [model,label,emotion,emotionLabel] of [['qwen',/Qwen3 9가지/,'calm','차분함'],['fish',/Fish S2 Pro 자유로운/,'excited','신남'],['higgs',/Higgs V3 21가지/,'enthusiasm','열정 · 신남']]){
  await page.getByRole('button',{name:label}).click();
  await page.locator('.roster-item').filter({hasText:'Sohee'}).click();
  await page.getByRole('button',{name:`Sohee · ${emotionLabel} 선택`,exact:true}).click();
  await expect(page.getByRole('button',{name:`Sohee · ${emotionLabel} 선택`,exact:true})).toHaveAttribute('aria-pressed','true');
  const expected=catalog.previews?.[model]?.Sohee?.[emotion];
  if(expected){
   await page.locator('.audition-panel audio').evaluate(a=>a.play());
   const audio=page.locator('.audition-panel audio');
   await expect(audio).toHaveAttribute('src',expected);
   await expect.poll(()=>audio.evaluate(el=>el.currentTime),{timeout:15000}).toBeGreaterThan(0);
   const response=await page.request.get('https://axforwork.wia.co.kr'+expected,{headers:{Range:'bytes=0-100'}});
   expect(response.status()).toBe(206);
  }
  const body=await submit();
  expect(body.model).toBe(model);expect(body.voice).toBe('Sohee');expect(body.emotion).toBe(emotion);
  expect(body.language).toBeUndefined();expect(body.reference_language).toBeUndefined();expect(body.languages).toBeUndefined();
  await expect(page.getByRole('radio')).toHaveCount(0);
 }
 await page.locator('.custom-roster').click();
 await page.getByLabel('목소리 샘플 파일',{exact:true}).setInputFiles('samples/qwen_serena_excited.wav');
 await expect(page.getByText('첨부 완료',{exact:false})).toBeVisible();
 await expect(page.getByText('Custom Voice는 샘플 듣기를 제공하지 않습니다.',{exact:true})).toBeVisible();
 await expect(page.locator('.audition-panel audio')).toHaveCount(0);
 await expect(page.locator('.custom-section audio')).toHaveCount(0);
 const customBody=await submit();expect(customBody.voice).toBe('custom');expect(customBody.upload_id).toBeTruthy();expect(customBody.emotion).toBe('enthusiasm');
 await expect(page.locator('#reference-transcript')).toHaveCount(0);
 await page.getByRole('button',{name:/Qwen3 9가지/}).click();
 await expect(page.locator('.roster-item').filter({hasText:'Sohee'})).toHaveAttribute('aria-pressed','true');
 await page.getByRole('button',{name:'Sohee · 차분함 선택',exact:true}).click();
 await page.locator('.audition-panel audio').evaluate(a=>a.play());
 await page.locator('.roster-item').filter({hasText:'Serena'}).click();
 await expect(page.locator('.audition-panel audio')).toHaveAttribute('src',catalog.previews.qwen.Serena.calm);
 expect(await page.locator('.audition-panel audio').evaluate(el=>el.paused)).toBe(true);
 if(await page.getByRole('button',{name:'오류 닫기'}).count())await page.getByRole('button',{name:'오류 닫기'}).click();
 await page.evaluate(()=>window.scrollTo(0,0));
 await page.screenshot({path:'test-results/combinations-ui.png',fullPage:true});
 await page.screenshot({path:'test-results/combinations-viewport.png'});
 for(const width of [1200,1440,1920]){
 await page.setViewportSize({width,height:1000});
 const boxes=await Promise.all(['.voice-column','.mood-column','.listen-column'].map(s=>page.locator(s).boundingBox()));
 expect(Math.abs(boxes[0].y-boxes[1].y)).toBeLessThan(2);expect(Math.abs(boxes[1].y-boxes[2].y)).toBeLessThan(2);
 expect(boxes[0].x+boxes[0].width).toBeLessThan(boxes[1].x+1);expect(boxes[1].x+boxes[1].width).toBeLessThan(boxes[2].x+1);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(width);
 }
 await page.setViewportSize({width:1200,height:900});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(1200);
 expect(errors).toEqual([]);
 console.log('PASS: no language controls; model/voice/emotion selection; actual preview audio and ranges; payloads; Custom preview disabled; three-column desktop layout; model switching; desktop layout');
}finally{await browser.close();}
