import Introduction from './Introduction';
import React, {useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {AudioLines, Mic2, ChevronRight, ArrowLeft, Headphones, Sparkles, FileText, SlidersHorizontal, Lightbulb, Upload, Check, Download, LoaderCircle, X, CircleAlert, Volume2, Clock3, FolderHeart, BookmarkPlus, ArrowRight, Store} from 'lucide-react';
import './styles.css';
import MyVoice, {SaveVoiceDialog} from './MyVoice';
import MarketPlace from './MarketPlace';
import AXAccount from './AXAccount';
import AdminWorkspace from './AdminWorkspace';
const currentPage=()=>window.location.hash==='#marketplace'?'marketplace':window.location.hash==='#my-voice'?'library':'create';

const API='/wiavoice/api';
const LOGIN='https://axforwork.wia.co.kr/login?next='+encodeURIComponent('/wiavoice/agent'+window.location.search+window.location.hash);
async function request(path,options={}){
  const {responseType,...fetchOptions}=options;
  const response=await fetch(API+path,fetchOptions);
  if(response.status===401||(response.status===403&&path==='/auth/me')){window.location.replace(LOGIN);throw new Error('통합 로그인을 확인해 주세요.');}
  if(response.ok&&responseType==='blob')return response.blob();
  const data=await response.json().catch(()=>({}));
  if(!response.ok){const d=data.detail;throw new Error(typeof d==='string'?d:Array.isArray(d)?d.map(x=>x.msg.replace('Value error, ','')).join(' '):'서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.');}
  return data;
}
const busyStatus=['queued','loading','generating'];
const DEFAULT_HIGGS={speed:'default',pitch:'default',expression:'default',style:'default'};

function App({user}){
  const [loggingOut,setLoggingOut]=useState(false),[logoutError,setLogoutError]=useState('');
  async function logout(){
    if(loggingOut)return;setLoggingOut(true);setLogoutError('');
    try{await request('/auth/logout',{method:'POST'});window.location.replace(LOGIN);}
    catch(e){setLogoutError(e.message);setLoggingOut(false);}
  }
  const [page,setPage]=useState(currentPage);
  const [saveJob,setSaveJob]=useState(null),[saved,setSaved]=useState({}),[notice,setNotice]=useState('');
  useEffect(()=>{const sync=()=>setPage(currentPage());window.addEventListener('hashchange',sync);return()=>window.removeEventListener('hashchange',sync);},[]);
  function navigate(next){document.querySelectorAll('audio').forEach(audio=>audio.pause());window.location.hash=next==='marketplace'?'marketplace':next==='library'?'my-voice':'create';setPage(next);}

  const [catalog,setCatalog]=useState(null),[catalogError,setCatalogError]=useState('');
  const [model,setModel]=useState('qwen');
  const [higgsOptions,setHiggsOptions]=useState({...DEFAULT_HIGGS});
  const [text,setText]=useState(''),[voice,setVoice]=useState('Sohee'),[emotion,setEmotion]=useState('neutral'),[instructions,setInstructions]=useState('');
  const [upload,setUpload]=useState(null),[uploading,setUploading]=useState(false),[dragging,setDragging]=useState(false);
  const [error,setError]=useState(''),[submitting,setSubmitting]=useState(false),[job,setJob]=useState(null),[history,setHistory]=useState([]),[pollError,setPollError]=useState('');
  const sampleAudio=useRef(null),fileInput=useRef(null),moodGrid=useRef(null);
  const active=catalog?.models[model];
  const busy=submitting||busyStatus.includes(job?.status);
  const sampleUrl=voice==='custom'?null:catalog?.previews?.[model]?.[voice]?.[emotion];

  async function loadCatalog(){setCatalogError('');try{setCatalog(await request('/catalog'));}catch(e){setCatalogError(e.message);}}
  useEffect(()=>{loadCatalog();request('/jobs').then(items=>{
    const valid=items.filter(Boolean);setHistory(valid);setJob(valid.find(x=>busyStatus.includes(x.status))||valid[0]||null);
  }).catch(e=>setError(e.message));},[]);
  useEffect(()=>{
    if(!job||!busyStatus.includes(job.status))return;
    let disposed=false;
    const timer=setInterval(async()=>{try{const updated=await request('/jobs/'+job.id);if(!disposed){setJob(updated);setHistory(items=>items.map(x=>x.id===updated.id?updated:x));setPollError('');}}catch{if(!disposed)setPollError('연결을 다시 확인하고 있습니다. 새로고침해도 작업은 계속됩니다.');}},2000);
    return()=>{disposed=true;clearInterval(timer);};
  },[job?.id,job?.status]);
  useEffect(()=>{
    if(!catalog)return;
    const count=Object.values(catalog.previews||{}).reduce((n,voices)=>n+Object.values(voices).reduce((a,emotions)=>a+Object.keys(emotions).length,0),0);
    const expected=catalog.voices.length*Object.values(catalog.models).reduce((n,m)=>n+m.emotions.length,0);
    if(count>=expected)return;
    const timer=setInterval(()=>request('/catalog').then(setCatalog).catch(()=>{}),30000);
    return()=>clearInterval(timer);
  },[catalog]);
  function stopPreview(){sampleAudio.current?.pause();}
  function changeModel(next){stopPreview();if(moodGrid.current)moodGrid.current.scrollTop=0;setModel(next);setEmotion('neutral');setInstructions('');setError('');if(next==='qwen'&&voice==='custom')setVoice('Sohee');}
  function chooseVoice(next){stopPreview();setVoice(next);}
  function chooseEmotion(next){if(next!==emotion)stopPreview();setEmotion(next);}
  async function attach(file){
    if(!file)return;
    stopPreview();setError('');setUpload(null);
    if(!/\.(wav|mp3|flac|ogg)$/i.test(file.name)){setError('WAV, MP3, FLAC, OGG 파일을 첨부해 주세요.');return;}
    if(file.size>20*1024*1024){setError('파일은 최대 20MB까지 첨부할 수 있습니다.');return;}
    setUploading(true);const data=new FormData();data.append('file',file);
    try{setUpload(await request('/uploads',{method:'POST',body:data}));}catch(e){setError(e.message);}finally{setUploading(false);if(fileInput.current)fileInput.current.value='';}
  }
  async function generate(e){
    e.preventDefault();setError('');
    if(!text.trim()){setError('음성으로 만들 문장을 입력해 주세요.');return;}
    if(voice==='custom'&&!upload){setError('목소리 샘플을 첨부해 주세요.');return;}
    setSubmitting(true);sampleAudio.current?.pause();
    try{
      const next=await request('/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,model,voice,emotion,...(model==='higgs'?{higgs_options:higgsOptions}:{}),instructions:active.instructions?instructions:'',upload_id:voice==='custom'?upload.id:null})});
      setJob(next);setHistory(items=>[next,...items].slice(0,20));
    }catch(e){setError(e.message);}finally{setSubmitting(false);}
  }
  const selectedVoice=catalog?.voices.find(x=>x.id===voice);
  const voiceLabel=voice==='custom'?'Custom Voice':selectedVoice?.label;
  const selectedEmotion=active?.emotions.find(x=>x.id===emotion);
  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="/wiavoice/"><AudioLines size={35}/><div>WiaVoice<small>AI VOICE STUDIO</small></div></a>
      <div className="workspace-label">WORKSPACE</div>
      <nav aria-label="메인 메뉴"><button className={page==='create'?'active':''} aria-current={page==='create'?'page':undefined} onClick={()=>navigate('create')}><Mic2 size={18}/>Voice 생성<ChevronRight size={16}/></button><button className={page==='library'?'active':''} aria-current={page==='library'?'page':undefined} onClick={()=>navigate('library')}><FolderHeart size={18}/>My Voice<ChevronRight size={16}/></button><button className={page==='marketplace'?'active':''} aria-current={page==='marketplace'?'page':undefined} onClick={()=>navigate('marketplace')}><Store size={18}/>Market Place<ChevronRight size={16}/></button></nav>
      <AXAccount name={user.full_name} team={user.team_name} admin={false} onLogout={logout} disabled={loggingOut}/>
      {logoutError&&<p className="account-error" role="alert">{logoutError}</p>}
    </aside>
    <div className="main-shell"><header className="topbar"><div><a href="/">AX for Works</a><ChevronRight size={13}/><span>WiaVoice</span><ChevronRight size={13}/><strong>{page==='marketplace'?'Market Place':page==='library'?'My Voice':'Voice 생성'}</strong></div><a className="return-link" href="/"><ArrowLeft size={14}/>AX for Works로 돌아가기</a></header>
      <main><div className="page-heading"><div><div className="eyebrow">AI VOICE STUDIO</div><h1>{page==='marketplace'?'Market Place':page==='library'?'My Voice':'Voice 생성'}</h1><p>{page==='marketplace'?'목소리를 발견하고, 나누고, 새로운 이야기에 담아 보세요.':page==='library'?'마음에 드는 목소리를 저장하고, 언제든 다시 꺼내 들어 보세요.':'문장을 입력하고, 목소리와 감정을 골라 나만의 음성을 만들어 보세요.'}</p></div><div className="heading-note"><Headphones size={24}/><div>하나의 문장, 다양한 목소리<small>한국어 · English</small></div></div></div>
      {page==='marketplace'?<MarketPlace request={request}/>:page==='library'?<MyVoice request={request} catalog={catalog} onCreate={()=>navigate('create')} onDeleted={item=>{setSaved(values=>Object.fromEntries(Object.entries(values).filter(([,id])=>id!==item.voice_id)));setNotice('');}}/>:<>
      {catalogError?<div className="error" role="alert"><CircleAlert size={18}/>{catalogError}<button className="button" onClick={loadCatalog}>다시 연결</button></div>:!catalog?<div className="loading"><LoaderCircle className="spin"/>목소리 옵션을 불러오는 중입니다.</div>:<div className="workspace-grid">
        <form onSubmit={generate} className="form-column"><fieldset disabled={busy}>
          <section className="panel"><div className="section-title"><div className="section-label"><span className="tile-icon"><FileText size={20}/></span><div><h2>어떤 이야기를 들려줄까요?</h2><p>실제로 읽을 문장을 입력해 주세요.</p></div></div></div>
            <textarea aria-label="읽을 문장" id="speech-text" className="speech-text" placeholder="안녕하세요. 오늘 소개할 서비스를 만나보세요. 영어 문장도 그대로 입력할 수 있어요." value={text} maxLength={catalog.max_text_length} onChange={e=>setText(e.target.value)}/>
            <div className="text-bottom text-counter"><span>{text.length.toLocaleString()} / {catalog.max_text_length.toLocaleString()}</span></div>
            <div className="pronunciation-guide" role="note" aria-label="발음 가이드"><span className="guide-icon"><Lightbulb size={19}/></span><div><b>발음 가이드</b><p>고유명사를 원하는 한글 발음으로 입력하면 발음을 맞추기 쉽습니다.</p></div></div>

          </section>
          <section className="panel"><div className="section-title"><div className="section-label"><span className="tile-icon"><SlidersHorizontal size={20}/></span><div><h2>목소리 설정</h2><p>모델에 맞는 목소리와 표현을 선택하세요.</p></div></div></div>
            <div className="field-label" id="model-label">음성 모델</div><div className="model-grid" role="group" aria-labelledby="model-label">{Object.entries(catalog.models).map(([id,m])=><button type="button" key={id} className={'model-card '+(model===id?'selected':'')} aria-pressed={model===id} onClick={()=>changeModel(id)}><div><span className="model-mark">{id==='qwen'?'Q':id==='higgs'?'H':'F'}</span><span className="radio-dot">{model===id&&<span/>}</span></div><b>{m.label}</b><small>{m.description}</small></button>)}</div>
            <div className="divider"/>
            <div className="studio-heading"><div><span className="mini-eyebrow">VOICE & MOOD</span><h3>목소리에 표정을 더해 보세요</h3></div><span className="count-badge">{catalog.voices.length} VOICES · {active.emotions.length} MOODS</span></div>
            <div className="studio-columns">
            <section className="studio-column voice-column" aria-labelledby="voice-label">
              <div className="column-heading"><span>01</span><div><h3 id="voice-label">Voice</h3><p>목소리를 선택하세요</p></div></div>
              <div className="voice-roster" role="group" aria-labelledby="voice-label">{catalog.voices.map(v=><button type="button" key={v.id} className={'roster-item '+(voice===v.id?'selected':'')} aria-pressed={voice===v.id} onClick={()=>chooseVoice(v.id)}><span className="roster-name"><b>{v.label}</b><small>{v.gender}</small></span></button>)}</div>
              {active.custom_voice&&<button type="button" className={'roster-item custom-roster '+(voice==='custom'?'selected':'')} aria-pressed={voice==='custom'} onClick={()=>chooseVoice('custom')}><span className="roster-avatar"><Upload size={19}/></span><span className="roster-name"><b>Custom Voice</b><small>내 목소리 샘플 첨부</small></span>{voice==='custom'&&<Check size={15}/>}</button>}
            {voice==='custom'&&<div className="custom-section"><input ref={fileInput} type="file" accept=".wav,.mp3,.flac,.ogg" className="visually-hidden" aria-label="목소리 샘플 파일" onChange={e=>attach(e.target.files[0])}/>
              <button type="button" disabled={uploading} className={'dropzone '+(dragging?'dragging':'')} onClick={()=>fileInput.current?.click()} onDragOver={e=>{e.preventDefault();setDragging(true);}} onDragLeave={()=>setDragging(false)} onDrop={e=>{e.preventDefault();setDragging(false);if(!busy&&!uploading)attach(e.dataTransfer.files[0]);}}>{uploading?<LoaderCircle className="spin"/>:<Upload size={25}/>}<b>{uploading?'음성을 확인하고 있습니다':upload?upload.filename:'파일을 끌어 놓거나 클릭하여 첨부하세요'}</b><span>WAV, MP3, FLAC, OGG · 3~30초 · 최대 20MB</span></button>
              {upload&&<div className="uploaded"><span><Check size={13}/> 첨부 완료</span><span>{upload.seconds}초</span><button type="button" className="icon-button" aria-label="첨부 제거" onClick={()=>{stopPreview();setUpload(null);}}><X size={17}/></button></div>}
            </div>}
            </section>
            <section className="studio-column mood-column" aria-labelledby="emotion-label">
              <div className="column-heading"><span>02</span><div><h3 id="emotion-label">Mood</h3><p>감정 · 말투 {active.emotions.length}가지</p></div></div>
              <div className="mood-grid" ref={moodGrid} role="group" aria-labelledby="emotion-label">{active.emotions.map((item,index)=><div key={item.id} className={'mood-card mood-color-'+(index%5)+(emotion===item.id?' selected':'')}><button type="button" className="mood-select" aria-label={`${voiceLabel} · ${item.label} 선택`} aria-pressed={emotion===item.id} onClick={()=>chooseEmotion(item.id)}><span className="mood-card-top"><span>{String(index+1).padStart(2,'0')}</span><span className="mood-check">{emotion===item.id&&<Check size={11}/>}</span></span><strong>{item.label}</strong></button></div>)}</div>
              {model!=='higgs'&&<p className="hint mood-note">{active.emotion_note}</p>}
            </section>
            <section className="studio-column listen-column" aria-labelledby="listen-label">
              <div className="column-heading"><span>03</span><div><h3 id="listen-label">샘플 듣기</h3><p>선택한 조합을 확인하세요</p></div></div>
              <div className={'audition-panel '+(voice==='custom'?'custom-unavailable':'')}>
                <span className="model-badge">{active.label}</span><div className="listen-art"><AudioLines size={46}/></div>
                <div className="audition-top"><div><small>선택한 목소리 + 감정</small><b>{voiceLabel} <span>·</span> {selectedEmotion?.label}</b></div></div>
                {voice==='custom'?<div className="custom-preview-notice"><Headphones size={20}/><b>샘플 듣기 미제공</b><p>Custom Voice는 샘플 듣기를 제공하지 않습니다.</p><small>첨부한 목소리와 선택한 감정으로<br/>Voice 생성하기를 눌러 주세요.</small></div>:<>
                  {sampleUrl?<audio ref={sampleAudio} controls preload="metadata" src={sampleUrl} aria-label={`${voiceLabel} · ${selectedEmotion?.label} 조합 미리듣기`} onError={()=>{setError('미리듣기를 불러오지 못했습니다.');}}/>:<p className="preview-empty">이 조합의 미리듣기를 준비하고 있습니다.</p>}
                  <p className="sample-script">“{catalog.preview_text}”</p>
                </>}
              </div>
            </section>
            </div>
            {model==='higgs'&&<section className="instructions higgs-settings" aria-labelledby="higgs-settings-title"><div className="settings-heading"><div><h3 id="higgs-settings-title"><SlidersHorizontal size={16}/>추가 음성 설정</h3><p>목소리의 속도와 높이, 표현을 조절해 보세요.</p></div><button type="button" className="text-button" onClick={()=>setHiggsOptions({...DEFAULT_HIGGS})}>기본값으로 초기화</button></div>
              <div className="settings-grid">{active.controls?.map(control=><div className="setting-card" key={control.id}><div className="field-label" id={'setting-'+control.id}>{control.label}</div><div className="setting-options" role="group" aria-labelledby={'setting-'+control.id}>{control.options.map(option=><button type="button" key={option.id} aria-pressed={higgsOptions[control.id]===option.id} className={'setting-option '+(higgsOptions[control.id]===option.id?'selected':'')} onClick={()=>setHiggsOptions(values=>({...values,[control.id]:option.id}))}>{option.label}</button>)}</div></div>)}</div>
              <p className="hint settings-note">설정은 새 음성 생성에 적용되며, 기존 샘플 듣기는 바뀌지 않습니다.</p>
            </section>}
            {active.instructions&&<div className="instructions"><label className="field-label" htmlFor="instructions">Reference text · 추가 지시 프롬프트 <span>선택</span></label><textarea id="instructions" rows={3} maxLength={1000} value={instructions} onChange={e=>setInstructions(e.target.value)} placeholder={model==='qwen'?'예: 또렷한 발음으로, 문장 사이에 잠시 쉬면서 따뜻하게 말해 주세요.':'예: professional broadcast tone, clear pronunciation, warm and friendly'}/><div className="pronunciation-guide" role="note" aria-label="감정·말투 가이드"><span className="guide-icon"><Lightbulb size={19}/></span><div><b>감정·말투 가이드</b><p>{model==='fish'?'감정·말투 지시로 적용됩니다. 영어로 작성하면 의도를 전달하기 쉽습니다.':'감정과 속도, 억양을 자연어로 설명해 주세요. 이 문장은 읽지 않습니다.'}</p></div></div></div>}
          </section>
        </fieldset>
        {error&&<div className="error" role="alert"><CircleAlert size={18}/><span>{error}</span><button type="button" aria-label="오류 닫기" onClick={()=>setError('')}><X size={16}/></button></div>}
        <div className="generate-bar"><span><Sparkles size={16}/>{voiceLabel} · {selectedEmotion?.label}</span><button type="submit" className="button primary generate" disabled={busy||uploading}>{busy?<LoaderCircle size={18} className="spin"/>:<AudioLines size={18}/>} {busy?'음성 생성 중':'Voice 생성하기'}</button></div>
        </form>
        <aside className="result-column"><section className="panel result-panel"><div className="section-title"><div className="section-label"><span className="tile-icon"><Headphones size={20}/></span><h2>생성 결과</h2></div>{job?.status==='completed'&&<span className="success-badge"><Check size={12}/>완료</span>}</div>
          {!job?<div className="empty-result"><div className="wave-orb"><AudioLines size={44}/></div><h3>목소리를 들을 준비가 됐어요</h3><p>문장과 목소리를 선택하고<br/>Voice 생성하기를 눌러 주세요.</p><div className="empty-wave">{Array.from({length:29},(_,i)=><i key={i} style={{height:8+Math.sin(i*1.7)**2*29}}/>)}</div><span>생성한 음성은 WAV로 저장할 수 있습니다.</span></div>:<div className="result-content"><div className="result-model">{catalog.models[job.request.model].label}<span>{job.request.voice==='custom'?'Custom Voice':job.request.voice} · {catalog.models[job.request.model].emotions.find(e=>e.id===job.request.emotion)?.label}</span></div>{job.request.model==='higgs'&&job.request.higgs_options&&<div className="result-settings">{catalog.models.higgs.controls?.filter(c=>job.request.higgs_options[c.id]&&job.request.higgs_options[c.id]!=='default').map(c=><span key={c.id}>{c.label} · {c.options.find(o=>o.id===job.request.higgs_options[c.id])?.label}</span>)}</div>}<p className="result-text">{job.request.text}</p>
          {busyStatus.includes(job.status)?<div className="progress" role="status"><LoaderCircle size={28} className="spin"/><b>{job.status==='queued'?'생성 대기 중':job.status==='loading'?'목소리를 준비하고 있어요':'음성을 만들고 있어요'}</b><p>{job.message}</p><span className="progress-track"><i/></span>{pollError&&<p>{pollError}</p>}</div>:job.status==='failed'?<div className="error" role="alert"><CircleAlert size={18}/>{job.message}</div>:<><div className="ready-visual"><AudioLines size={52}/><span>YOUR VOICE IS READY</span></div><audio className="result-audio" controls preload="metadata" src={job.audio_url} aria-label="생성된 음성"/><div className="audio-meta"><span>{job.seconds}초</span><span>{job.sample_rate/1000} kHz</span><span>WAV</span></div><div className="voice-result-actions"><a className="result-action action-download" href={job.audio_url+'?download=true'} download><span className="action-icon"><Download size={19}/></span><span><b>음성 다운로드</b><small>WAV 파일로 내려받기</small></span></a><button type="button" className={'result-action action-save '+(saved[job.id]?'is-saved':'')} disabled={!!saved[job.id]} onClick={()=>{setNotice('');setSaveJob(job);}}><span className="action-icon">{saved[job.id]?<Check size={19}/>:<BookmarkPlus size={19}/>}</span><span><b>{saved[job.id]?'저장 완료':'My Voice 저장'}</b><small>내 보이스에 보관하기</small></span></button></div>{notice&&<div className="save-success" role="status"><Check size={15}/><span>{notice}</span><button type="button" onClick={()=>navigate('library')}>보러 가기<ArrowRight size={13}/></button></div>}</>}
          </div>}
          <div className="result-footer"><Check size={14}/>목소리와 감정 조합을 바꿔 비교해 보세요.</div></section>
          <section className="panel history-panel"><div className="section-title"><h3><Clock3 size={16}/>최근 생성</h3><span>{history.length}개</span></div><p className="hint">로그아웃하거나 로그인 세션이 만료되면 생성한 음성이 삭제됩니다.</p>{!history.length?<p className="hint">현재 로그인 세션에서 만든 음성이 표시됩니다.</p>:<div className="history-list">{history.map(item=><button key={item.id} disabled={busy&&job?.id!==item.id} className={'history-item '+(job?.id===item.id?'selected':'')} onClick={()=>setJob(item)}><span className="history-icon">{busyStatus.includes(item.status)?<LoaderCircle size={17} className="spin"/>:<Volume2 size={17}/>}</span><span><b>{item.request.voice==='custom'?'Custom Voice':item.request.voice}<em>{catalog.models[item.request.model].label} · {catalog.models[item.request.model].emotions.find(e=>e.id===item.request.emotion)?.label}</em></b><small>{item.request.text}</small></span><span className="history-status">{item.status==='completed'?`${item.seconds}초`:item.status==='failed'?'실패':'진행 중'}</span></button>)}</div>}</section>
        </aside>
      </div>}
      </>}
      <footer className="page-footer"><span>HYUNDAI WIA <i/> AX for Works</span><span>WiaVoice · AI Voice Studio</span></footer></main>
    </div>
    {saveJob&&<SaveVoiceDialog job={saveJob} request={request} onClose={()=>setSaveJob(null)} onSaved={item=>{setSaved(values=>({...values,[saveJob.id]:item.voice_id}));setNotice('My Voice에 저장되었습니다.');setSaveJob(null);}}/>}
  </div>;
}
function SessionGate(){
  const [user,setUser]=useState(null),[error,setError]=useState('');
  useEffect(()=>{
    let disposed=false;
    async function check(){try{const next=await request('/auth/me');if(!disposed){setUser(previous=>{if(previous&&(previous.user_id!==next.user_id||previous.session_id!==next.session_id||previous.is_admin!==next.is_admin))window.location.reload();return next;});setError('');}}catch(e){if(!disposed)setError(e.message);}}
    check();const timer=setInterval(check,30000);window.addEventListener('focus',check);
    return()=>{disposed=true;clearInterval(timer);window.removeEventListener('focus',check);};
  },[]);
  if(error)return <div className="loading" role="alert">{error}<button className="button" onClick={()=>window.location.reload()}>다시 연결</button></div>;
  return user?(user.is_admin?<AdminWorkspace key={user.user_id} user={user} request={request}/>:<App key={user.user_id} user={user}/>):<div className="loading"><LoaderCircle className="spin"/>로그인을 확인하고 있습니다.</div>;
}
const isAgent = /^\/wiavoice\/agent\/?$/.test(window.location.pathname) || /^\/agent\/?$/.test(window.location.pathname);
const legacyHash = ['#app', '#create', '#my-voice', '#marketplace'].includes(window.location.hash);
if (!isAgent && legacyHash) {
  window.location.replace('/wiavoice/agent' + window.location.search + (window.location.hash === '#app' ? '' : window.location.hash));
} else {
  document.title = isAgent ? 'WiaVoice · Voice 생성' : 'WiaVoice · 텍스트에 목소리를 더하다';
  createRoot(document.getElementById('root')).render(isAgent ? <SessionGate/> : <Introduction/>);
}

