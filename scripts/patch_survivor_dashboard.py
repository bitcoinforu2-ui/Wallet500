from pathlib import Path

# One-shot idempotent patcher for the main operational dashboard.
p=Path('index.html')
s=p.read_text(encoding='utf-8')

nav_old='<a href="#doge1-case">🚀 DOGE‑1</a>'
nav_new=nav_old+'<a href="#survivor-wave-watch">🌊 Survivors</a>'
if nav_old in s and '#survivor-wave-watch' not in s:
    s=s.replace(nav_old,nav_new,1)

anchor='</section>\n<section id="kol-convergence"'
panel='''</section>\n<section id="survivor-wave-watch" class="sec panel casehot"><div class="head">🌊 WINNER SURVIVORS · HOURLY WAVE WATCH</div><div class="note">מטבעות ששרדו את WINNER_SEPARATOR_NO_HINDSIGHT_V1 ונשארו עם ≥$50K נזילות ב‑Exact Pair. מעקב שעתי אחרי גל נוסף: market acceleration, holder growth, Organic Social, KOL/listing/catalyst. מחקר בלבד — ללא BUY אוטומטי.</div><div class="grid" style="margin-top:10px"><div class="card"><div class="label">SURVIVED NOW</div><div class="n ok" id="survivorCount">—</div></div><div class="card"><div class="label">WAVE BUILDING</div><div class="n" id="survivorWaveCount">—</div></div><div class="card"><div class="label">EARLY REACCELERATION</div><div class="n warn" id="survivorEarlyCount">—</div></div><div class="card"><div class="label">SOURCE WINNERS</div><div class="n" id="survivorSourceCount">—</div></div></div><div class="tokens" id="survivorCards" style="margin-top:10px"><div class="token">טוען Survivor Watch…</div></div><div class="sub clock" id="survivorUpdated">Hourly snapshot: —</div>'''
if 'id="survivor-wave-watch"' not in s:
    if anchor not in s: raise SystemExit('SURVIVOR_PANEL_ANCHOR_MISSING')
    s=s.replace(anchor,panel+'\n<section id="kol-convergence"',1)

js_anchor='function alertCard(a,real=false)'
js='''function survivorCard(x){const state=esc(x.wave_status||'SURVIVOR_WATCH'),url=x.dex_url?`<a class="btn" target="_blank" rel="noopener" href="${esc(x.dex_url)}">DEX ↗</a>`:'';const hd=x.holder_delta_since_prior_hourly_snapshot;const holder=x.holders==null?'coverage חסר':num(x.holders)+(hd==null?'':` (${hd>=0?'+':''}${hd})`);const reasons=(x.wave_reasons||[]).map(r=>`<span class="tag">${esc(r)}</span>`).join('');return `<div class="token"><div class="toktop"><div><div class="sym">${state} · ${esc((x.chain||'').toUpperCase())} · Score ${esc(x.wave_score)}</div><div class="addr"><b>CA:</b> ${esc(x.token)}</div><div class="addr"><b>PAIR:</b> ${esc(x.pair_address)}</div></div>${url}</div><div class="stats"><div class="stat"><span class="label">PRICE</span><b>${money(x.price_usd)}</b></div><div class="stat"><span class="label">LIQ</span><b>${money(x.liquidity_usd)}</b></div><div class="stat"><span class="label">VOL H1</span><b>${money(x.volume_h1_usd)}</b></div><div class="stat"><span class="label">HOLDERS Δ</span><b>${esc(holder)}</b></div></div><div class="tags"><span class="tag">1H ${x.price_change_h1_pct==null?'—':Number(x.price_change_h1_pct).toFixed(2)+'%'}</span><span class="tag">6H ${x.price_change_h6_pct==null?'—':Number(x.price_change_h6_pct).toFixed(2)+'%'}</span><span class="tag">B/S ${esc(x.buys_h1)}/${esc(x.sells_h1)}</span><span class="tag">${esc(x.organic_social_status||'SOCIAL COVERAGE UNKNOWN')}</span>${reasons}</div></div>`}\nasync function loadSurvivors(){try{const d=await j('data/survivor-wave-watch.json'),rows=d.tokens||[];$('survivorCount').textContent=num(d.survivor_n);$('survivorWaveCount').textContent=num(d.wave_building_n);$('survivorEarlyCount').textContent=num(rows.filter(x=>x.wave_status==='EARLY_REACCELERATION').length);$('survivorSourceCount').textContent=num(d.source_winner_n);$('survivorCards').innerHTML=rows.length?rows.map(survivorCard).join(''):'<div class="token">אין כרגע Exact-Pair survivor מעל $50K.</div>';$('survivorUpdated').textContent='Hourly snapshot: '+(d.generated_at||'—')+' · Exact Pair ≥ $50K'}catch(e){$('survivorCards').innerHTML='<div class="token bad">Survivor Watch feed לא נטען.</div>'}}\n'''
if 'function survivorCard(' not in s:
    if js_anchor not in s: raise SystemExit('SURVIVOR_JS_ANCHOR_MISSING')
    s=s.replace(js_anchor,js+js_anchor,1)

run_old='main();loadDoge1();setInterval(main,5000);setInterval(refreshDoge1Pair,5000);setInterval(loadDoge1,60000);'
run_new='main();loadDoge1();loadSurvivors();setInterval(main,5000);setInterval(refreshDoge1Pair,5000);setInterval(loadDoge1,60000);setInterval(loadSurvivors,60000);'
if run_old in s:
    s=s.replace(run_old,run_new,1)
elif 'loadSurvivors();' not in s:
    raise SystemExit('SURVIVOR_RUN_ANCHOR_MISSING')

p.write_text(s,encoding='utf-8')
print('SURVIVOR_DASHBOARD_PATCH_OK')
