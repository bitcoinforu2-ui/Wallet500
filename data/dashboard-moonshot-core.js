(()=>{
  'use strict';
  const FEED='/Wallet500/data/moonshot-future-listing-ledger.json';
  const ID='w500MoonshotFuture';
  const esc=s=>String(s??'—').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  const money=n=>{n=Number(n);if(!Number.isFinite(n)||n<=0)return '—';return n>=1e6?'$'+(n/1e6).toFixed(2)+'M':n>=1e3?'$'+(n/1e3).toFixed(1)+'K':'$'+n.toFixed(0)};
  const when=x=>{try{return new Date(x).toLocaleString('he-IL',{timeZone:'Asia/Jerusalem',hour12:false})}catch{return x||'—'}};

  function installStyle(){
    if(document.getElementById(ID+'Style'))return;
    const s=document.createElement('style');s.id=ID+'Style';s.textContent=`
      #${ID}{margin-top:17px;border:1px solid #744d1e;border-radius:16px;background:linear-gradient(145deg,#171108,#0c0d10);padding:12px;box-shadow:0 0 28px #ffae3212}
      #${ID} .ms-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-end;margin-bottom:9px}
      #${ID} .ms-title{font-size:13px;font-weight:1000;color:#ffc86a}
      #${ID} .ms-sub{font-size:8px;color:#99886d;margin-top:3px;line-height:1.45}
      #${ID} .ms-count{font-size:9px;color:#cda65f;white-space:nowrap}
      #${ID} .ms-grid{display:grid;gap:9px}
      #${ID} .ms-card{border:1px solid #5e421c;border-radius:14px;padding:12px;background:#0b0d11}
      #${ID} .ms-card.pass{border-color:#a33d37;box-shadow:0 0 22px #ff605018}
      #${ID} .ms-top{display:flex;justify-content:space-between;gap:9px}
      #${ID} .ms-coin{font-size:19px;font-weight:1000;direction:ltr}
      #${ID} .ms-meta{font-size:8px;color:#8e806e;margin-top:3px;direction:ltr}
      #${ID} .ms-badge{font-size:8px;font-weight:1000;border:1px solid currentColor;border-radius:999px;padding:5px 7px;height:max-content;color:#ffc45e}
      #${ID} .ms-card.pass .ms-badge{color:#ff766d}
      #${ID} .ms-cells{display:grid;grid-template-columns:repeat(4,1fr);gap:5px;margin-top:10px}
      #${ID} .ms-cell{background:#080a0d;border:1px solid #22252b;border-radius:8px;padding:7px}
      #${ID} .ms-cell small{display:block;font-size:7px;color:#776e61}.ms-cell b{display:block;font-size:10px;margin-top:3px}
      #${ID} .ms-gate{margin-top:9px;font-size:9px;line-height:1.5;color:#b9b0a2}
      #${ID} .ms-gate b{color:#eee3d2}
      #${ID} .ms-ca{direction:ltr;text-align:left;overflow-wrap:anywhere;font:8px/1.45 monospace;color:#a89a86;margin-top:8px}
      #${ID} .ms-link{display:inline-block;margin:8px 6px 0 0;text-decoration:none;color:#ffd997;border:1px solid #5d4727;border-radius:8px;padding:6px 8px;font-size:8px;font-weight:900}
      #${ID} .ms-empty{padding:14px;text-align:center;color:#8e806e;font-size:9px;border:1px dashed #4c3a20;border-radius:10px}
      @media(min-width:760px){#${ID} .ms-grid{grid-template-columns:repeat(2,1fr)}}
      @media(max-width:520px){#${ID} .ms-cells{grid-template-columns:repeat(2,1fr)}}`;
    document.head.appendChild(s);
  }

  function ensure(){
    let box=document.getElementById(ID);if(box)return box;
    const action=document.getElementById('action');if(!action)return null;
    installStyle();
    box=document.createElement('section');box.id=ID;
    box.innerHTML='<div class="ms-head"><div><div class="ms-title">🚀 MOONSHOT FUTURE LISTING</div><div class="ms-sub">הודעה עתידית רשמית מ‑Moonshot נשארת כאן במעקב. Telegram נשלח רק אם אותו mint עובר את ה‑Canonical REAL ALERT של Wallet500.</div></div><div class="ms-count" id="w500MoonshotCount">—</div></div><div class="ms-grid" id="w500MoonshotCards"><div class="ms-empty">טוען פיד Moonshot…</div></div>';
    action.insertBefore(box,action.firstChild);
    return box;
  }

  function card(e){
    const m=e.market||{},g=e.wallet500_gate||{},a=g.canonical_alert||{};
    const pass=g.pass===true, pending=e.phase==='FUTURE_LISTING_PENDING';
    const sym=e.symbol||m.symbol||String(e.token||'TOKEN').slice(0,9);
    const pair=m.pair_address||a.pair_address||'—';
    const age=m.market_age_days;
    const score=a.score;
    return `<article class="ms-card ${pass?'pass':''}"><div class="ms-top"><div><div class="ms-coin">${esc(sym)}</div><div class="ms-meta">SOLANA · PRIORITY 100 · ${esc(when(e.published_at||e.first_seen_at))}</div></div><span class="ms-badge">${pending?'🚀 FUTURE LISTING':'✅ MOONSHOT LIVE'}</span></div><div class="ms-cells"><div class="ms-cell"><small>WALLET500 GATE</small><b>${pass?'PASS ✅':'WAITING ⏳'}</b></div><div class="ms-cell"><small>LIQUIDITY</small><b>${money(m.liquidity_usd)}</b></div><div class="ms-cell"><small>AGE</small><b>${age==null?'—':esc(Number(age).toFixed(0)+'d')}</b></div><div class="ms-cell"><small>SCORE</small><b>${score==null?'—':esc(score)}</b></div></div><div class="ms-gate"><b>${pass?'SPECIAL ALERT READY':'SPECIAL WATCH'}:</b> ${pass?'המטבע עבר כרגע את ה‑Canonical REAL ALERT. Telegram מיוחד נשלח פעם אחת כל עוד הרישום עדיין עתידי.':'ההודעה הרשמית נשמרת בדאש והמנוע בודק מחדש בכל סריקה. אין Telegram עד שכל שערי Wallet500 עוברים.'}</div><div class="ms-ca"><b>CA</b> ${esc(e.token)}<br><b>PAIR</b> ${esc(pair)}</div>${e.source_url?`<a class="ms-link" target="_blank" rel="noopener" href="${esc(e.source_url)}">Moonshot source ↗</a>`:''}${(m.dex_url||a.dex_url)?`<a class="ms-link" target="_blank" rel="noopener" href="${esc(m.dex_url||a.dex_url)}">DEX ↗</a>`:''}</article>`;
  }

  async function refresh(){
    if(!ensure())return;
    const cards=document.getElementById('w500MoonshotCards'),count=document.getElementById('w500MoonshotCount');
    try{
      const r=await fetch(FEED+'?v='+Date.now(),{cache:'no-store'});
      if(!r.ok)throw new Error('HTTP '+r.status);
      const d=await r.json(),all=Object.values(d.events||{}).filter(e=>e&&e.dashboard_visible!==false);
      all.sort((a,b)=>Number(b.phase==='FUTURE_LISTING_PENDING')-Number(a.phase==='FUTURE_LISTING_PENDING')||Number((b.wallet500_gate||{}).pass===true)-Number((a.wallet500_gate||{}).pass===true)||String(b.published_at||b.first_seen_at||'').localeCompare(String(a.published_at||a.first_seen_at||'')));
      const pending=all.filter(e=>e.phase==='FUTURE_LISTING_PENDING'),completed=all.filter(e=>e.phase!=='FUTURE_LISTING_PENDING').slice(0,10),visible=[...pending,...completed];
      count.textContent=`${pending.length} PENDING · ${all.filter(e=>(e.wallet500_gate||{}).pass===true).length} PASS`;
      cards.innerHTML=visible.length?visible.map(card).join(''):'<div class="ms-empty">אין כרגע הודעת רישום עתידי רשמית עם mint מדויק. המעקב פעיל.</div>';
    }catch(err){
      count.textContent='FEED PENDING';
      if(cards&&!cards.dataset.loaded)cards.innerHTML='<div class="ms-empty">פיד Moonshot עדיין לא פורסם או זמנית לא זמין. שאר הדאש ממשיך כרגיל.</div>';
    }
    if(cards)cards.dataset.loaded='1';
  }
  ensure();refresh();setInterval(refresh,5000);
})();
