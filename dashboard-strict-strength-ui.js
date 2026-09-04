(function(){
  'use strict';
  if(document.title!=='Wallet500 Revival Solana Expanded') return;

  const n=v=>{const x=Number(v);return Number.isFinite(x)?x:0};
  const isStrict=x=>(x?.order_flow_absorption||{}).signal===true;
  const level=x=>isStrict(x)?Number((x.order_flow_absorption||{}).strict_level||0):0;
  const strength=x=>isStrict(x)?Number((x.order_flow_absorption||{}).strict_strength_score||0):0;
  const token=x=>String(x?.token_address||'');

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
    return coins.map((coin,i)=>{
      const card=cards[i];
      if(card)card.dataset.strictToken=token(coin);
      return {coin,card};
    }).filter(x=>x.card);
  }

  function paint(){
    const grid=document.getElementById('candidateGrid');
    if(!grid) return;
    const coins=sourceOrder();
    const cards=[...grid.querySelectorAll('.candidateCard')];
    if(!coins.length||cards.length!==coins.length) return;

    const pairs=pairCards(coins,cards);
    for(const {coin,card} of pairs){
      if(!isStrict(coin)) continue;
      const flow=coin.order_flow_absorption||{};
      const lv=Number(flow.strict_level||0);
      const grade=flow.strict_grade||'STRICT';
      const score=flow.strict_strength_score;
      const badge=card.querySelector('.badge');
      if(badge){
        badge.textContent=grade;
        badge.title='Research-only STRICT strength level. STRICT-3 is strongest; this is not a buy signal.';
      }
      const metrics=card.querySelector('.cMetrics');
      if(metrics&&!metrics.querySelector('.strict-strength-metric')){
        const box=document.createElement('div');
        box.className='cm strict-strength-metric';
        box.innerHTML=`<b>${score==null?'—':Math.round(Number(score))+'/100'}</b><span>STRICT STRENGTH</span>`;
        metrics.appendChild(box);
      }
      const why=card.querySelector('.why');
      const sd=coin.strict_discovery||{};
      if(why&&why.dataset.strictLevelPainted!=='1'){
        const atDiscovery=sd.strict_grade_at_discovery||null;
        why.textContent+=` · CURRENT ${grade}${atDiscovery?` · T0 ${atDiscovery}`:''}`;
        why.dataset.strictLevelPainted='1';
      }
      card.dataset.strictLevel=String(lv||0);
      card.dataset.strictStrength=String(score??0);
    }

    pairs.sort((a,b)=>{
      const sa=isStrict(a.coin)?1:0,sb=isStrict(b.coin)?1:0;
      if(sb!==sa) return sb-sa;
      if(sa){
        const ld=level(b.coin)-level(a.coin);if(ld) return ld;
        const sd=strength(b.coin)-strength(a.coin);if(sd) return sd;
      }
      return n((b.coin.order_flow_absorption||{}).score)-n((a.coin.order_flow_absorption||{}).score);
    });
    const desired=pairs.map(x=>x.card);
    const current=[...grid.querySelectorAll(':scope > .candidateCard')];
    if(desired.some((card,i)=>current[i]!==card))for(const card of desired)grid.appendChild(card);

    const strict=coins.filter(isStrict);
    const s1=strict.filter(x=>level(x)===1).length;
    const s2=strict.filter(x=>level(x)===2).length;
    const s3=strict.filter(x=>level(x)===3).length;
    const early=coins.length-strict.length;
    const summary=document.getElementById('candidateSummary');
    if(summary) summary.textContent=`${coins.length} expansion watch · S3 ${s3} · S2 ${s2} · S1 ${s1} · ${early} pre-move`;
  }

  function install(){
    const original=window.renderCandidates;
    if(typeof original==='function'&&!original._strictStrengthWrapped){
      const wrapped=function(){const out=original.apply(this,arguments);queueMicrotask(paint);return out};
      wrapped._strictStrengthWrapped=true;
      window.renderCandidates=wrapped;
    }
    paint();
    const grid=document.getElementById('candidateGrid');
    if(grid)new MutationObserver(()=>queueMicrotask(paint)).observe(grid,{childList:true,subtree:false});
    setInterval(paint,5000);
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});
  else install();
})();
