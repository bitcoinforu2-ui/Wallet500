(function(){
  'use strict';
  if(document.title!=='Wallet500 Revival Solana Expanded') return;
  const CA='B8RHrVBxSjBGKqAbn1tXo6CWjvt5jFkkqjbCZtuDpump';
  const PAIR='2z2uBDXaAFishs6XRz2atV2Ro7jL8hfdUcKxTTfhjHDw';
  const DEX='https://dexscreener.com/solana/'+PAIR;
  let busy=false,state={market:null,onchain:null,caseStudy:null};
  const n=v=>{const x=Number(v);return Number.isFinite(x)?x:null};
  const ageMin=v=>{const t=Date.parse(v||'');return Number.isFinite(t)?Math.max(0,(Date.now()-t)/60000):null};
  const money=v=>{const x=n(v);if(x===null)return '—';if(Math.abs(x)>=1e6)return '$'+(x/1e6).toFixed(2)+'M';if(Math.abs(x)>=1e3)return '$'+(x/1e3).toFixed(1)+'K';if(Math.abs(x)>=1)return '$'+x.toFixed(2);return '$'+x.toPrecision(4)};
  const pct=v=>{const x=n(v);return x===null?'—':(x>=0?'+':'')+x.toFixed(1)+'%'};
  const val=v=>v===null||v===undefined?'—':String(v);
  async function get(path){const r=await fetch(path+'?v='+Date.now(),{cache:'no-store'});if(!r.ok)throw Error(path+' '+r.status);return r.json()}
  function ensureStyle(){
    if(document.getElementById('w500-dusd-style'))return;
    const s=document.createElement('style');s.id='w500-dusd-style';s.textContent=`
      #dusd-case{border-color:#2f6958;background:#081510}#dusd-case .candidateTitle{color:#56efaa}
      #dusd-case .dusd-age{font:9px monospace;color:#8eabb5}#dusd-case .dusd-warn{color:#ffd65a}#dusd-case .dusd-bad{color:#ff7b86}
    `;document.head.appendChild(s);
  }
  function ensurePanel(){
    let p=document.getElementById('dusd-case');if(p)return p;
    p=document.createElement('div');p.id='dusd-case';p.className='candidatePanel';
    const doge=document.getElementById('doge1-case');
    if(doge&&doge.parentNode)doge.parentNode.insertBefore(p,doge.nextSibling);
    else{const note=document.querySelector('.note');if(note&&note.parentNode)note.parentNode.insertBefore(p,note);else document.body.appendChild(p)}
    return p;
  }
  function render(){
    ensureStyle();const p=ensurePanel();const m=state.market||{},x=m.exact_pair||{},o=state.onchain||{},cs=state.caseStudy||{},asset=cs.asset||{};
    const ma=ageMin(m.observed_at),oa=ageMin(o.observed_at),marketFresh=ma!==null&&ma<=30&&m?.token?.contract_address===CA&&x.pair_address===PAIR&&x.identity_verified===true,onchainFresh=oa!==null&&oa<=90&&o.mint===CA;
    const h=o.positive_account_deltas||{};const whales=Array.isArray(o.whales)?o.whales:[];const flows=Array.isArray(o.flows_vs_previous_hour)?o.flows_vs_previous_hour:[];
    const inflow=flows.filter(z=>z&&z.direction==='BUY_OR_INFLOW').length,outflow=flows.filter(z=>z&&z.direction==='SELL_OR_OUTFLOW').length;
    const live=marketFresh?`<div class="cMetrics"><div class="cm"><b>${money(x.price_usd)}</b><span>PRICE</span></div><div class="cm"><b>${money(x.liquidity_usd)}</b><span>EXACT-PAIR LIQ</span></div><div class="cm"><b>${money(x.volume_h1)}</b><span>VOL H1</span></div><div class="cm"><b>${val(x.buys_h1)} / ${val(x.sells_h1)}</b><span>BUYS / SELLS H1</span></div><div class="cm"><b>${pct(x.price_change_h1_pct)}</b><span>PRICE H1</span></div><div class="cm"><b>${pct(x.price_change_24h_pct)}</b><span>PRICE 24H</span></div></div><div class="why">LIVE EXACT PAIR · snapshot age ${Math.round(ma)}m · no automatic buy</div>`:`<div class="why dusd-bad">NO FRESH EXACT-PAIR MARKET SNAPSHOT — fail closed; no stale price shown as live.</div>`;
    const chain=onchainFresh?`<div class="cMetrics"><div class="cm"><b>${val(o.positive_token_accounts)}</b><span>POSITIVE TOKEN ACCOUNTS</span></div><div class="cm"><b>${val(h.h1)}</b><span>Δ 1H</span></div><div class="cm"><b>${val(h.h6)}</b><span>Δ 6H</span></div><div class="cm"><b>${val(h.h24)}</b><span>Δ 24H</span></div><div class="cm"><b>${whales.length}</b><span>ACCOUNTS ≥0.1% SUPPLY</span></div><div class="cm"><b>${inflow} / ${outflow}</b><span>WHALE INFLOW / OUTFLOW</span></div><div class="cm"><b>${val(o.burned_tokens_since_previous)}</b><span>BURNED SINCE PREV</span></div><div class="cm"><b>${pct(o.supply_change_pct_vs_previous)}</b><span>SUPPLY Δ</span></div></div><div class="why">ON-CHAIN FORWARD LEDGER · age ${Math.round(oa)}m · token-account count is not unique humans</div>`:`<div class="why dusd-warn">ON-CHAIN LEDGER BUILDING / STALE — holder and whale deltas are not inferred.</div>`;
    p.innerHTML=`<div class="candidateHead"><div><div class="candidateTitle">CASE STUDY · DUSD · HISTORICAL + LIVE CLOSE WATCH</div><div class="candidateSub">Exact mint ${CA.slice(0,8)}…${CA.slice(-6)} · Exact pair ${PAIR.slice(0,8)}…${PAIR.slice(-6)} · forward-only research.</div></div><a class="link" target="_blank" rel="noopener" href="${DEX}">פתח DUSD ב‑DEX ↗</a></div><div class="candidateGrid"><div class="candidateCard strict"><div class="cTop"><div class="cSym">DUSD</div><span class="badge strict">PRIORITY CLOSE WATCH</span></div><div class="why">MINT ${CA} · PAIR ${PAIR} · ${asset.dex||'PumpSwap'} · RESEARCH ONLY · NO BUY SIGNAL</div></div><div class="candidateCard"><div class="cTop"><div class="cSym">LIVE MARKET</div><span class="badge ${marketFresh?'strict':''}">${marketFresh?'FRESH':'UNAVAILABLE'}</span></div>${live}</div><div class="candidateCard"><div class="cTop"><div class="cSym">HOLDERS / WHALES / SUPPLY</div><span class="badge ${onchainFresh?'strict':''}">${onchainFresh?'FORWARD LIVE':'BUILDING'}</span></div>${chain}</div></div>`;
  }
  async function refresh(){
    if(busy)return;busy=true;
    const out={...state};
    try{out.caseStudy=await get('../data/case-study-dusd.json')}catch(_e){}
    try{out.market=await get('../data/dusd-live-market.json')}catch(_e){out.market=null}
    try{out.onchain=await get('../data/dusd-whale-current.json')}catch(_e){out.onchain=null}
    state=out;busy=false;render();
  }
  function install(){render();refresh();setInterval(refresh,60000);setInterval(render,5000)}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
