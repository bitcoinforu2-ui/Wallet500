(()=>{
  'use strict';
  // WALLET500 OVERLAY LOADER — preserves MOONSHOT FUTURE LISTING, EXIT ENGINE experiment, and ACCURACY LAB research.
  const scripts=[
    '/Wallet500/data/dashboard-moonshot-core.js',
    '/Wallet500/data/dashboard-exit-experiment.js',
    '/Wallet500/data/dashboard-accuracy-research.js'
  ];
  function load(i){
    if(i>=scripts.length)return;
    const s=document.createElement('script');
    s.src=scripts[i]+'?v='+Date.now();
    s.async=false;
    s.onload=()=>load(i+1);
    s.onerror=()=>load(i+1);
    document.body.appendChild(s);
  }
  load(0);
})();
