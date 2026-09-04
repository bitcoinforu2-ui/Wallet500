(function(g){
  'use strict';
  const EVM=new Set(['ethereum','eth','bsc','bnb','base','arbitrum','polygon','optimism','avalanche']);
  const chainId=c=>({eth:'ethereum',ethereum:'ethereum',bsc:'bsc',bnb:'bsc',sol:'solana',solana:'solana',base:'base',arbitrum:'arbitrum',polygon:'polygon',optimism:'optimism',avalanche:'avalanche'}[String(c||'').toLowerCase()]||String(c||'').toLowerCase());
  const norm=(c,v)=>{const s=String(v||'');return EVM.has(chainId(c))?s.toLowerCase():s};
  const pairOf=x=>x?.pair_address||x?.pair||x?.dex_pair_address||'';
  const tokenOf=x=>x?.token||x?.token_address||x?.mint||x?.address||x?.contract_address||'';
  const key=x=>chainId(x?.chain)+':'+norm(x?.chain,pairOf(x))+':'+norm(x?.chain,tokenOf(x));
  const same=(c,a,b)=>Boolean(a&&b)&&norm(c,a)===norm(c,b);
  const positive=v=>{const n=Number(v);return Number.isFinite(n)&&n>0?n:null};

  function identityMark(chain,target,pair){
    if(!pair||!target||!pair.pairAddress)return null;
    const base=pair.baseToken||{},quote=pair.quoteToken||{};
    let side=null,price=null;
    if(same(chain,target,base.address)){
      side='BASE';price=positive(pair.priceUsd);
    }else if(same(chain,target,quote.address)){
      side='QUOTE';
      const baseUsd=positive(pair.priceUsd),native=positive(pair.priceNative);
      price=baseUsd!==null&&native!==null?baseUsd/native:null;
    }else return null;
    if(price===null||!Number.isFinite(price)||price<=0)return null;
    const mark={...pair,priceUsd:String(price)};
    mark._wallet500Identity={verified:true,contractVersion:2,targetToken:target,targetSide:side,baseTokenAddress:base.address||null,quoteTokenAddress:quote.address||null,rawBasePriceUsd:pair.priceUsd??null,rawPriceNative:pair.priceNative??null};
    return mark;
  }

  async function dexPoll(rows){
    const out=new Map(),groups={};
    for(const x of rows||[]){
      const c=chainId(x?.chain),p=pairOf(x),t=tokenOf(x);
      if(!c||!p||!t)continue;
      (groups[c]||(groups[c]=[])).push({row:x,pair:p,token:t});
    }
    for(const [c,items] of Object.entries(groups)){
      const unique=[...new Set(items.map(x=>norm(c,x.pair)))];
      const fetched=new Map();
      for(let i=0;i<unique.length;i+=30){
        const wanted=unique.slice(i,i+30);
        try{
          const rawPairs=items.filter(x=>wanted.includes(norm(c,x.pair))).map(x=>x.pair);
          const requestPairs=[...new Set(rawPairs)];
          const u='https://api.dexscreener.com/latest/dex/pairs/'+encodeURIComponent(c)+'/'+requestPairs.map(encodeURIComponent).join(',');
          const r=await fetch(u,{cache:'no-store'});if(!r.ok)continue;
          const j=await r.json();
          for(const p of (j.pairs||[])){
            if(!p?.pairAddress)continue;
            fetched.set(norm(c,p.pairAddress),p);
          }
        }catch(_e){}
      }
      for(const item of items){
        const raw=fetched.get(norm(c,item.pair));
        if(!raw||!same(c,raw.pairAddress,item.pair))continue;
        const mark=identityMark(c,item.token,raw);
        if(mark)out.set(key(item.row),mark);
      }
    }
    return {provider:'DEXSCREENER_IDENTITY_VERIFIED_V2',marks:out,received_at:Date.now(),contractVersion:2};
  }

  g.Wallet500LivePrice={chainId,norm,pairOf,tokenOf,key,poll:dexPoll,identityMark,intervalMs:5000,contractVersion:2};
})(window);

