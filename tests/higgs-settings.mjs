import {chromium,expect} from '../frontend/node_modules/@playwright/test/index.mjs';
import {writeFileSync} from 'node:fs';
const b=await chromium.launch({headless:true,args:['--no-sandbox']});
const p=await b.newPage({viewport:{width:1440,height:1000}});const errors=[];p.on('pageerror',e=>errors.push(e.message));
try{
 await p.goto('https://axforwork.wia.co.kr/wiavoice/',{waitUntil:'networkidle'});
 await expect(p.locator('.higgs-settings')).toHaveCount(0);
 await p.getByRole('button',{name:/Higgs V3 21가지/}).click();
 await expect(p.locator('#instructions')).toHaveCount(0);
 await expect(p.locator('.setting-card')).toHaveCount(4);
 await expect(p.locator('.setting-option.selected')).toHaveCount(4);
 await p.getByRole('group',{name:'말하기 속도',exact:true}).getByRole('button',{name:'빠르게',exact:true}).click();
 await p.getByRole('button',{name:'기본값으로 초기화',exact:true}).click();
 await expect(p.getByRole('group',{name:'말하기 속도',exact:true}).getByRole('button',{name:'기본',exact:true})).toHaveAttribute('aria-pressed','true');
 for(const [group,label] of [['말하기 속도','느리게'],['음높이','낮게'],['표현 강도','강하게'],['발성 스타일','속삭임']])await p.getByRole('group',{name:group,exact:true}).getByRole('button',{name:label,exact:true}).click();
 await p.locator('#speech-text').fill('안녕하세요. 위아보이스의 새로운 음성 설정을 소개합니다. 편안하게 들어 주세요.');
 let sent;
 await p.route('**/api/jobs',async r=>{if(r.request().method()!=='POST')return r.continue();sent=r.request().postDataJSON();await r.fulfill({status:422,contentType:'application/json',body:JSON.stringify({detail:'검증용 요청'})});});
 await p.getByRole('button',{name:/Fish S2 Pro 자유로운/}).click();await expect(p.locator('.higgs-settings')).toHaveCount(0);
 await p.getByRole('button',{name:'Voice 생성하기',exact:true}).click();await expect(p.getByRole('alert')).toContainText('검증용 요청');expect(sent.higgs_options).toBeUndefined();
 await p.getByRole('button',{name:/Higgs V3 21가지/}).click();
 await p.unroute('**/api/jobs');
 for(const width of [1200,1440]){await p.setViewportSize({width,height:1000});expect(await p.evaluate(()=>document.documentElement.scrollWidth)).toBe(width);}
 await p.locator('.higgs-settings').scrollIntoViewIfNeeded();await p.screenshot({path:'test-results/higgs-settings.png'});
 const responsePromise=p.waitForResponse(r=>r.url().endsWith('/api/jobs')&&r.request().method()==='POST');
 await p.getByRole('button',{name:'Voice 생성하기',exact:true}).click();
 const response=await responsePromise;expect(response.status()).toBe(202);const job=await response.json();
 expect(job.request.higgs_options).toEqual({speed:'slow',pitch:'low',expression:'high',style:'whispering'});
 console.log('SUBMITTED',job.id);
 await expect(p.getByRole('link',{name:'음성 다운로드'})).toBeVisible({timeout:300000});
 await p.locator('.result-audio').evaluate(a=>a.play());await expect.poll(()=>p.locator('.result-audio').evaluate(a=>a.currentTime),{timeout:15000}).toBeGreaterThan(0);
 const finished=await(await p.request.get('https://axforwork.wia.co.kr/wiavoice/api/jobs/'+job.id)).json();
 const audio=await p.request.get('https://axforwork.wia.co.kr'+finished.audio_url);expect((await audio.body()).subarray(0,4).toString()).toBe('RIFF');
 writeFileSync('test-results/higgs-settings-live.wav',await audio.body());writeFileSync('test-results/higgs-settings-live.json',JSON.stringify(finished,null,2));
 await expect(p.locator('.result-settings span')).toHaveCount(4);expect(errors).toEqual([]);
 console.log('PASS: Higgs-only settings, defaults/reset, validated payload, real generation, playback, result settings; seconds='+finished.seconds);
}finally{await b.close();}
