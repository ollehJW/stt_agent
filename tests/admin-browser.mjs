// Isolated UI simulation: no administrator role changes or production mutations.
import {chromium,expect} from '../frontend/node_modules/@playwright/test/index.mjs';
import assert from 'node:assert/strict';
const browser=await chromium.launch({args:['--no-sandbox']});
try{
 const page=await browser.newPage({viewport:{width:1600,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const stamp=new Date().toISOString(),user={user_id:'ui-test',is_admin:true,full_name:'관리자 검증',team_name:'DX추진랩',employee_id:'TEST',role_name:'매니저',session_id:'test'};
 const generation={...user,job_id:'job',model:'higgs',voice:'Sohee',emotion:'neutral',purpose:'generation',text:'안녕하세요. 생성 기록의 입력 멘트입니다.\n두 번째 문장입니다.',character_count:44,status:'completed',created_at:stamp,started_at:stamp,completed_at:stamp,audio_seconds:6.05,generation_seconds:1.3,trimmed_seconds:75.59};
 const saved={...user,voice_id:'saved',name:'안내 목소리',model:'higgs',speaker:'Sohee',emotion:'neutral',created_at:stamp,duration_seconds:6.05,text:'안녕하세요. 새로운 이야기를 시작합니다.'};
 const merge={...user,action_id:'merge',name:'안내 문장 병합',status:'failed',created_at:stamp,error_message:'검증용 실패 기록',source_count:2,input_voices:[{name:'첫 문장'},{name:'마지막 문장'}],gaps_seconds:[.5]};
 let market={...user,voice_id:'market',name:'뉴스 앵커',description:'또렷한 안내 목소리',gender:'male',download_count:12,favorites:4,created_at:stamp,updated_at:stamp,reference_seconds:20,sample_seconds:6.05,sample_text:'안녕하세요. 오늘도 만나서 반갑습니다.',consent_at:stamp,consent_text:'개인의 동의를 받았음을 서약합니다.',consent_version:'v1',hidden_at:null,deleted_at:null};let history=[];
 const wave=Buffer.alloc(44+24000*2);wave.write('RIFF');wave.writeUInt32LE(wave.length-8,4);wave.write('WAVEfmt ',8);wave.writeUInt32LE(16,16);wave.writeUInt16LE(1,20);wave.writeUInt16LE(1,22);wave.writeUInt32LE(24000,24);wave.writeUInt32LE(48000,28);wave.writeUInt16LE(2,32);wave.writeUInt16LE(16,34);wave.write('data',36);wave.writeUInt32LE(wave.length-44,40);
 await page.route('**/wiavoice/api/**',async route=>{
  const url=new URL(route.request().url()),path=url.pathname;let data={};
  if(path.endsWith('/auth/me'))data=user;
  else if(path.endsWith('/options'))data={users:[user],tracking_started_at:stamp};
  else if(path.endsWith('/operations'))data={summary:{total:18,completed:16,failed:1,cancelled:1,pending:0,users:5,audio_seconds:153.4,average_seconds:2.8},daily:[{day:stamp.slice(0,10),total:18,completed:16,failed:1}],models:[{model:'higgs',total:12,completed:11,average_seconds:2.4},{model:'qwen',total:6,completed:5,average_seconds:3.2}],activity:[{...user,total:18,completed:16,audio_seconds:153.4,last_used:stamp}],errors:[{...generation,job_id:'failed',error_message:'생성 오류 검증'}],snapshot:{saved:8,published:4,hidden:1,downloads:28},period_downloads:12,live:{state:'idle',model:null,queued:0}};
  else if(path.endsWith('/voices')){const kind=url.searchParams.get('kind');data={items:[kind==='saved'?saved:kind==='merge'?merge:generation],total:1};}
  else if(path.includes('/voices/'))data=path.includes('/generation/')?generation:path.includes('/saved/')?saved:merge;
  else if(path.endsWith('/actions')){const body=route.request().postDataJSON(),before={...market};if(body.action==='edit')market={...market,name:body.name,description:body.description,gender:body.gender};else if(body.action==='hide')market.hidden_at=stamp;else if(body.action==='publish')market.hidden_at=null;else if(body.action==='delete')market.deleted_at=stamp;history.unshift({audit_id:history.length+1,action:body.action,reason:body.reason,before_state:before,after_state:{...market},created_at:stamp,actor_name:user.full_name});data={ok:true};}
  else if(path.endsWith('/marketplace'))data={items:[market],total:1};
  else if(path.endsWith('/sample')||path.endsWith('/audio')){await route.fulfill({contentType:'audio/wav',body:wave});return;}
  else if(path.includes('/marketplace/'))data={voice:market,history};
  await route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
 });
 await page.goto((process.env.WIAVOICE_UI_ORIGIN||'http://127.0.0.1:11005')+'/wiavoice/');
 await expect(page.getByRole('navigation',{name:'관리자 메뉴'}).getByRole('button')).toHaveCount(3);
 await expect(page.locator('.va-stat')).toHaveCount(4);await expect(page.getByRole('heading',{name:'운영 관리',exact:true})).toBeVisible();
 await page.screenshot({path:'test-results/admin-operations.png',fullPage:true});
 await page.getByRole('button',{name:'Voice 관리',exact:true}).click();await expect(page.getByRole('tab')).toHaveCount(3);
 await page.getByRole('button',{name:'Sohee 상세'}).click();await expect(page.getByRole('dialog')).toContainText('75.59초');await expect(page.getByRole('dialog')).toContainText(generation.text);await expect(page.getByRole('dialog').locator('audio')).toHaveCount(0);await page.getByRole('button',{name:'팝업 닫기'}).click();
 await page.getByRole('tab',{name:'My Voice',exact:true}).click();await page.getByRole('button',{name:'안내 목소리 상세'}).click();await expect(page.getByRole('dialog')).toContainText(saved.text);await page.getByRole('button',{name:'음성 확인',exact:true}).click();await expect(page.getByRole('dialog').locator('audio')).toHaveCount(1);await page.getByRole('button',{name:'팝업 닫기'}).click();
 await page.getByRole('tab',{name:'병합 작업'}).click();await page.getByRole('button',{name:'안내 문장 병합 상세'}).click();await expect(page.getByRole('dialog')).toContainText('검증용 실패 기록');await expect(page.getByRole('dialog')).toContainText('다음 음성까지 0.5초');await page.getByRole('button',{name:'팝업 닫기'}).click();
 await page.screenshot({path:'test-results/admin-voices.png',fullPage:true});
 await page.getByRole('button',{name:'Market Place 관리',exact:true}).click();await page.getByRole('button',{name:'뉴스 앵커 상세'}).click();await expect(page.getByRole('dialog')).toContainText('개인의 동의를 받았음을 서약합니다.');await page.screenshot({path:'test-results/admin-consent.png',fullPage:true});await page.getByRole('button',{name:'팝업 닫기'}).click();
 await page.getByRole('button',{name:'뉴스 앵커 수정'}).click();await page.getByLabel('목소리 이름',{exact:true}).fill('안내 앵커');await expect(page.getByRole('button',{name:'정보 수정',exact:true})).toBeDisabled();await page.getByLabel('처리 사유').fill('표기 수정 검증');await page.getByRole('button',{name:'정보 수정',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);
 for(const action of ['공개 중지','재공개']){await page.getByRole('button',{name:'안내 앵커 '+action,exact:true}).click();await page.getByLabel('처리 사유').fill(action+' 검증');await page.getByRole('dialog').getByRole('button',{name:action,exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);}
 await page.getByRole('button',{name:'안내 앵커 상세'}).click();await expect(page.locator('.va-audit li')).toHaveCount(3);await page.getByRole('button',{name:'팝업 닫기'}).click();
 await page.setViewportSize({width:1200,height:900});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=1200));await page.screenshot({path:'test-results/admin-marketplace-1200.png',fullPage:true});
 await page.getByRole('button',{name:'안내 앵커 삭제'}).click();await page.getByRole('button',{name:'취소',exact:true}).click();assert.equal(market.deleted_at,null);await page.getByRole('button',{name:'안내 앵커 삭제'}).click();await page.getByLabel('처리 사유').fill('삭제 검증');await page.getByRole('dialog').getByRole('button',{name:'삭제',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);await expect(page.locator('.va-table')).toContainText('삭제됨');assert.deepEqual(errors,[]);
 console.log('Mock admin UI: three menus, Voice tabs/details/audio, consent, required reasons, edit/hide/publish/delete/cancel, history and 1200px layout verified');
}finally{await browser.close();}
