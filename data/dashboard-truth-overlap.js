(function(){
  'use strict';
  if(document.title!=='Wallet500 Revival Solana Expanded') return;
  const DOGE1='DpBzjtgGLF7QA9Ug3eUVGbnqa6j3jvYBn1XuQuktvfhm';
  let state={pre:null,real:null,holder:null,waking:null,loadedAt:0};
  let busy=false;

  const n=v=>{const x=Number(v);return Number.isFinite(x)?x:null};
  const ageMin=v=>{const t=Date.parse(v||'');return Number.isFinite(t)?Math.max(0,(Date.now()-t)/60000):null};
  const skewMin=(a,b)=>{const x=Date.parse(a||''),y=Date.parse(b||'');return Number.isFinite(x)&&Number.isFinite(y)?Math.abs(x-y)/60000:null};
  const fmtAge=m=>m===null?'—':m<1?'<1m':Math.round(m)+'m';
  const fmtN=v=>{const x=n(v);return x===null?'—':Math.round(x).toLocaleString()};
  async function get(path){const r=await fetch(path+'?v='+Date.now(),{cache:'no-store'});if(!r.ok)throw Error(path+' '+r.status);return r.json()}

  function ensureStyle(){
    if(document.getElementById('w500-truth-overlap-style'))return;
    const s=document.createElement('style');s.id='w500-truth-overlap-style';s.textContent=`
      #w500TruthOverlap{display:flex;gap:6px;align-items:center;flex-wrap:wrap;padding:6px 8px;margin:5px 0;border:1px solid #31515d;background:#071118;font:10px monospace;direction:ltr}
      #w500TruthOverlap .truth-chip{padding:3px 6px;border-radius:999px;border:1px solid #31515d;white-space:nowrap}
      #w500TruthOverlap .ok{color:#56efaa;border-color:#2f6958}#w500TruthOverlap .warn{color:#ffd65a;border-color:#6b5b22}#w500TruthOverlap .bad{color:#ff7b86;border-color:#7c3139}#w500TruthOverlap .mut{color:#8eabb5}
      .w500-research-status{color:#ffd65a!important;background:transparent!important}.w500-holder-unverified{color:#ffd65a!important;border-color:#6b5b22!important}.w500-holder-verified{color:#56efaa!important;border-color:#2f6958!important}
      @media(max-width:700px){#w500TruthOverlap{font-size:9px;padding:5px;gap:4px}}
    `;document.head.appendChild(s)
  }

  function ensurePanel(){
    let p=document.getElementById('w500TruthOverlap');if(p)return p;
    p=document.createElement('div');p.id='w500TruthOverlap';p.setAttribute('aria-live','polite');
    const kpis=document.querySelector('.kpis');if(kpis&&kpis.parentNode)kpis.parentNode.insertBefore(p,kpis.nextSibling);else document.body.prepend(p);
    return p;
  }

  function holderRow(){
    const h=state.holder||{};return (h.coins||[]).find(x=>String(x?.token_address||'')===DOGE1)||null;
  }

  function holderVerified(row){
    if(!row||row.holder_count===null||row.holder_count===undefined||row.growth_eligible!==true)return false;
    const st=String(row.holder_truth_status||'').toUpperCase();
    return st.includes('VERIFIED');
  }

  function fixDogeHolderTruth(){
    const cards=[...document.querySelectorAll('.candidateCard')];
    const card=cards.find(x=>String(x.querySelector('.cSym')?.textContent||'').trim()==='HOLDER GROWTH');if(!card)return;
    const badge=card.querySelector('.badge');if(!badge)return;
    const row=holderRow(),ok=holderVerified(row);
    badge.textContent=ok?'FORWARD VERIFIED':'BUILDING / UNVERIFIED';
    badge.classList.toggle('strict',ok);badge.classList.toggle('w500-holder-verified',ok);badge.classList.toggle('w500-holder-unverified',!ok);
    badge.title=ok?'Verified forward holder observation exists for DOGE-1.':'Unique-holder truth is not currently verified. No retroactive holder count is inferred.';
    const note=document.getElementById('dogeHNote');if(note&&!ok)note.textContent='Unique-holder source is unavailable/unverified for this mint. No retroactive holder history is fabricated.';
  }

  function fixDeepWatchSemantics(){
    for(const cell of document.querySelectorAll('td.status,.status')){
      if(String(cell.textContent||'').trim()!=='DEEP_WATCH')continue;
      cell.classList.remove('green','cyan');cell.classList.add('yellow','w500-research-status');
      cell.title='DEEP_WATCH = research queue membership only; not a positive verdict, REAL ALERT, or buy signal.';
    }
  }

  function labelDogeCase(){
    const title=document.querySelector('#doge1-case .candidateTitle');if(!title)return;
    if(!title.dataset.truthRelabeled){title.textContent='CASE STUDY · DOGE‑1 · HISTORICAL + LIVE RESEARCH WATCH';title.dataset.truthRelabeled='1'}
    title.title='Case-study history and current live research are separate. Current status comes from live engine feeds.';
  }

  function render(){
    ensureStyle();const panel=ensurePanel();
    const pre=state.pre||{},real=state.real||{},waking=state.waking||{},holder=state.holder||{};
    const preAge=ageMin(pre.generated_at),realAge=ageMin(real.generated_at),wakeAge=ageMin(waking.generated_at),skew=skewMin(pre.generated_at,real.generated_at);
    const pc=pre.counts||{},wc=waking.counts||{},rc=real.counts||{};
    const preTruth=pre.no_hindsight===true&&pre.production_portfolio_impact==='NONE'&&pre.automatic_buy===false;
    const preHealth=!preTruth||preAge===null||preAge>30?'bad':preAge>15?'warn':'ok';
    const overlapBad=skew===null||skew>30||realAge===null||realAge>30;
    const overlapClass=overlapBad?'bad':skew>15?'warn':'ok';
    const unique=((pre.integrity||{}).record_ids_unique===true)?'UNIQUE':'LEGACY/UNKNOWN';
    panel.innerHTML=`
      <span class="truth-chip ${preHealth}">PRE‑T0 ${fmtAge(preAge)} · ${fmtN(pc.records_total)} records · IDs ${unique}</span>
      <span class="truth-chip ${preHealth}">DEEP ${fmtN(pc.active_deep_watch_snapshots)} · BOUND ${fmtN(pc.active_waking_bindings)}</span>
      <span class="truth-chip ${overlapClass}">ENGINE↔DASH skew ${fmtAge(skew)} · REAL ${fmtAge(realAge)} · WAKING ${fmtAge(wakeAge)}</span>
      <span class="truth-chip mut">REAL ALERTS ${fmtN(rc.real_alerts)} · PRE‑T0 research only</span>
      <span class="truth-chip ${holder.provider_configured===true?'ok':'warn'}">HOLDER provider ${holder.provider_configured===true?'READY':'UNAVAILABLE'}</span>`;
    panel.title='Truth overlap contract: freshness, PRE‑T0 identity integrity, WAKING bindings, production alerts, and holder-provider state.';
    fixDogeHolderTruth();fixDeepWatchSemantics();labelDogeCase();
  }

  async function refresh(){
    if(busy)return;busy=true;
    try{
      const [pre,real,holder,waking]=await Promise.all([
        get('../data/revival-pre-t0-evidence.json'),
        get('../data/real-alerts.json'),
        get('../data/revival-holder-latest.json'),
        get('../data/waking-pre-t0-confirmation.json')
      ]);
      if(pre.mode!=='RESEARCH_ONLY_IMMUTABLE_PRE_T0_EVIDENCE'||pre.network!=='solana')throw Error('PRE_T0_TRUTH_CONTRACT');
      if(holder.network!=='solana'||holder.no_hindsight!==true)throw Error('HOLDER_TRUTH_CONTRACT');
      state={pre,real,holder,waking,loadedAt:Date.now()};
    }catch(_e){state={...state,loadedAt:Date.now()};}
    finally{busy=false;render()}
  }

  function install(){
    ensureStyle();render();refresh();
    const tbody=document.getElementById('rows');if(tbody)new MutationObserver(()=>queueMicrotask(()=>{fixDeepWatchSemantics();fixDogeHolderTruth()})).observe(tbody,{childList:true,subtree:true});
    setInterval(refresh,60000);setInterval(()=>{render()},5000);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
