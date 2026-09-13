(()=>{
  'use strict';
  const ID='w500-accuracy-lab';
  const DATA='/Wallet500/data/accuracy-research.json';
  const esc=v=>String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const n=(v,d=1)=>{const x=Number(v);return Number.isFinite(x)?x.toFixed(d):'—'};
  const pct=v=>v==null?'—':`${n(v,1)}%`;

  function style(){
    if(document.getElementById(ID+'-style'))return;
    const s=document.createElement('style');s.id=ID+'-style';s.textContent=`
      #${ID}{margin-top:12px;border:1px solid #7a5b22;border-radius:18px;background:radial-gradient(circle at 15% 0,#2b200b,#0b1722 55%);box-shadow:0 14px 42px #0005,0 0 34px #ffc65b12;overflow:hidden}
      #${ID} .arHead{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;padding:13px 14px;border-bottom:1px solid #47381d}
      #${ID} .arTitle{font-size:14px;font-weight:1000;color:#ffe19a}#${ID} .arSub{font-size:8px;color:#9db0bd;margin-top:4px;line-height:1.45}
      #${ID} .arFlag{font-size:8px;font-weight:1000;border:1px solid #3b775e;color:#74efbb;background:#0d281e;border-radius:999px;padding:6px 8px;white-space:nowrap}
      #${ID} .arKpis{display:grid;grid-template-columns:repeat(2,1fr);gap:6px;padding:10px 12px 4px}
      #${ID} .arK{background:#07121b;border:1px solid #253b4b;border-radius:11px;padding:9px}#${ID} .arK small{display:block;font-size:7px;color:#73899a}#${ID} .arK b{display:block;margin-top:4px;font-size:17px}#${ID} .gold{color:#ffd166}#${ID} .green{color:#55e4ad}#${ID} .cyan{color:#60d9ff}#${ID} .violet{color:#c2b2ff}
      #${ID} .arFindings{display:grid;gap:6px;padding:8px 12px 12px}#${ID} .arRow{padding:9px;border:1px solid #22394a;background:#08141e;border-radius:11px;font-size:9px;line-height:1.5}#${ID} .arRow strong{display:block;font-size:10px;margin-bottom:2px}
      #${ID} .arPriority{display:flex;gap:5px;flex-wrap:wrap;margin-top:6px}#${ID} .arChip{font-size:7px;border:1px solid #3b4e60;color:#a9c1d0;border-radius:999px;padding:4px 6px}#${ID} .arChip.on{border-color:#735f2d;color:#ffd982}
      #${ID} .arFoot{padding:0 12px 12px;color:#708697;font-size:7px;line-height:1.5}
      @media(min-width:760px){#${ID} .arKpis{grid-template-columns:repeat(4,1fr)}#${ID} .arFindings{grid-template-columns:repeat(3,1fr)}}`;
    document.head.appendChild(s);
  }

  function shell(){
    if(document.getElementById(ID))return document.getElementById(ID);
    const hero=document.querySelector('.hero');
    if(!hero)return null;
    const el=document.createElement('section');el.id=ID;
    hero.insertAdjacentElement('afterend',el);
    return el;
  }

  function render(d){
    const el=shell();if(!el)return;
    const sample=d.sample||{}, head=d.headline||{}, findings=d.findings||[], cov=d.t0_coverage_freshness||{}, gd=d.gate_distance||{}, barrier=d.barrier_probabilities||{};
    const indep=findings.find(x=>x.id==='INDEPENDENT_CONFIRMATION_FALSE_NEGATIVE')||{};
    const strong=findings.find(x=>x.id==='STRONG_DECISION_LANE_CLEAN_SHADOW')||{};
    const priorities=d.research_priority||[];
    el.innerHTML=`
      <div class="arHead"><div><div class="arTitle">🎯 ACCURACY LAB · מחקר שיפור אחוזי הקליעה</div><div class="arSub">Forward/T0 בלבד · מזהה מה היה ב-Winners ומה היה חסר בפספוסים · לא משנה שער Production אוטומטית</div></div><div class="arFlag">PRODUCTION UNCHANGED ✓</div></div>
      <div class="arKpis">
        <div class="arK"><small>24H VERIFIED SAMPLE</small><b class="gold">${esc(sample.mature_24h??'—')}/${esc(sample.strong_target??50)}</b></div>
        <div class="arK"><small>24H WINNER RATE</small><b class="green">${pct(head.verified_24h_winner_rate_pct)}</b></div>
        <div class="arK"><small>T0 MEAN COVERAGE</small><b class="cyan">${pct(cov.mean_feature_coverage_pct)}</b></div>
        <div class="arK"><small>ONE GATE SHORT WIN RATE</small><b class="violet">${pct((gd.one_gate_short||{}).winner_rate_pct)}</b></div>
      </div>
      <div class="arFindings">
        <div class="arRow"><strong class="gold">#1 חשוד ב-False Negatives: Independent Confirmation</strong>${esc(indep.winner_count??0)}/${esc(indep.n??0)} Winners · Big Winner ${esc(indep.big_winner_count??0)} · Mean ${pct(indep.mean_friction_adjusted_return_pct)}<br><span style="color:#7f95a5">החלטה: מחקר בלבד. לא מורידים את השער עדיין.</span></div>
        <div class="arRow"><strong class="green">Strong Decision Gate נשאר קשיח</strong>Clean 6/7 shadow: ${esc(strong.winner_count_24h??0)}/${esc(strong.n_24h??0)} Winners ב-24h.<br><span style="color:#7f95a5">אין כרגע ראיה מספקת להקלה.</span></div>
        <div class="arRow"><strong class="cyan">כיסוי T0 הוא מגבלה מרכזית</strong>${esc(cov.low_coverage_under_50pct_count??'—')} התראות עם פחות מ-50% Feature Coverage.<br><span style="color:#7f95a5">Missing ≠ Zero. קודם משפרים ראייה, אחר כך משקלים.</span></div>
      </div>
      <div class="arFoot">סדר המחקר: <span class="arPriority">${priorities.map((x,i)=>`<span class="arChip ${i<2?'on':''}">${i+1}. ${esc(x.replaceAll('_',' '))}</span>`).join('')}</span><br>יעד הבא: ${esc(sample.next_strong_sample_remaining??'—')} תוצאות 24h נוספות למדגם Strong. ${barrier.probabilities_publishable===false?'P(+25/+50/+100 לפני -8%) עדיין לא מפורסם עד שיש סדר אירועים מלא.':''}</div>`;
  }

  async function refresh(){
    style();
    const el=shell();if(!el)return;
    try{
      const r=await fetch(DATA+'?v='+Date.now(),{cache:'no-store'});
      if(!r.ok)throw new Error('HTTP '+r.status);
      const d=await r.json();
      if(d.mode!=='RESEARCH_ONLY_ACCURACY_LAB_V1')throw new Error('mode mismatch');
      render(d);
    }catch(e){
      el.innerHTML='<div class="arHead"><div><div class="arTitle">🎯 ACCURACY LAB · מחקר שיפור אחוזי הקליעה</div><div class="arSub">המחקר מופעל; ממתין ל-snapshot המאומת הראשון.</div></div><div class="arFlag">RESEARCH ONLY</div></div>';
    }
  }
  refresh();setInterval(refresh,60000);
})();
