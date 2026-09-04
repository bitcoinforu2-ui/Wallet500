(function(){
  'use strict';
  const current=document.currentScript;
  const src=current&&current.src?current.src:'';
  const base=src?src.slice(0,src.lastIndexOf('/')+1):'';
  const core=base+'data/dashboard-live-price-core.js';
  const truth=base+'data/dashboard-truth-overlap.js';
  const esc=u=>String(u).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');
  if(document.readyState==='loading'){
    document.write('<script src="'+esc(core)+'"><\/script>');
    document.write('<script src="'+esc(truth)+'"><\/script>');
    return;
  }
  const load=u=>new Promise((resolve,reject)=>{const s=document.createElement('script');s.src=u;s.onload=resolve;s.onerror=reject;document.head.appendChild(s)});
  load(core).then(()=>load(truth)).catch(()=>{});
})();