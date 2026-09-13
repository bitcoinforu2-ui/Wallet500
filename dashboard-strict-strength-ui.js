(function(){
  'use strict';
  if(document.title!=='Wallet500 Revival Solana Expanded') return;

  const n=v=>{const x=Number(v);return Number.isFinite(x)?x:0};
  const isStrict=x=>(x?.order_flow_absorption||{}).signal===true;
  const level=x=>isStrict(x)?Number((x.order_flow_absorption||{}).strict_level||0):0;
  const strength=x=>isStrict(x)?Number((x.order_flow_absorption||{}).strict_strength_score||0):0;
  const token=x=>String(x?.token_address||'');
  const ACTIVE={liq:15000,vol:10000,txns:40,buys:10,sells:5,turnover:0.10};

  function activity(x){
    const f=x?.order_flow_absorption||{};
    const ready=f.signal_type&&f.signal_type!=='DATA_UNAVAILABLE'&&f.buys_h24!=null&&f.sells_h24!=null&&f.volume_24h_usd!=null&&f.liquidity_usd!=null;
    const buys=n(f.buys_h24),sells=n(f.sells_h24),txns=buys+sells,vol=n(f.volume_24h_usd),liq=n(f.liquidity_usd),turnover=liq>0?vol/liq:0;
    return {ready,buys,sells,txns,vol,liq,turnover};
  }
  function activePass(x){
    const a=activity(x);
    return !!a.ready&&a.liq>=ACTIVE.liq&&a.vol>=ACTIVE.vol&&a.txns>=ACTIVE.txns&&a.buys>=ACTIVE.buys&&a.sells>=ACTIVE.sells&&a.turnover>=ACTIVE.turnover;
  }
  function money(v){const x=n(v);if(x>=1e6)return '$'+(x/1e6).toFixed(2)+'M';if(x>=1e3)return '$'+(x/1e3).toFixed(1)+'K';return '$'+x.toFixed(0)}

  function installActivityGate(){
    if(typeof window.baseCoins==='function'&&!window.baseCoins._activityGateWrapped){
      const original=window.baseCoins;
      const wrapped=function(){return original.apply(this,arguments).filter(activePass)};
      wrapped._activityGateWrapped=true;window.baseCoins=wrapped;
    }
    if(typeof window.candidateCoins==='function'&&!window.candidateCoins._activityGateWrapped){
      const original=window.candidateCoins;
      const wrapped=function(){return original.apply(this,arguments).filter(activePass)};
      wrapped._activityGateWrapped=true;window.candidateCoins=wrapped;
    }
  }

  function paintGateLabels(){
    const truth=document.querySelector('.truth');
    if(truth)truth.textContent='ACTIVE DISPLAY GATE: VERIFIED AGE 90D+ · EXACT-PAIR LIQ >= $15K · VOL 24H >= $10K · TXNS >= 40 · BUYS >= 10 · SELLS >= 5 · VOL/LIQ >= 10% · NO STABLES/PEGGED · NO HINDSIGHT · RESEARCH ONLY';
    const u=document.getElementById('u');if(u&&u.parentElement?.querySelector('.lab'))u.parentElement.querySelector('.lab').textContent='ACTIVE DISPLAY GATE';
    const all=document.querySelector('#band option[value="all"]');if(all)all.textContent='כל הפעילים שעברו Activity Gate';
    const section=document.querySelector('.sectionTitle');if(section)section.textContent='BASE VERIFIED REVIVAL · ACTIVE ONLY · 90D+ · LIQ ≥ $15K · VOL ≥ $10K · TXNS ≥ 40 · 10+ BUYS · 5+ SELLS · VOL/LIQ ≥ 10%';
    const note=document.querySelector('.note');if(note)note.innerHTML='<b>ACTIVE DISPLAY GATE קשיח:</b> גיל 90D+ · Exact-Pair Liquidity ≥ $15K · Volume 24h ≥ $10K · 40+ עסקאות · 10+ buy txns · 5+ sell txns · Vol/Liq ≥ 10%. מטבע שלא עובר נשאר במחקר ואינו נמחק, אבל לא מוצג כמועמד פעיל. נתוני buy/sell כאן הם <b>transaction counts</b>, לא unique wallets.';
  }

  function sourceOrder(){
    if(typeof window.candidateCoins!=='function') return [];
    return [...window.candidateCoins()].sort((a,b)=>{
      const sa=isStrict(a)?1:0,sb=isStrict(b)?1:0;
      return sb-sa||n((b.order_flow_absorption||{}).score)-n((a.order_flow_absorption||{}).score);
    });
  }

  function pairCards(coins,cards){
    const byToken=new Map(coins.map(x=>[token(x),x]));
    const alreadyMapped=cards.length>0&&cards.every(c=>c.dataset.strictToken&&byToken.has(c.dataset.strictToken));
    if(alreadyMapped)return cards.map(card=>({coin:byToken.get(card.dataset.strictToken),card}));
    return coins.map((coin,i)=>{const card=cards[i];if(card)card.dataset.strictToken=token(coin);return {coin,card}}).filter(x=>x.card);
  }

  function paint(){
    installActivityGate();paintGateLabels();
    const grid=document.getElementById('candidateGrid');
    if(!grid) return;
    const coins=sourceOrder();
    const cards=[...grid.querySelectorAll('.candidateCard')];
    if(!coins.length||cards.length!==coins.length) return;

    const pairs=pairCards(coins,cards);
    for(const {coin,card} of pairs){
      const a=activity(coin),metrics=card.querySelector('.cMetrics');
      if(metrics&&!metrics.querySelector('.activity-turnover-metric')){
        const box=document.createElement('div');box.className='cm activity-turnover-metric';
        box.innerHTML=`<b>${(a.turnover*100).toFixed(1)}%</b><span>VOL / LIQ 24H</span>`;metrics.appendChild(box);
      }
      if(!isStrict(coin)) continue;
      const flow=coin.order_flow_absorption||{},lv=Number(flow.strict_level||0),grade=flow.strict_grade||'STRICT',score=flow.strict_strength_score;
      const badge=card.querySelector('.badge');if(badge){badge.textContent=grade;badge.title='Research-only STRICT strength level. STRICT-3 is strongest; this is not a buy signal.'}
      if(metrics&&!metrics.querySelector('.strict-strength-metric')){const box=document.createElement('div');box.className='cm strict-strength-metric';box.innerHTML=`<b>${score==null?'—':Math.round(Number(score))+'/100'}</b><span>STRICT STRENGTH</span>`;metrics.appendChild(box)}
      const why=card.querySelector('.why'),sd=coin.strict_discovery||{};if(why&&why.dataset.strictLevelPainted!=='1'){const atDiscovery=sd.strict_grade_at_discovery||null;why.textContent+=` · CURRENT ${grade}${atDiscovery?` · T0 ${atDiscovery}`:''}`;why.dataset.strictLevelPainted='1'}
      card.dataset.strictLevel=String(lv||0);card.dataset.strictStrength=String(score??0);
    }

    pairs.sort((a,b)=>{const sa=isStrict(a.coin)?1:0,sb=isStrict(b.coin)?1:0;if(sb!==sa)return sb-sa;if(sa){const ld=level(b.coin)-level(a.coin);if(ld)return ld;const sd=strength(b.coin)-strength(a.coin);if(sd)return sd}return n((b.coin.order_flow_absorption||{}).score)-n((a.coin.order_flow_absorption||{}).score)});
    const desired=pairs.map(x=>x.card),current=[...grid.querySelectorAll(':scope > .candidateCard')];if(desired.some((card,i)=>current[i]!==card))for(const card of desired)grid.appendChild(card);
    const strict=coins.filter(isStrict),s1=strict.filter(x=>level(x)===1).length,s2=strict.filter(x=>level(x)===2).length,s3=strict.filter(x=>level(x)===3).length,early=coins.length-strict.length;
    const summary=document.getElementById('candidateSummary');if(summary)summary.textContent=`${coins.length} active expansion watch · S3 ${s3} · S2 ${s2} · S1 ${s1} · ${early} pre-move`;
  }

  function decorateTable(){
    paintGateLabels();
    const table=document.querySelector('.table');if(!table||typeof window.filtered!=='function')return;
    const head=table.querySelector('thead tr');if(head&&!head.querySelector('.activity-head')){
      const ths=[...head.children],anchor=ths.find(x=>x.textContent.trim()==='24h Vol');
      if(anchor){['BUY / SELL TXNS','TXNS 24H','VOL / LIQ'].reverse().forEach(label=>{const th=document.createElement('th');th.className='activity-head';th.textContent=label;anchor.after(th)})}
    }
    const limit=n(document.getElementById('limit')?.value)||500,coins=window.filtered().slice(0,limit),rows=[...table.querySelectorAll('tbody tr')];
    if(rows.length===1&&rows[0].children.length===1){rows[0].children[0].colSpan=27;return}
    rows.forEach((row,i)=>{
      const coin=coins[i];if(!coin||row.querySelector('.activity-cell'))return;
      const a=activity(coin),cells=[...row.children],anchor=cells[6];if(!anchor)return;
      const values=[`${Math.round(a.buys)} / ${Math.round(a.sells)}`,String(Math.round(a.txns)),`${(a.turnover*100).toFixed(1)}%`];
      values.reverse().forEach(value=>{const td=document.createElement('td');td.className='activity-cell';td.textContent=value;anchor.after(td)});
      anchor.textContent=money(a.vol);
    });
  }

  function install(){
    installActivityGate();paintGateLabels();
    const originalCandidates=window.renderCandidates;
    if(typeof originalCandidates==='function'&&!originalCandidates._strictStrengthWrapped){const wrapped=function(){const out=originalCandidates.apply(this,arguments);queueMicrotask(paint);return out};wrapped._strictStrengthWrapped=true;window.renderCandidates=wrapped}
    const originalRender=window.render;
    if(typeof originalRender==='function'&&!originalRender._activityTableWrapped){const wrapped=function(){const out=originalRender.apply(this,arguments);queueMicrotask(()=>{paint();decorateTable()});return out};wrapped._activityTableWrapped=true;window.render=wrapped}
    paint();decorateTable();
    const grid=document.getElementById('candidateGrid');if(grid)new MutationObserver(()=>queueMicrotask(paint)).observe(grid,{childList:true,subtree:false});
    setInterval(()=>{paint();decorateTable()},5000);
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