(function(){
  function installRevivalDesktopFit(){
    if(document.title!=='Wallet500 Revival Solana Expanded' && !document.querySelector('.candidatePanel')) return;
    if(document.getElementById('wallet500-revival-desktop-fit')) return;
    const style=document.createElement('style');
    style.id='wallet500-revival-desktop-fit';
    style.textContent=`
      @media (min-width:901px){
        html,body{height:100%;overflow:hidden}
        body{font-size:11px}
        .wrap{width:100%;max-width:none;height:100vh;box-sizing:border-box;padding:4px 6px;display:flex;flex-direction:column;overflow:hidden}
        .top{position:relative;top:auto;padding:5px 8px;flex:0 0 auto}
        .brand{font-size:17px;line-height:1.05}
        .sub{font-size:9px;margin-top:1px;line-height:1.1}
        .truth{font-size:7.5px;margin-top:2px;line-height:1.15;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .livebar,.rbar{gap:4px;margin-top:3px;flex-wrap:nowrap;overflow:hidden}
        .pill,.rb{padding:2px 5px;font-size:7.5px;white-space:nowrap}
        .dot{width:6px;height:6px}
        .kpis{grid-template-columns:repeat(6,1fr);gap:4px;margin:4px 0;flex:0 0 auto}
        .k{padding:4px 6px;min-height:0}
        .lab{font-size:7.5px;line-height:1}
        .num{font-size:17px;line-height:1;margin-top:2px}
        .note{padding:3px 6px;margin-bottom:3px;font-size:8px;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:0 0 auto}
        .candidatePanel{margin:3px 0;max-height:142px;overflow:auto;flex:0 0 auto}
        .candidateHead{padding:4px 6px;gap:5px;position:sticky;top:0;background:#141108;z-index:2}
        .candidateTitle{font-size:11px;line-height:1}
        .candidateSub{font-size:7.5px;line-height:1.1}
        .candidateGrid{grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:3px;padding:4px}
        .candidateCard{padding:4px 5px}
        .cTop{gap:4px}
        .cSym{font-size:11px}
        .badge{font-size:7px;padding:2px 4px}
        .cMetrics{grid-template-columns:repeat(4,1fr);gap:3px;margin-top:4px}
        .cm{padding-top:2px}
        .cm b{font-size:9px;line-height:1}
        .cm span{font-size:7px;line-height:1}
        .why{margin-top:3px;font-size:7px;line-height:1.1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .research{padding:3px 6px;margin-bottom:3px;font-size:8px;line-height:1.15;flex:0 0 auto;white-space:nowrap;overflow:hidden}
        .research .rbar{display:inline-flex;vertical-align:middle;margin:0 0 0 6px;max-width:62%;overflow:hidden}
        .controls{grid-template-columns:2fr repeat(3,1fr);gap:3px;margin:3px 0;flex:0 0 auto}
        .controls input,.controls select{padding:4px 6px;font-size:9px;min-height:26px}
        .sectionTitle{font-size:10px;margin:3px 0 2px;line-height:1;flex:0 0 auto}
        .tablebox{flex:1 1 auto;min-height:0;overflow:auto;overscroll-behavior:contain}
        .table{width:100%;min-width:0!important;table-layout:fixed;font-size:clamp(13px,1vw,16px)}
        .table th,.table td{padding:5px 2px;line-height:1.18;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .table th{top:0;font-size:clamp(12px,.92vw,15px)}
        .table th:nth-child(1),.table td:nth-child(1){width:2.3%}
        .table th:nth-child(2),.table td:nth-child(2){width:7.2%}
        .table th:nth-child(3),.table td:nth-child(3){width:5.5%}
        .table th:nth-child(4),.table td:nth-child(4){width:6.1%}
        .table th:nth-child(7),.table td:nth-child(7){width:5.8%}
        .table th:nth-child(13),.table td:nth-child(13){width:5.8%}
        .table th:nth-child(19),.table td:nth-child(19){width:6.0%}
        .table th:nth-child(20),.table td:nth-child(20){width:7.0%}
        .table th:nth-child(21),.table td:nth-child(21){width:4.5%}
        .table th:nth-child(22),.table td:nth-child(22){width:3.5%}
        .score{font-size:18px}
        .bar{width:34px;height:3px;margin-left:2px}
        .cov,.status,.sig,.conf{font-size:12px}
        .conf{font-weight:900;text-align:center!important}
        .foot{padding:2px;font-size:7px;line-height:1;flex:0 0 auto;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      }
      @media (min-width:901px) and (max-height:820px){
        .candidatePanel{max-height:116px}
        .candidateGrid{grid-template-columns:repeat(auto-fit,minmax(160px,1fr))}
        .candidateSub{display:none}
        .note{display:none}
        .research{font-size:7.5px}
      }
    `;
    document.head.appendChild(style);
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',installRevivalDesktopFit,{once:true});
  else installRevivalDesktopFit();
})();

(function(){
  if(document.title!=='Wallet500 Revival Solana Expanded') return;
  const confByMint=new Map();
  let summary=null,busy=false;
  const shortStatus=s=>s==='WAKING_STRONG_RESEARCH'?['STRONG','green']:s==='WAKING_CONFIRMED_RESEARCH'?['CONF','cyan']:s==='WAKING_RISK_RESEARCH'?['RISK','red']:s==='WAKING_UNCONFIRMED_RESEARCH'?['LEARN','yellow']:['—','mut'];
  const n=v=>{const x=Number(v);return Number.isFinite(x)?x:null};
  function tooltip(r){
    if(!r)return 'No Waking confirmation row';
    const ch=r.channels||{},h=ch.holders||{},w=ch.wallets||{},s=ch.social||{},news=ch.news||{},hm=h.metrics||{},sm=s.metrics||{},nm=news.metrics||{};
    const parts=[r.confirmation_status||'—','score '+(n(r.confirmation_score)?.toFixed(1)??'—')];
    if((r.strong_families||[]).length)parts.push('strong '+r.strong_families.join(','));
    if(h.verified===true)parts.push('holders '+(hm.holder_count??'—')+(hm.holder_change_pct==null?'':' Δ'+Number(hm.holder_change_pct).toFixed(2)+'%'));
    if(w.verified===true)parts.push('wallets verified');
    if(s.verified===true)parts.push('social '+(sm.mentions??0));
    if(news.verified===true)parts.push('news '+(nm.items??0));
    const d=r.distribution_evidence||{};if(d.risk_score!=null)parts.push('concentration risk '+Number(d.risk_score).toFixed(0));
    return parts.join(' · ');
  }
  function ensureHeader(){
    const tr=document.querySelector('.table thead tr');if(!tr)return;
    if(tr.querySelector('th.waking-conf-head'))return;
    const th=document.createElement('th');th.className='waking-conf-head';th.textContent='CONF';th.title='Waking Confirmation research layer';
    tr.insertBefore(th,tr.lastElementChild);
  }
  function visibleCoins(){
    try{
      if(typeof window.filtered!=='function')return [];
      let arr=window.filtered();const lim=document.getElementById('limit');if(lim)arr=arr.slice(0,Number(lim.value)||500);return arr;
    }catch(_e){return []}
  }
  function paint(){
    ensureHeader();
    const tbody=document.getElementById('rows');if(!tbody)return;
    const trs=[...tbody.querySelectorAll('tr')];const coins=visibleCoins();
    trs.forEach((tr,i)=>{
      if(tr.children.length<2)return;
      let cell=tr.querySelector('td.waking-conf-cell');
      if(!cell){cell=document.createElement('td');cell.className='conf waking-conf-cell';tr.insertBefore(cell,tr.lastElementChild)}
      const coin=coins[i];const r=coin?confByMint.get(String(coin.token_address||'')):null;
      if(!coin||coin.watch_status!=='WAKING_MARKET_ONLY'){cell.textContent='—';cell.className='conf waking-conf-cell mut';cell.title='';return}
      const [txt,cls]=shortStatus(r?.confirmation_status);cell.textContent=txt;cell.className='conf waking-conf-cell '+cls;cell.title=tooltip(r);
    });
    const livebar=document.querySelector('.livebar');
    if(livebar){let el=document.getElementById('wakingConfMeta');if(!el){el=document.createElement('span');el.id='wakingConfMeta';el.className='mut';livebar.appendChild(el)}
      const c=summary?.counts||{};el.textContent=summary?`WAKING CONF: ${c.strong||0} strong · ${c.confirmed||0} conf · ${c.risk||0} risk · ${c.unconfirmed||0} learn`:'WAKING CONF: waiting…';
    }
  }
  async function loadConf(){
    if(busy)return;busy=true;
    try{
      const r=await fetch('../data/waking-confirmation-latest.json?v='+Date.now(),{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);
      const d=await r.json();if(d.mode!=='RESEARCH_ONLY_WAKING_CONFIRMATION_V1'||d.network!=='solana'||d.production_portfolio_impact!=='NONE')throw Error('CONF_TRUTH_CONTRACT');
      confByMint.clear();for(const x of d.targets||[]){if(x&&x.token_address)confByMint.set(String(x.token_address),x)}summary=d;paint();
    }catch(_e){summary=null;paint()}finally{busy=false}
  }
  function install(){
    ensureHeader();
    const tbody=document.getElementById('rows');if(tbody){new MutationObserver(()=>queueMicrotask(paint)).observe(tbody,{childList:true})}
    loadConf();setInterval(loadConf,60000);setInterval(paint,2500);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();

(function(){
  function keepExperimentRubricVisible(){
    const bar=document.getElementById('w500-experiment-rubric');
    if(!bar) return;
    bar.style.setProperty('position','sticky','important');
    bar.style.setProperty('top','0','important');
    bar.style.setProperty('z-index','2147483000','important');
    bar.style.setProperty('background','rgba(2,8,13,.98)','important');
    bar.style.setProperty('box-shadow','0 4px 14px rgba(0,0,0,.45)','important');
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',keepExperimentRubricVisible,{once:true});
  else keepExperimentRubricVisible();
})();

(function(){
  if(document.title!=='Wallet500 Revival Solana Expanded') return;
  const n=v=>{const x=Number(v);return Number.isFinite(x)?x:null};
  const money=v=>{const x=n(v);if(x===null||x<=0)return '—';if(Math.abs(x)>=1e9)return '$'+(x/1e9).toFixed(2)+'B';if(Math.abs(x)>=1e6)return '$'+(x/1e6).toFixed(2)+'M';if(Math.abs(x)>=1e3)return '$'+(x/1e3).toFixed(1)+'K';return '$'+x.toLocaleString(undefined,{maximumSignificantDigits:6})};
  const pct=v=>{const x=n(v);return x===null?'—':(x>=0?'+':'')+x.toFixed(1)+'%'};
  let holderByMint=new Map(),fallbackByMint=new Map(),holderMeta=null,busy=false;
  function visibleCoins(){try{if(typeof window.filtered!=='function')return [];let a=window.filtered();const lim=document.getElementById('limit');return lim?a.slice(0,Number(lim.value)||500):a}catch(_e){return []}}
  function livePriceFor(x){try{if(typeof livePrice==='function')return n(livePrice(x));}catch(_e){}return n(x?.price_usd)}
  function ensureStyle(){if(document.getElementById('w500-discovery-truth-style'))return;const s=document.createElement('style');s.id='w500-discovery-truth-style';s.textContent='.discovery-truth-head{min-width:180px}.discovery-truth-cell{white-space:normal!important;line-height:1.15!important;min-width:180px;font-size:10px}.discovery-truth-cell b{font-size:11px}.discovery-truth-cell .dt-sub{font-size:9px;color:#7f9da7}.discovery-truth-cell .dt-green{color:#56efaa}.discovery-truth-cell .dt-red{color:#ff7b86}.discovery-truth-cell .dt-yellow{color:#ffd65a}@media(max-width:700px){.discovery-truth-head,.discovery-truth-cell{min-width:190px}}';document.head.appendChild(s)}
  function ensureHeader(){const tr=document.querySelector('.table thead tr');if(!tr||tr.querySelector('.discovery-truth-head'))return;const th=document.createElement('th');th.className='discovery-truth-head';th.textContent='DISCOVERY → NOW';th.title='Immutable price T0 and verified holder T0. Holder T0 begins at first verified holder observation and is never retroactively fabricated.';const conf=tr.querySelector('.waking-conf-head');tr.insertBefore(th,conf||tr.lastElementChild)}
  function holderInfo(x){const mint=String(x?.token_address||''),h=holderByMint.get(mint);if(h){const first=n(h.first_holder_count),cur=n(h.holder_count),g=n(h.holder_growth_pct),dc=n(h.holder_growth_count);return{line:`H ${first===null?'—':Math.round(first).toLocaleString()} → ${cur===null?'—':Math.round(cur).toLocaleString()}${g===null?'':' · '+pct(g)}`,title:`Holder T0 ${first??'—'} at ${h.first_holder_observed_at||'—'} · current ${cur??'—'} · growth count ${dc??'—'} · source ${h.source||'—'} · no retroactive holder backfill`,verified:true}}const f=fallbackByMint.get(mint),hm=((f?.channels||{}).holders||{}).metrics||{},cur=n(hm.holder_count),d=n(hm.holder_change_pct);if(cur!==null)return{line:`H ${Math.round(cur).toLocaleString()}${d===null?'':' · Δscan '+pct(d)}`,title:'Verified holder count from Waking confirmation; full holder T0 tracker baseline is not yet available for this mint.',verified:true};return{line:'HOLDERS: — awaiting verified baseline',title:'No verified holder baseline yet. The rotating tracker will fill coverage without fabricating history.',verified:false}}
  function paint(){ensureStyle();ensureHeader();const tbody=document.getElementById('rows');if(!tbody)return;const coins=visibleCoins(),trs=[...tbody.querySelectorAll('tr')];trs.forEach((tr,i)=>{if(tr.children.length<2)return;let cell=tr.querySelector('.discovery-truth-cell');if(!cell){cell=document.createElement('td');cell.className='discovery-truth-cell';const conf=tr.querySelector('.waking-conf-cell');tr.insertBefore(cell,conf||tr.lastElementChild)}const x=coins[i];if(!x){cell.innerHTML='—';cell.title='';return}const t0=x.t0||{},p0=n(t0.t0_price_usd),now=livePriceFor(x),ret=(p0&&now)?(now/p0-1)*100:null,rc=ret===null?'':ret>0?'dt-green':ret<0?'dt-red':'',hi=holderInfo(x),first=t0.first_seen_at?new Date(t0.first_seen_at).toLocaleString():'—';cell.innerHTML=`<b>T0 ${money(p0)}</b> → <b>${money(now)}</b><br><span class="${rc}">${ret===null?'ROI —':pct(ret)+' since discovery'}</span><br><span class="dt-sub">${hi.line}</span>`;cell.title=`DISCOVERED ${first} · Immutable price T0 ${money(p0)} · NOW ${money(now)} · ROI ${pct(ret)}. ${hi.title}`});const livebar=document.querySelector('.livebar');if(livebar){let e=document.getElementById('discoveryTruthMeta');if(!e){e=document.createElement('span');e.id='discoveryTruthMeta';e.className='mut';livebar.appendChild(e)}e.textContent=holderMeta?`DISCOVERY T0: LOCKED · HOLDER COVERAGE ${holderMeta.covered||0}/${holderMeta.universe||0} (${Number(holderMeta.coverage_pct||0).toFixed(1)}%)`:'DISCOVERY T0: LOCKED · HOLDER TRACKER: building'}}
  async function loadHolders(){if(busy)return;busy=true;try{const [a,b]=await Promise.all([fetch('../data/revival-holder-latest.json?v='+Date.now(),{cache:'no-store'}),fetch('../data/waking-confirmation-latest.json?v='+Date.now(),{cache:'no-store'})]);holderByMint.clear();fallbackByMint.clear();holderMeta=null;if(a.ok){const d=await a.json();if(d.mode==='RESEARCH_ONLY_REVIVAL_HOLDER_TRACKER_V1'&&d.network==='solana'&&d.no_hindsight===true){for(const x of d.coins||[]){if(x?.token_address)holderByMint.set(String(x.token_address),x)}holderMeta=d}}if(b.ok){const w=await b.json();for(const x of w.targets||[]){if(x?.token_address)fallbackByMint.set(String(x.token_address),x)}}}catch(_e){}finally{busy=false;paint()}}
  function install(){ensureStyle();ensureHeader();const tbody=document.getElementById('rows');if(tbody)new MutationObserver(()=>queueMicrotask(paint)).observe(tbody,{childList:true});loadHolders();setInterval(loadHolders,60000);setInterval(paint,2000)}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();

(function(){
  if(document.title!=='Wallet500 Revival Solana Expanded') return;
  let busy=false;
  function relabelSnapshotAge(){
    const age=document.getElementById('age');
    const box=age?.closest('.k');
    const lab=box?.querySelector('.lab');
    if(lab){lab.textContent='REVIVAL SNAPSHOT AGE';lab.title='Age of revival-1000-latest.json only; this is not engine freshness.'}
    if(age)age.title='Revival research snapshot age — separate from live engine and browser exact-pair marks.';
  }
  async function refreshEngineFreshness(){
    if(busy)return;busy=true;
    try{
      const r=await fetch('../data/run-summary.json?v='+Date.now(),{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);
      const d=await r.json();const t=Date.parse(d.updated_at);if(!Number.isFinite(t))throw Error('BAD_TIMESTAMP');
      const sec=Math.max(0,Math.floor((Date.now()-t)/1000));
      const txt=sec<60?`${sec}s ago`:`${Math.floor(sec/60)}m ago`;
      const livebar=document.querySelector('.livebar');if(!livebar)return;
      let el=document.getElementById('engineFreshMeta');if(!el){el=document.createElement('span');el.id='engineFreshMeta';livebar.appendChild(el)}
      el.textContent='ENGINE: '+txt;
      el.className=sec<=600?'green':sec<=1800?'yellow':'red';
      el.title='Wallet500 run-summary freshness. Separate from Revival snapshot age and browser live marks.';
    }catch(_e){
      const livebar=document.querySelector('.livebar');if(livebar){let el=document.getElementById('engineFreshMeta');if(!el){el=document.createElement('span');el.id='engineFreshMeta';livebar.appendChild(el)}el.textContent='ENGINE: unavailable';el.className='red';}
    }finally{busy=false}
  }
  function install(){relabelSnapshotAge();refreshEngineFreshness();setInterval(relabelSnapshotAge,2000);setInterval(refreshEngineFreshness,60000)}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
