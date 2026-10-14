import React from 'react';
import {AudioLines, ArrowLeft, ArrowRight, ArrowUpRight, Mic2, SlidersHorizontal, Combine, Store, FileText, Download, Headphones} from 'lucide-react';
import {introResources} from './introContent';
import './introduction.css';

const steps = [
  [FileText, '01', '전달할 문장을 준비하세요', '서비스 소개, 교육 자료, 업무 안내처럼 실제로 읽을 내용을 입력하세요. 문장에서 나만의 내레이션이 시작됩니다.', '문장 입력'],
  [SlidersHorizontal, '02', '어울리는 목소리를 찾으세요', '음성 모델과 목소리, 감정을 선택하고 준비된 샘플을 들어 보세요. 모델에 따라 속도와 높이, 표현 방식도 조절할 수 있습니다.', '목소리 · 감정'],
  [Headphones, '03', '듣고, 저장하고, 활용하세요', '생성한 음성을 직접 확인하고 WAV 파일로 내려받으세요. 다시 쓸 음성은 이름을 붙여 My Voice에 보관할 수 있습니다.', '음성 생성 · 활용'],
];
export default function Introduction() {
  return <div className="intro-page voice-intro-page">
    <header className="intro-header"><a className="intro-brand" href="/wiavoice/" aria-label="WiaVoice 소개 처음으로"><AudioLines size={28}/><span>WiaVoice</span></a><a className="voice-intro-return" href="/"><ArrowLeft size={15}/>AX for Works로 돌아가기</a></header>
    <main className="intro-main">
      <section className="intro-hero" aria-labelledby="intro-heading">
        <div className="intro-hero-copy"><div className="intro-eyebrow"><span/>HYUNDAI WIA · AI VOICE STUDIO</div><h1 id="intro-heading">전하고 싶은 이야기에<br/>어울리는 목소리,<br/><em>WiaVoice.</em></h1><p>문장을 준비하고, 원하는 분위기를 골라 보세요.<br/>영상 내레이션부터 업무 안내까지,<br/>AI가 텍스트에 나만의 목소리를 더해 드립니다.</p><div className="intro-hero-actions"><a className="intro-primary" href="/wiavoice/agent">나의 음성 만들기<ArrowRight size={18}/></a><a className="intro-text-link" href="#intro-how">어떻게 이용하나요?<ArrowRight size={15} style={{transform:'rotate(90deg)'}}/></a></div></div>
        <div className="intro-video-column"><div className="intro-video-topline"><span>SERVICE FILM</span></div>{introResources.videoUrl ? <video className="intro-video" controls preload="metadata" aria-label="WiaVoice 서비스 소개 영상"><source src={introResources.videoUrl} type="video/mp4"/></video> : <div className="intro-video-placeholder voice-film" aria-label="WiaVoice 소개 영상 준비 중"><div className="intro-orbit orbit-one"/><div className="intro-orbit orbit-two"/><span className="intro-video-corner">WiaVoice / INSIDE</span><div className="voice-film-card"><div className="voice-film-label"><AudioLines size={18}/><strong>WiaVoice</strong><span>VOICE STUDIO</span></div><p>글이 목소리가 되는 순간</p><div className="voice-film-wave" aria-hidden="true">{Array.from({length:31},(_,i)=><i key={i} style={{height:12+Math.sin(i*.73)**2*55,animationDelay:`${i*-.09}s`}}/>)}</div><div className="voice-film-tags"><span>문장</span><ArrowRight size={13}/><span>목소리</span><ArrowRight size={13}/><span>나의 이야기</span></div></div><div className="intro-video-caption"><span className="voice-film-icon"><Mic2 size={23}/></span><div><strong>영상으로 만나는 WiaVoice</strong><small>소개 영상 준비 중</small></div></div></div>}<p className="intro-video-foot">전달할 내용에 집중하세요. 어울리는 목소리는 WiaVoice와 함께.</p></div>
      </section>
      <section className="intro-benefits" aria-label="WiaVoice의 주요 기능">{[[AudioLines,'문장에 어울리는 목소리','다양한 모델과 감정으로 음성 생성'],[Combine,'하나로 이어지는 내레이션','저장한 음성의 순서와 간격을 조절해 병합'],[Store,'함께 나누는 좋은 목소리','커스텀 목소리를 마켓에서 공유']].map(([Icon,title,text])=><div key={title}><span><Icon size={21}/></span><div><h2>{title}</h2><p>{text}</p></div></div>)}</section>
      <section className="intro-how" id="intro-how" aria-labelledby="intro-how-heading"><div className="intro-section-head"><div><span className="intro-eyebrow">HOW IT WORKS</span><h2 id="intro-how-heading">문장에서 나만의 내레이션까지.</h2></div><p>전하고 싶은 이야기를 준비하세요.<br/>목소리를 고르고, 듣고, 활용하면 됩니다.</p></div><div className="intro-steps">{steps.map(([Icon,n,title,text,tag])=><article key={n}><div className="intro-step-top"><Icon size={23}/><span>{n}</span></div><span className="intro-step-tag">{tag}</span><h3>{title}</h3><p>{text}</p></article>)}</div></section>
      <section className="intro-guide" id="intro-guide" aria-labelledby="intro-guide-heading"><div className="intro-guide-icon"><FileText size={35}/><span>PDF</span></div><div className="intro-guide-copy"><span className="intro-eyebrow">QUICK START GUIDE</span><h2 id="intro-guide-heading">처음이라면, 가이드와 함께.</h2><p>음성 생성부터 보관·병합, 목소리 공유까지.<br/>{introResources.guideUrl?'11페이지 PDF 가이드에서 단계별 사용 방법을 확인하세요.':'단계별 사용 방법을 담은 가이드를 준비하고 있습니다.'}</p></div>{introResources.guideUrl?<a className="intro-guide-download" href={introResources.guideUrl} download={introResources.guideFilename}><Download size={18}/>PDF 가이드 다운로드<ArrowUpRight size={16}/></a>:<div className="intro-guide-ready"><button disabled><FileText size={18}/>PDF 가이드 준비 중</button><span>등록 후 이곳에서 다운로드할 수 있습니다.</span></div>}</section>
    </main><footer className="intro-footer"><span><b>HYUNDAI WIA</b><i/>WiaVoice</span><p>Turn your words into a voice of your own.</p></footer>
  </div>;
}
