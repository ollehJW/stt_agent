import React, {useEffect, useRef, useState} from 'react';
import {AudioLines, Upload, Plus, Star, Download, Trash2, Search, X, LoaderCircle, ShieldCheck, Check, ArrowLeft, ArrowRight, Headphones, Mic2, CircleAlert} from 'lucide-react';

const json=body=>({headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
const genderLabel=value=>value==='male'?'남자':value==='female'?'여자':'';
const pending=['queued','loading','generating'];
function playOne(event){document.querySelectorAll('audio').forEach(audio=>{if(audio!==event.currentTarget)audio.pause();});}

function RegisterDialog({request,config,onClose,onSaved}){
  const dialog=useRef(null),input=useRef(null),alive=useRef(true);
  const [gender,setGender]=useState('');
  const [name,setName]=useState(''),[description,setDescription]=useState(''),[upload,setUpload]=useState(null),[job,setJob]=useState(null);
  const [uploading,setUploading]=useState(false),[saving,setSaving]=useState(false),[error,setError]=useState(''),[pollError,setPollError]=useState('');
  const [step,setStep]=useState('upload'),[consent,setConsent]=useState(false),[dragging,setDragging]=useState(false);
  const busy=uploading||pending.includes(job?.status);
  useEffect(()=>{dialog.current.showModal();return()=>{alive.current=false;};},[]);
  useEffect(()=>{
    if(!pending.includes(job?.status))return;
    let stopped=false;
    const timer=setInterval(async()=>{try{const next=await request('/jobs/'+job.id);if(!stopped){setJob(next);setPollError('');}}catch(e){if(!stopped)setPollError(e.message);}},2000);
    return()=>{stopped=true;clearInterval(timer);};
  },[job?.id,job?.status]);
  async function preview(item){setError('');setUploading(true);try{const next=await request('/marketplace/preview',{method:'POST',...json({upload_id:item.id})});if(alive.current)setJob(next);}catch(e){if(alive.current)setError(e.message);}finally{if(alive.current)setUploading(false);}}
  async function attach(file){
    if(!file||busy)return;
    setError('');
    if(!/\.(wav|mp3|flac|ogg)$/i.test(file.name)){setError('WAV, MP3, FLAC, OGG 파일을 선택해 주세요.');return;}
    if(file.size>20*1024*1024){setError('최대 20MB까지 업로드할 수 있습니다.');return;}
    setUploading(true);setJob(null);setUpload(null);setConsent(false);
    const form=new FormData();form.append('file',file);
    try{const item=await request('/uploads',{method:'POST',body:form});if(!alive.current)return;setUpload(item);setName(previous=>previous.trim()?previous:file.name.replace(/\.[^.]+$/,'').slice(0,100));await preview(item);}
    catch(e){if(alive.current)setError(e.message);}finally{if(alive.current)setUploading(false);if(input.current)input.current.value='';}
  }
  async function publish(){
    if(saving||!consent)return;setSaving(true);setError('');
    try{const item=await request('/marketplace',{method:'POST',...json({job_id:job.id,name:name.trim(),description:description.trim(),gender,consent:true,consent_version:config.consent_version})});onSaved(item);}
    catch(e){setError(e.message);setSaving(false);}
  }
  return <dialog ref={dialog} className="market-dialog" aria-labelledby="market-register-title" onCancel={e=>{e.preventDefault();if(!saving)onClose();}}>
    <button type="button" className="dialog-close icon-button" aria-label="등록 팝업 닫기" disabled={saving} onClick={onClose}><X size={20}/></button>
    <div className="market-dialog-heading"><span className="market-symbol">{step==='consent'?<ShieldCheck size={26}/>:<Mic2 size={26}/>}</span><div><span className="mini-eyebrow">SHARE YOUR VOICE</span><h2 id="market-register-title">{step==='consent'?'목소리 공유 전, 확인해 주세요':'새로운 목소리 등록'}</h2></div></div>
    <div className="market-steps"><span className={step==='upload'?'active':'done'}><i>{step==='upload'?'1':<Check size={12}/>}</i>음성 & 샘플</span><b/><span className={step==='consent'?'active':''}><i>2</i>동의 & 등록</span></div>
    {step==='upload'?<>
      <div className="market-form-grid"><div><label htmlFor="market-name">목소리 이름</label><input id="market-name" value={name} onChange={e=>setName(e.target.value)} maxLength={100} placeholder="예: 부드러운 안내 목소리" autoFocus/><div className="market-gender" role="group" aria-labelledby="market-gender-label"><span id="market-gender-label">성별 <small>필수</small></span><div>{['male','female'].map(value=><label key={value} className={gender===value?'selected':''}><input type="radio" name="market-gender" value={value} checked={gender===value} onChange={()=>setGender(value)} required/>{genderLabel(value)}</label>)}</div></div><label htmlFor="market-description">한 줄 소개 <span>필수</span></label><textarea id="market-description" required value={description} onChange={e=>setDescription(e.target.value)} maxLength={300} rows={3} placeholder="어떤 분위기의 목소리인지 소개해 주세요."/>
        <input ref={input} type="file" accept=".wav,.mp3,.flac,.ogg" hidden onChange={e=>attach(e.target.files[0])}/>
        <button type="button" className={'market-drop '+(dragging?'dragging':'')} disabled={busy} onClick={()=>input.current.click()} onDragOver={e=>{e.preventDefault();setDragging(true);}} onDragLeave={()=>setDragging(false)} onDrop={e=>{e.preventDefault();setDragging(false);attach(e.dataTransfer.files[0]);}}>
          {uploading?<LoaderCircle size={26} className="spin"/>:<Upload size={26}/>}<b>{upload?'다른 음성으로 바꾸기':'음성 파일을 놓거나 선택하세요'}</b><small>WAV · MP3 · FLAC · OGG</small><small>3~30초 · 최대 20MB</small>
        </button>
        {upload&&<div className="market-uploaded"><Check size={16}/><span title={upload.filename}>{upload.filename}</span><small>{upload.seconds}초</small></div>}
      </div><div className="market-preview-column"><div className="market-preview"><div className="market-preview-title"><Headphones size={19}/><b>샘플 미리듣기</b></div><div className="market-badges"><span>Higgs V3</span><span>중립 Mood</span></div><p className="market-sample-text">“{config.sample_text}”</p>
        {busy?<div className="market-preview-state" role="status"><LoaderCircle size={30} className="spin"/><b>{uploading?'음성을 업로드하고 있어요':job?.status==='loading'?'모델을 준비하고 있어요':'샘플을 만들고 있어요'}</b><p>{job?.message||'잠시만 기다려 주세요.'}</p></div>:job?.status==='completed'?<div className="market-preview-ready"><span><Check size={14}/>샘플 생성 완료</span><audio controls src={job.audio_url} onPlay={playOne} aria-label="등록할 목소리 샘플"/></div>:<div className="market-preview-state"><AudioLines size={36}/><p>{job?.status==='failed'?job.message:'음성을 업로드하면 샘플이 자동으로 생성됩니다.'}</p>{upload&&<button type="button" className="button" onClick={()=>preview(upload)}>샘플 다시 생성</button>}</div>}
        {pollError&&<p className="error" role="alert">{pollError}</p>}
        <small className="market-preview-note">샘플은 위 문장으로 생성됩니다.<br/>다운로드에는 업로드한 참조 음성이 제공됩니다.</small>
      </div></div></div>
    </>:<div className="market-consent"><div className="market-consent-summary"><AudioLines size={24}/><div><b>{name}</b><span>{genderLabel(gender)} · Higgs V3 · 중립 샘플 포함</span></div></div><h3>음성 공유 및 활용 동의</h3><p>등록한 참조 음성과 샘플은 플랫폼 이용자에게 공개되며, 참조 음성은 다운로드하여 AI 음성 생성에 사용할 수 있습니다.</p><label className={'market-consent-check '+(consent?'checked':'')}><input type="checkbox" checked={consent} disabled={saving} onChange={e=>setConsent(e.target.checked)}/><span>{config.consent_text}</span></label><small>동의 내용과 확인 시각은 등록 정보에 함께 기록됩니다.</small></div>}
    {error&&<div className="error" role="alert"><CircleAlert size={16}/>{error}</div>}
    <div className="dialog-actions"><button type="button" className="button" disabled={saving} onClick={()=>step==='consent'?(setStep('upload'),setError('')):onClose()}>{step==='consent'?<><ArrowLeft size={16}/>이전</>:'취소'}</button>{step==='upload'?<button type="button" className="button primary" disabled={busy||job?.status!=='completed'||!name.trim()||!description.trim()||!gender} onClick={()=>{setError('');setStep('consent');}}>등록<ArrowRight size={16}/></button>:<button type="button" className="button primary" disabled={!consent||saving} onClick={publish}>{saving?<LoaderCircle size={16} className="spin"/>:<ShieldCheck size={16}/>} {saving?'등록 중…':'확인 · 최종 등록'}</button>}</div>
  </dialog>;
}

function DeleteDialog({item,request,onClose,onDeleted}){
  const dialog=useRef(null);const [busy,setBusy]=useState(false),[error,setError]=useState('');
  useEffect(()=>{dialog.current.showModal();},[]);
  async function remove(){setBusy(true);try{await request('/marketplace/'+item.voice_id,{method:'DELETE'});onDeleted();}catch(e){setError(e.message);setBusy(false);}}
  return <dialog ref={dialog} className="save-dialog delete-dialog" aria-labelledby="market-delete-title" onCancel={e=>{e.preventDefault();if(!busy)onClose();}}><div className="save-dialog-icon"><Trash2 size={25}/></div><h2 id="market-delete-title">등록한 목소리를 삭제할까요?</h2><p className="delete-name">{item.name}</p><p>마켓플레이스와 즐겨찾기에서 제거됩니다.<br/>이미 다운로드한 파일은 회수되지 않습니다.</p>{error&&<p className="error" role="alert">{error}</p>}<div className="dialog-actions"><button className="button" autoFocus disabled={busy} onClick={onClose}>취소</button><button className="button danger" disabled={busy} onClick={remove}>{busy?<LoaderCircle size={16} className="spin"/>:<Trash2 size={16}/>}삭제</button></div></dialog>;
}

export default function MarketPlace({request}){
  const [config,setConfig]=useState(null),[items,setItems]=useState([]),[total,setTotal]=useState(0),[favorites,setFavorites]=useState([]),[favoriteTotal,setFavoriteTotal]=useState(0),[favoritePage,setFavoritePage]=useState(0);
  const [sort,setSort]=useState('popular'),[downloading,setDownloading]=useState({});
  const [page,setPage]=useState(0),[mine,setMine]=useState(false),[search,setSearch]=useState(''),[draft,setDraft]=useState(''),[revision,setRevision]=useState(0);
  const [loading,setLoading]=useState(true),[error,setError]=useState(''),[notice,setNotice]=useState(''),[register,setRegister]=useState(false),[deleting,setDeleting]=useState(null),[toggling,setToggling]=useState({});
  useEffect(()=>{request('/marketplace/config').then(setConfig).catch(e=>setError(e.message));},[]);
  useEffect(()=>{
    let disposed=false;setLoading(true);setError('');
    request(`/marketplace?limit=8&offset=${page*8}&mine=${mine}&sort=${sort}&search=${encodeURIComponent(search)}`).then(data=>{if(disposed)return;setItems(data.items);setTotal(data.total);if(page&&page*8>=data.total)setPage(Math.max(0,Math.ceil(data.total/8)-1));}).catch(e=>{if(!disposed)setError(e.message);}).finally(()=>{if(!disposed)setLoading(false);});
    return()=>{disposed=true;};
  },[page,mine,search,sort,revision]);
  useEffect(()=>{let disposed=false;request(`/marketplace?favorites=true&limit=12&offset=${favoritePage*12}`).then(data=>{if(!disposed){setFavorites(data.items);setFavoriteTotal(data.total);if(favoritePage&&favoritePage*12>=data.total)setFavoritePage(Math.max(0,Math.ceil(data.total/12)-1));}}).catch(e=>{if(!disposed)setError(e.message);});return()=>{disposed=true;};},[revision,favoritePage]);
  async function download(event,item){
    event.preventDefault();if(downloading[item.voice_id])return;
    setDownloading(v=>({...v,[item.voice_id]:true}));setError('');
    try{
      const blob=await request('/marketplace/'+item.voice_id+'/reference',{responseType:'blob'});
      const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=item.name.replace(/[\\/:*?"<>|]/g,'_')+'.wav';document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);setRevision(v=>v+1);
    }catch(e){setError(e.message);}finally{setDownloading(v=>({...v,[item.voice_id]:false}));}
  }
  async function toggle(item){if(toggling[item.voice_id])return;setToggling(v=>({...v,[item.voice_id]:true}));try{await request('/marketplace/'+item.voice_id+'/favorite',{method:'PUT',...json({enabled:!item.favorite})});setRevision(v=>v+1);}catch(e){setError(e.message);}finally{setToggling(v=>({...v,[item.voice_id]:false}));}}
  return <section className="marketplace">
    <div className="market-hero"><div><span className="mini-eyebrow">A VOICE FOR EVERY STORY</span><h2>좋은 목소리, 함께 나누세요.</h2><p>새로운 목소리를 발견하고, 나만의 Custom Voice를 공유해 보세요.</p><div className="market-hero-tags"><span><Headphones size={14}/>먼저 들어보고</span><span><Star size={14}/>마음에 담고</span><span><Download size={14}/>자유롭게 활용하세요</span></div></div><div className="market-hero-right"><div className="market-hero-wave" aria-hidden="true">{Array.from({length:23},(_,i)=><i key={i} style={{height:12+Math.sin(i*.8)**2*55}}/>)}</div><button className="button primary" disabled={!config} onClick={()=>{setNotice('');setRegister(true);}}><Plus size={18}/>목소리 등록</button></div></div>
    <section className="market-favorites" aria-labelledby="market-favorite-title"><div className="market-section-heading"><h2 id="market-favorite-title"><Star size={19}/>즐겨찾기<span>{favoriteTotal}</span></h2><p>다시 듣고 싶은 목소리를 모아 두세요.</p>{favoriteTotal>12&&<div className="market-favorite-pages"><button className="icon-button" aria-label="이전 즐겨찾기" disabled={!favoritePage} onClick={()=>setFavoritePage(v=>v-1)}><ArrowLeft size={16}/></button><span>{favoritePage+1} / {Math.ceil(favoriteTotal/12)}</span><button className="icon-button" aria-label="다음 즐겨찾기" disabled={(favoritePage+1)*12>=favoriteTotal} onClick={()=>setFavoritePage(v=>v+1)}><ArrowRight size={16}/></button></div>}</div>
      {favorites.length?<div className="market-favorite-list">{favorites.map(item=><article key={item.voice_id} className="market-favorite-card"><div><span className="market-small-avatar"><AudioLines size={20}/></span><b title={item.name}>{item.name}</b><button className="market-star selected" aria-label={item.name+' 즐겨찾기 해제'} aria-pressed="true" disabled={toggling[item.voice_id]} onClick={()=>toggle(item)}><Star size={17}/></button></div><audio controls preload="none" src={item.audio_url} onPlay={playOne} aria-label={item.name+' 즐겨찾기 샘플'}/><a href={item.download_url} download onClick={event=>download(event,item)} aria-disabled={!!downloading[item.voice_id]}><Download size={13}/>참조 음성 다운로드</a></article>)}</div>:<div className="market-favorite-empty"><Star size={20}/><span>마음에 드는 목소리의 <b>별 버튼</b>을 눌러 보세요.</span></div>}
    </section>
    <div className="market-browse-heading"><div><h2>목소리 둘러보기</h2><span>Higgs V3 · 중립 Mood 샘플</span></div><div className="market-browse-tools"><select className="market-sort" aria-label="목소리 정렬" value={sort} onChange={e=>{setSort(e.target.value);setPage(0);}}><option value="popular">인기순</option><option value="latest">최신순</option></select><label className="market-mine"><input type="checkbox" checked={mine} onChange={e=>{setMine(e.target.checked);setPage(0);}}/>내가 등록한 Voice</label><form className="library-search" onSubmit={e=>{e.preventDefault();setSearch(draft.trim());setPage(0);}}><Search size={17}/><input aria-label="마켓플레이스 목소리 검색" placeholder="목소리 이름, 소개 검색" maxLength={100} value={draft} onChange={e=>setDraft(e.target.value)}/><button type="submit">검색</button></form></div></div>
    {notice&&<div className="save-success" role="status"><Check size={16}/>{notice}<button onClick={()=>setNotice('')} aria-label="알림 닫기"><X size={15}/></button></div>}
    {error&&<div className="error" role="alert">{error}<button onClick={()=>{setRevision(v=>v+1);request('/marketplace/config').then(setConfig).catch(e=>setError(e.message));}}>다시 시도</button></div>}
    {loading?<div className="loading"><LoaderCircle className="spin"/>목소리를 불러오고 있습니다.</div>:items.length?<><div className="market-grid">{items.map((item,index)=><article key={item.voice_id} className={'market-card tone-'+index%3}><div className="market-card-top"><span className="market-avatar"><AudioLines size={27}/></span><span className="market-custom-label">CUSTOM VOICE</span><button className={'market-star '+(item.favorite?'selected':'')} disabled={toggling[item.voice_id]} onClick={()=>toggle(item)} aria-label={item.name+(item.favorite?' 즐겨찾기 해제':' 즐겨찾기 추가')} aria-pressed={item.favorite}><Star size={20}/></button></div><div className="market-card-name"><h3 title={item.name}>{item.name}</h3>{item.gender&&<span className="market-gender-badge">{genderLabel(item.gender)}</span>}</div><p className="market-description">{item.description||'이 목소리로 나만의 이야기를 완성해 보세요.'}</p><div className="market-owner"><small>등록자</small><span title={item.owner_display_name||item.owner_name}>{item.owner_display_name||item.owner_name}</span></div><div className="market-card-player"><span><Headphones size={13}/>샘플 듣기 <small>{Number(item.sample_seconds.toFixed(1))}초</small></span><audio controls preload="none" src={item.audio_url} onPlay={playOne} aria-label={item.name+' 샘플'}/></div><div className="market-card-actions"><a href={item.download_url} download onClick={event=>download(event,item)} aria-disabled={!!downloading[item.voice_id]}><Download size={16}/>참조 음성 다운로드<small>WAV</small></a>{item.is_owner&&<button aria-label={item.name+' 삭제'} title="내 Voice 삭제" onClick={()=>setDeleting(item)}><Trash2 size={17}/></button>}</div><div className="market-card-meta"><span className="market-download-count" title="참조 음성 다운로드 횟수"><Download size={12}/>{(item.download_count||0).toLocaleString()}회</span><time dateTime={item.created_at}>{new Intl.DateTimeFormat('ko-KR',{dateStyle:'medium'}).format(new Date(item.created_at))}</time>{item.is_owner&&<span>내 Voice</span>}</div></article>)}</div>{total>8&&<div className="library-pagination"><button className="button" disabled={!page} onClick={()=>setPage(v=>v-1)}>이전</button><span>{page+1} / {Math.ceil(total/8)}</span><button className="button" disabled={(page+1)*8>=total} onClick={()=>setPage(v=>v+1)}>다음</button></div>}</>:!error&&<div className="library-empty market-empty"><div><Mic2 size={34}/></div><h2>{search?'검색한 목소리가 없습니다':mine?'아직 등록한 목소리가 없어요':'첫 번째 목소리의 주인공이 되어 보세요'}</h2><p>{search?'다른 이름이나 소개로 검색해 보세요.':'참조 음성을 올리고, 새로운 목소리를 함께 나눠 보세요.'}</p>{!search&&<button className="button primary" disabled={!config} onClick={()=>setRegister(true)}><Plus size={16}/>목소리 등록</button>}</div>}
    {register&&<RegisterDialog request={request} config={config} onClose={()=>setRegister(false)} onSaved={()=>{setRegister(false);setPage(0);setSearch('');setDraft('');setRevision(v=>v+1);setNotice('새로운 목소리가 마켓플레이스에 등록되었습니다.');}}/>}
    {deleting&&<DeleteDialog item={deleting} request={request} onClose={()=>setDeleting(null)} onDeleted={()=>{setDeleting(null);setRevision(v=>v+1);setNotice('등록한 목소리가 삭제되었습니다.');}}/>}
  </section>;
}
