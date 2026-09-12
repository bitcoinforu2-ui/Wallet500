(()=>{
  const BASE='/Wallet500/';
  const esc=s=>String(s??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const n=(v,d=4)=>v==null?'—':Number(v).toLocaleString('en-US',{maximumFractionDigits:d});
  const usd=v=>v==null?'—':'$'+Number(v).toLocaleString('en-US',{maximumFractionDigits:6});
  const money=v=>v==null?'—':'$'+Number(v).toLocaleString('en-US',{maximumFractionDigits:0});
  function ensurePanel(){
    if(document.getElementById('tradeManagerPanel')) return;
    const learning=document.querySelector('details.panel');
    const el=document.createElement('section');
    el.className='panel'; el.id='tradeManagerPanel';
    el.innerHTML='<div class="title">🎯 7/7 TRADE MANAGER · כניסה / יציאה בזמן אמת</div><div class="muted" style="margin-bottom:8px">אחרי REAL ALERT בלבד · נרות 1H · נזילות / מחזור / Buy-Sell · החלטה ידנית בלבד</div><div class="cards" id="tradeManagerCards"><div class="card">טוען Trade Manager…</div></div>';
    if(learning) learning.parentNode.insertBefore(el,learning); else document.querySelector('.wrap')?.appendChild(el);
  }
  function zone(z){return !z||z.low==null?'—':`${usd(z.low)}–${usd(z.high)}`}
  function stateClass(s){return ['BUY_ZONE','BREAKOUT_RETEST'].includes(s)?'green':s&&s.startsWith('EXIT')||s==='INVALIDATED'?'red':'yellow'}
  function card(x){
    const m=x.market||{},t=x.technicals_1h||{},e=x.entry_plan||{},o=x.exit_plan||{};
    const link=x.dex_url||'';
    return `<div class="card ${x.trade_state==='INVALIDATED'?'action':'build'}">
      <div class="top"><div><div class="symbol">${esc(x.symbol)}</div><div class="muted">${esc(x.chain)} · REAL ALERT 7/7</div></div><span class="badge ${stateClass(x.trade_state)}">${esc(x.state_label)}</span></div>
      <div class="mini"><div class="m"><span class="label">SIGNAL</span><b>${usd(x.signal_price_usd)}</b></div><div class="m"><span class="label">NOW</span><b>${usd(m.current_price_usd)}</b></div><div class="m"><span class="label">FROM SIGNAL</span><b>${n(m.move_from_signal_pct,2)}%</b></div><div class="m"><span class="label">LIQ</span><b>${money(m.liquidity_usd)}</b></div><div class="m"><span class="label">LIQ Δ</span><b>${n(m.liquidity_change_from_signal_pct,1)}%</b></div></div>
      <div class="whygrid"><div class="whybox"><b>כניסה</b>Zone 1: <strong>${zone(e.zone_1)}</strong><br>Zone 2: ${zone(e.zone_2)}<br>Breakout/retest: ${usd(e.breakout_retest_reference)}<br>Invalidation ref: ${usd(e.invalidation_reference)}</div><div class="whybox"><b>ניהול יציאה</b>TP1 / recent high: ${usd(o.target_1_recent_high)}<br>TP2 +1 ATR: ${usd(o.target_2_plus_1atr)}<br>TP3 +2 ATR: ${usd(o.target_3_plus_2atr)}<br>DD high: ${n(m.drawdown_from_12h_high_pct,2)}%</div></div>
      <div class="reason"><b>${esc(x.decision_reason)}</b><br>EMA10 ${usd(t.ema10)} · EMA20 ${usd(t.ema20)} · EMA30 ${usd(t.ema30)} · ATR ${n(t.atr14_pct,2)}% · H1 ${money(m.volume_h1_usd)} · Buys/Sells ${n(m.buys_h1,0)}/${n(m.sells_h1,0)}</div>
      <div class="addr">TOKEN ${esc(x.token_address)}<br>PAIR ${esc(x.pair_address)}</div>
      <div class="actions">${link?`<a class="btn" target="_blank" rel="noopener" href="${esc(link)}">DEX ↗</a>`:''}</div>
    </div>`;
  }
  async function load(){
    ensurePanel(); const box=document.getElementById('tradeManagerCards'); if(!box) return;
    try{const r=await fetch(BASE+'data/trade-management.json?v='+Date.now(),{cache:'no-store'}); if(!r.ok) throw new Error('not ready'); const d=await r.json(); const rows=d.positions||[]; box.innerHTML=rows.length?rows.map(card).join(''):'<div class="card empty">אין כרגע REAL ALERT 7/7 לניהול.</div>';}
    catch(e){box.innerHTML='<div class="card"><span class="yellow">Trade Manager ממתין למחזור הנתונים הראשון…</span></div>';}
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',load); else load();
  setInterval(load,60000);
})();
