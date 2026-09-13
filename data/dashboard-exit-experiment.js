(()=>{
  'use strict';
  const FEED='/Wallet500/data/exit-engine-experiment-live.json';
  const ID='w500ExitExperiment';
  const esc=s=>String(s??'—').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  const usd=n=>{n=Number(n);return Number.isFinite(n)?'$'+n.toFixed(2):'—'};
  const price=n=>{n=Number(n);if(!Number.isFinite(n)||n<=0)return '—';return n>=1?'$'+n.toFixed(4):n>=0.01?'$'+n.toFixed(5):'$'+n.toPrecision(4)};
  const pct=n=>{n=Number(n);return Number.isFinite(n)?(n>=0?'+':'')+n.toFixed(2)+'%':'—'};
  const cls=n=>Number(n)>=0?'xp-pos':'xp-neg';
  const when=x=>{try{return new Date(x).toLocaleString('he-IL',{timeZone:'Asia/Jerusalem',hour12:false})}catch{return x||'—'}};

  function style(){
    if(document.getElementById(ID+'Style'))return;
    const s=document.createElement('style');s.id=ID+'Style';s.textContent=`
      #${ID}{margin:17px 0;border:1px solid #235b42;border-radius:16px;background:linear-gradient(145deg,#08150f,#0a0d10);padding:12px;box-shadow:0 0 30px #2df28a12}
      #${ID} .xp-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-end;margin-bottom:10px}
      #${ID} .xp-title{font-size:14px;font-weight:1000;color:#69f3aa}#${ID} .xp-sub{font-size:8px;line-height:1.5;color:#83a493;margin-top:3px}
      #${ID} .xp-updated{font-size:8px;color:#698577;white-space:nowrap}
      #${ID} .xp-metrics{display:grid;grid-template-columns:repeat(6,1fr);gap:6px;margin-bottom:10px}
      #${ID} .xp-metric{border:1px solid #1d3b2d;background:#07100c;border-radius:10px;padding:8px;min-width:0}#${ID} .xp-metric small{display:block;font-size:7px;color:#6f8c7d}#${ID} .xp-metric b{display:block;font-size:13px;margin-top:4px;direction:ltr;text-align:left}
      #${ID} .xp-pos{color:#62efa7!important}#${ID} .xp-neg{color:#ff7777!important}#${ID} .xp-rule{font-size:9px;line-height:1.5;color:#aabbb2;border:1px solid #183526;border-radius:9px;padding:8px;margin-bottom:10px}#${ID} .xp-rule b{color:#e8fff2}
      #${ID} .xp-table{display:grid;gap:6px}#${ID} .xp-row{display:grid;grid-template-columns:1.1fr repeat(6,.8fr);gap:5px;align-items:center;border:1px solid #182820;border-radius:9px;background:#080c0a;padding:7px}
      #${ID} .xp-row.xp-th{font-size:7px;color:#64786d;background:transparent;border-style:dashed}#${ID} .xp-symbol{font-weight:1000;font-size:11px;direction:ltr}#${ID} .xp-meta{font-size:7px;color:#718178;margin-top:2px;direction:ltr}#${ID} .xp-cell{font-size:9px;direction:ltr;text-align:left;overflow:hidden;text-overflow:ellipsis}#${ID} .xp-state{font-size:8px;font-weight:900}
      #${ID} .xp-empty{padding:13px;text-align:center;color:#718178;border:1px dashed #244333;border-radius:9px;font-size:9px}
      @media(max-width:760px){#${ID} .xp-metrics{grid-template-columns:repeat(3,1fr)}#${ID} .xp-row{grid-template-columns:1.2fr repeat(3,.85fr)}#${ID} .xp-hide-mobile{display:none}}
    `;document.head.appendChild(s);
  }

  function ensure(){
    let box=document.getElementById(ID);if(box)return box;
    const action=document.getElementById('action');if(!action)return null;
    style();box=document.createElement('section');box.id=ID;
    box.innerHTML='<div class="xp-head"><div><div class="xp-title">🧪 EXIT ENGINE · $10 PAPER EXPERIMENT</div><div class="xp-sub">ניסוי קבוע: $10 לכל FIRST REAL ALERT, פוזיציה אחת לכל token. Hard Stop ‎-8% · Trailing 10% מופעל אחרי +25% · ללא hindsight.</div></div><div class="xp-updated" id="w500ExitUpdated">טוען…</div></div><div class="xp-metrics" id="w500ExitMetrics"></div><div class="xp-rule" id="w500ExitRule">טוען נתוני ניסוי…</div><div class="xp-table" id="w500ExitRows"><div class="xp-empty">מאתחל את ניסוי ה‑Exit Engine…</div></div>';
    action.insertBefore(box,action.firstChild);return box;
  }

  function metric(label,value,c=''){return `<div class="xp-metric"><small>${esc(label)}</small><b class="${c}">${esc(value)}</b></div>`}
  function row(p){
    const open=p.status==='OPEN';
    const ret=open?p.hold_return_pct:p.realized_return_pct;
    const stop=open?p.active_stop_price_usd:p.exit_price_usd;
    const state=open?(p.trailing_active?'TRAIL ACTIVE':'OPEN'):(p.exit_reason||'CLOSED');
    const legacy=p.legacy_cohort?'LEGACY REPLAY':'FORWARD';
    return `<div class="xp-row"><div><div class="xp-symbol">${esc(p.symbol||'TOKEN')}</div><div class="xp-meta">${esc(String(p.chain||'').toUpperCase())} · ${esc(legacy)}</div></div><div class="xp-cell"><small>ENTRY</small><br>${esc(price(p.entry_price_usd))}</div><div class="xp-cell"><small>NOW</small><br>${esc(price(p.current_price_usd))}</div><div class="xp-cell"><small>RETURN</small><br><b class="${cls(ret)}">${esc(pct(ret))}</b></div><div class="xp-cell xp-hide-mobile"><small>PEAK</small><br>${esc(price(p.observed_peak_price_usd))}</div><div class="xp-cell xp-hide-mobile"><small>${open?'STOP':'EXIT'}</small><br>${esc(price(stop))}</div><div class="xp-cell"><span class="xp-state ${open?'xp-pos':''}">${esc(state)}</span><br><b>${esc(usd(p.strategy_value_usd))}</b></div></div>`;
  }

  async function refresh(){
    if(!ensure())return;
    const metrics=document.getElementById('w500ExitMetrics'),rows=document.getElementById('w500ExitRows'),rule=document.getElementById('w500ExitRule'),updated=document.getElementById('w500ExitUpdated');
    try{
      const r=await fetch(FEED+'?v='+Date.now(),{cache:'no-store'});if(!r.ok)throw new Error('HTTP '+r.status);
      const d=await r.json(),s=d.strategy||{},ps=Array.isArray(d.positions)?d.positions:[];
      metrics.innerHTML=[
        metric('START',usd(d.initial_capital_usd)),metric('STRATEGY',usd(d.strategy_equity_usd),cls(d.strategy_pnl_usd)),metric('ROI',pct(d.strategy_roi_pct),cls(d.strategy_roi_pct)),metric('HOLD',usd(d.hold_equity_usd),cls(d.hold_pnl_usd)),metric('VS HOLD',usd(d.strategy_vs_hold_usd),cls(d.strategy_vs_hold_usd)),metric('OPEN / CLOSED',`${d.open_positions||0} / ${d.closed_positions||0}`)
      ].join('');
      rule.innerHTML=`<b>RULE:</b> Hard Stop ${esc(pct(s.hard_stop_pct))} · Trailing ${esc(Number(s.trailing_stop_from_peak_pct||0).toFixed(0))}% after ${esc(pct(s.trailing_activation_gain_pct))}. <b>Truth:</b> first observed exact-pair mark only. Legacy cohort uses only timestamped persisted checkpoints; unknown intraperiod moves are not invented. Duplicates excluded: ${esc((d.duplicates_excluded||[]).length)}.`;
      rows.innerHTML=ps.length?ps.map(row).join(''):'<div class="xp-empty">אין עדיין פוזיציות בניסוי.</div>';
      updated.textContent='עדכון '+when(d.updated_at);
    }catch(e){
      updated.textContent='ממתין לפיד';
      if(rows&&!rows.dataset.loaded)rows.innerHTML='<div class="xp-empty">הניסוי הוגדר. הפיד החי יתמלא בריצת המעקב הקרובה.</div>';
    }
    if(rows)rows.dataset.loaded='1';
  }
  ensure();refresh();setInterval(refresh,5000);
})();
