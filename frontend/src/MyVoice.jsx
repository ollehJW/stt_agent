import MergeVoice from './MergeVoice';
import React, {useEffect, useRef, useState} from 'react';
import {AudioLines, BookmarkPlus, Check, Download, FolderHeart, LoaderCircle, Search, X, ArrowRight, CircleAlert, Combine, ChevronDown, Trash2} from 'lucide-react';

export function SaveVoiceDialog({job, request, onClose, onSaved}){
  const dialog=useRef(null),nameInput=useRef(null);
  const [name,setName]=useState(job.request.text.replace(/\s+/g,' ').slice(0,40));
  const [saving,setSaving]=useState(false),[error,setError]=useState('');
  useEffect(()=>{dialog.current.showModal();nameInput.current.focus();nameInput.current.select();},[]);
  async function save(event){
    event.preventDefault();if(saving||!name.trim())return;
    setSaving(true);setError('');
    try{const item=await request('/jobs/'+job.id+'/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name.trim()})});onSaved(item);}
    catch(e){setError(e.message);setSaving(false);}
  }
  return <dialog className="save-dialog" ref={dialog} aria-labelledby="save-title" aria-describedby="save-description" onCancel={e=>{e.preventDefault();if(!saving)onClose();}}>
    <form onSubmit={save}>
      <button type="button" className="dialog-close icon-button" aria-label="저장 팝업 닫기" disabled={saving} onClick={onClose}><X size={20}/></button>
      <div className="save-dialog-icon"><BookmarkPlus size={26}/></div>
      <span className="mini-eyebrow">YOUR VOICE COLLECTION</span><h2 id="save-title">My Voice에 저장</h2>
      <p id="save-description">다시 찾기 쉬운 이름을 지어 주세요.<br/>저장한 음성은 로그아웃 후에도 보관됩니다.</p>
      <label htmlFor="voice-name">음성 이름</label><input ref={nameInput} id="voice-name" value={name} onChange={e=>setName(e.target.value)} maxLength={100} required disabled={saving} placeholder="예: 서비스 소개 · 차분한 목소리"/>
      <div className="name-count">{name.length} / 100</div>
      <div className="save-context"><AudioLines size={20}/><p>{job.request.text}</p><span>{job.seconds}초</span></div>
      {error&&<div className="error" role="alert"><CircleAlert size={16}/>{error}</div>}
      <div className="dialog-actions"><button type="button" className="button" disabled={saving} onClick={onClose}>취소</button><button type="submit" className="button primary" disabled={saving||!name.trim()}>{saving?<LoaderCircle size={17} className="spin"/>:<BookmarkPlus size={17}/>} {saving?'저장 중…':'My Voice 저장'}</button></div>
    </form>
  </dialog>;
}

function DeleteVoiceDialog({item,request,onClose,onDeleted}){
  const dialog=useRef(null),cancel=useRef(null);
  const [deleting,setDeleting]=useState(false),[error,setError]=useState('');
  useEffect(()=>{dialog.current.showModal();cancel.current.focus();},[]);
  async function remove(){if(deleting)return;setDeleting(true);setError('');try{await request('/my-voices/'+item.voice_id,{method:'DELETE'});onDeleted(item);}catch(e){setError(e.message);setDeleting(false);}}
  return <dialog ref={dialog} className="save-dialog delete-dialog" aria-labelledby="delete-title" aria-describedby="delete-description" onCancel={e=>{e.preventDefault();if(!deleting)onClose();}}><div className="save-dialog-icon"><Trash2 size={25}/></div><h2 id="delete-title">Voice를 삭제할까요?</h2><p className="delete-name">{item.name}</p><p id="delete-description">My Voice에서 음성과 파일이 삭제됩니다.<br/>삭제한 음성은 복구할 수 없습니다.</p>{error&&<div className="error" role="alert">{error}</div>}<div className="dialog-actions"><button ref={cancel} type="button" className="button" disabled={deleting} onClick={onClose}>취소</button><button type="button" className="button danger" disabled={deleting} onClick={remove}>{deleting?<LoaderCircle size={16} className="spin"/>:<Trash2 size={16}/>} {deleting?'삭제 중…':'삭제'}</button></div></dialog>;
}

export default function MyVoice({request,catalog,onCreate,onDeleted}){
  const [deleting,setDeleting]=useState(null);
  const [merging,setMerging]=useState(false),[actions,setActions]=useState([]);
  const previousActions=useRef(new Map());
  useEffect(()=>{
    let disposed=false;
    async function refresh(){try{const next=await request('/merge-actions');if(disposed)return;let completed=false;for(const action of next){if(action.status==='completed'&&previousActions.current.has(action.action_id)&&previousActions.current.get(action.action_id)!=='completed')completed=true;}previousActions.current=new Map(next.map(a=>[a.action_id,a.status]));setActions(next);if(completed)setRetry(v=>v+1);}catch{}}
    refresh();const timer=setInterval(refresh,3000);return()=>{disposed=true;clearInterval(timer);};
  },[]);
  const [items,setItems]=useState([]),[total,setTotal]=useState(0),[loading,setLoading]=useState(true),[error,setError]=useState('');
  const [draft,setDraft]=useState(''),[search,setSearch]=useState(''),[page,setPage]=useState(0),[retry,setRetry]=useState(0);
  useEffect(()=>{
    let disposed=false;setLoading(true);setError('');
    request('/my-voices?limit=6&offset='+page*6+'&search='+encodeURIComponent(search)).then(data=>{if(!disposed){setItems(data.items);setTotal(data.total);if(page>0&&page*6>=data.total)setPage(Math.max(0,Math.ceil(data.total/6)-1));}}).catch(e=>{if(!disposed)setError(e.message);}).finally(()=>{if(!disposed)setLoading(false);});
    return()=>{disposed=true;};
  },[page,search,retry]);
  return <section className="my-voice-library">
    <div className="library-toolbar"><div className="library-tools"><button type="button" className="button primary merge-launch" onClick={()=>setMerging(true)}><Combine size={17}/>Voice 병합</button><form className="library-search" onSubmit={e=>{e.preventDefault();setSearch(draft.trim());setPage(0);}}><Search size={17}/><input aria-label="저장한 음성 검색" placeholder="이름 또는 문장 검색" value={draft} maxLength={100} onChange={e=>setDraft(e.target.value)}/><button type="submit">검색</button></form></div></div>
    {actions.length>0&&<details className="merge-history" open={actions.some(a=>['queued','running'].includes(a.status))||actions[0]?.status==='failed'||undefined}><summary><Combine size={15}/>최근 병합 작업 <span>{actions.filter(a=>['queued','running'].includes(a.status)).length>0?'진행 중':actions.length+'개'}</span><ChevronDown size={14}/></summary><div>{actions.map(action=><div className={'merge-history-row status-'+action.status} key={action.action_id}><span>{action.status==='running'?<LoaderCircle size={15} className="spin"/>:action.status==='completed'?<Check size={15}/>:<Combine size={15}/>}</span><b>{action.name}</b><small>{action.status==='failed'?action.error_message:action.input_voices.length+'개 음성'}</small><em>{action.status==='queued'?'대기 중':action.status==='running'?'병합 중 '+action.progress+'%':action.status==='completed'?(action.result_voice_id?'저장 완료':'결과 삭제됨'):'실패'}</em></div>)}</div></details>}
    {error?<div className="error" role="alert">{error}<button onClick={()=>setRetry(v=>v+1)}>다시 시도</button></div>:loading?<div className="loading"><LoaderCircle className="spin"/>저장한 음성을 불러오고 있습니다.</div>:items.length?<>
      <div className="library-grid">{items.map(item=><article className="library-card" key={item.voice_id}>
        <div className="library-card-top"><span className="library-icon"><AudioLines size={24}/></span><span className="model-badge">{item.model==='merged'?'병합 Voice':catalog?.models[item.model]?.label||item.model}</span></div>
        <h2 title={item.name}>{item.name}</h2><div className="library-tags"><span>{item.speaker==='mixed'?'여러 목소리':item.speaker==='custom'?'Custom Voice':item.speaker}</span><span>{item.emotion==='mixed'?'여러 감정':item.model==='merged'?(Object.values(catalog?.models||{}).flatMap(m=>m.emotions).find(e=>e.id===item.emotion)?.label||item.emotion):catalog?.models[item.model]?.emotions.find(e=>e.id===item.emotion)?.label||item.emotion}</span><span>{Number(item.duration_seconds.toFixed(1))}초</span></div>
        <p className="library-text">{item.text}</p>
        <audio controls preload="none" src={item.audio_url} aria-label={item.name+' 재생'} onPlay={e=>{document.querySelectorAll('audio').forEach(audio=>{if(audio!==e.currentTarget)audio.pause();});}}/>
        <div className="library-card-bottom"><time dateTime={item.created_at}>{new Intl.DateTimeFormat('ko-KR',{dateStyle:'medium'}).format(new Date(item.created_at))}</time><div className="library-card-actions"><a className="library-download" href={item.audio_url+'?download=true'} download aria-label={item.name+' 다운로드'}><Download size={15}/>다운로드</a><button type="button" className="library-delete" aria-label={item.name+' 삭제'} onClick={()=>setDeleting(item)}><Trash2 size={14}/>삭제</button></div></div>
      </article>)}</div>
      {total>6&&<div className="library-pagination"><button className="button" disabled={page===0} onClick={()=>setPage(p=>p-1)}>이전</button><span>{page+1} / {Math.ceil(total/6)}</span><button className="button" disabled={(page+1)*6>=total} onClick={()=>setPage(p=>p+1)}>다음</button></div>}
    </>:<div className="library-empty"><div><FolderHeart size={38}/></div><h2>{search?'검색한 음성이 없습니다':'나만의 목소리를 모아 보세요'}</h2><p>{search?'다른 이름이나 문장으로 검색해 보세요.':'음성을 생성한 뒤 My Voice에 저장하면 이곳에서 언제든 다시 들을 수 있어요.'}</p>{!search&&<button className="button primary" onClick={onCreate}>Voice 생성하기<ArrowRight size={16}/></button>}</div>}
    {deleting&&<DeleteVoiceDialog item={deleting} request={request} onClose={()=>setDeleting(null)} onDeleted={item=>{setDeleting(null);setRetry(v=>v+1);onDeleted?.(item);}}/>}
    {merging&&<MergeVoice request={request} onClose={()=>setMerging(false)} onSubmitted={action=>{setActions(values=>[action,...values.filter(v=>v.action_id!==action.action_id)]);previousActions.current.set(action.action_id,action.status);setMerging(false);setSearch('');setDraft('');setPage(0);}}/>}
  </section>;
}
