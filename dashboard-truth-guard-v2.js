(function(){
  'use strict';
  const money=v=>'$'+Number(v||0).toFixed(2);
  const pct=v=>(Number(v)>=0?'+':'')+Number(v).toFixed(2)+'%';
  const markVerified=m=>Boolean(m&&m._wallet500Identity?.verified===true&&m._wallet500Identity?.contractVersion===2);

  function verifiedMarkFor(row){
    try{
      if(typeof markFor!=='function')return null;
      const m=markFor(row);
      return markVerified(m)?m:null;
    }catch(_e){return null;}
  }

  function verifiedValue(row){
    const m=verifiedMarkFor(row),qty=Number(row?.quantity||0),px=Number(m?.priceUsd||0);
    return m&&qty>0&&px>0&&Number.isFinite(qty*px)?qty*px:null;
  }

  function setText(id,text,cls){
    const el=document.getElementById(id);if(!el)return;
    el.textContent=text;if(cls)el.className=cls;
  }

  function guardExternal(){
    if(typeof exState==='undefined'&&typeof exSummary==='undefined')return;
    const entries=Array.isArray(exState?.entries)?exState.entries:[];
    const total=entries.length||Number(exSummary?.positions||0);
    if(!total)return;
    const values=entries.map(verifiedValue);
    const covered=values.filter(v=>v!==null).length;
    const inv=entries.length?entries.reduce((s,r)=>s+Number(r?.cost_usd||1),0):Number(exSummary?.paper_invested_usd||0);
    if(entries.length===total&&covered===total){
      const val=values.reduce((s,v)=>s+v,0),roi=inv>0?(val/inv-1)*100:0;
      setText('exval',money(val),'n');
      setText('exroi',pct(roi),'n '+(roi>=0?'ok':'bad'));
      setText('exliveage','VERIFIED LIVE COVERAGE: '+covered+'/'+total+' · TOKEN IDENTITY V2 · 100% CURRENT','m');
    }else{
      setText('exval','WITHHELD','n warn');
      setText('exroi','WITHHELD','n warn');
      const snapVal=exSummary?.paper_current_value_usd, snapRoi=exSummary?.paper_roi_pct;
      const snap=snapVal==null?'':(' · LEDGER SNAPSHOT '+money(snapVal)+(snapRoi==null?'':' / '+pct(snapRoi))+' · NOT LIVE VERIFIED');
      setText('exliveage','VERIFIED LIVE COVERAGE: '+covered+'/'+total+' · PARTIAL → AGGREGATE ROI WITHHELD'+snap,'m warn');
    }
  }

  function guardPrimary(){
    if(typeof state==='undefined'||!state)return;
    const status=state.aggregate_current_roi_status;
    if(status==='WITHHELD_PARTIAL_CURRENT_COVERAGE'){
      setText('val','WITHHELD','n warn');setText('pl','WITHHELD','n warn');setText('roi','WITHHELD','n warn');
      const covered=Number(state.current_coverage_count||0),total=Number(state.current_coverage_total||state.paper_entries_count||0);
      const note=document.getElementById('note');if(note&&!note.textContent.includes('TOKEN IDENTITY V2'))note.textContent='TOKEN IDENTITY V2: '+covered+'/'+total+' current marks verified; aggregate current ROI withheld until coverage is complete. '+note.textContent;
    }
  }

  function installBadge(){
    if(document.getElementById('truthGuardV2'))return;
    const bar=document.querySelector('.livebar');if(!bar)return;
    const s=document.createElement('span');s.id='truthGuardV2';s.className='pill';s.textContent='🔒 TOKEN IDENTITY V2 · FAIL CLOSED';bar.appendChild(s);
  }

  function paint(){try{installBadge();guardExternal();guardPrimary();}catch(_e){}}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',paint,{once:true});else paint();
  setInterval(paint,1000);
})();
