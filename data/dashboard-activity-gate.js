(function(){
  'use strict';

  // Defense-in-depth display gate for the live Revival dashboard. The engine
  // keeps low-activity observations for audit/learning, but they must never be
  // rendered as active Revival candidates. Use the live exact-pair 24h volume
  // when available and fail closed on missing/non-finite data.
  const MIN_PAIR_VOLUME_24H_USD=10000;
  let installed=false;

  function pairVolume24h(x){
    try{
      if(typeof lmark==='function'){
        const z=lmark(x);
        const v=Number(z&&z.volume&&z.volume.h24);
        if(Number.isFinite(v)&&v>=0)return v;
      }
    }catch(_e){}
    const snapshot=Number(x&&x.dex_pair_volume_24h_usd);
    return Number.isFinite(snapshot)&&snapshot>=0?snapshot:null;
  }

  function activityEligible(x){
    const v=pairVolume24h(x);
    return v!==null&&v>=MIN_PAIR_VOLUME_24H_USD;
  }

  function wrapGlobal(name){
    let fn;
    try{fn=globalThis[name]}catch(_e){return false}
    if(typeof fn!=='function')return false;
    if(fn.__w500ActivityGate===true)return true;
    const wrapped=function(){
      const rows=fn.apply(this,arguments);
      return Array.isArray(rows)?rows.filter(activityEligible):[];
    };
    wrapped.__w500ActivityGate=true;
    wrapped.__w500ActivityGateOriginal=fn;
    try{globalThis[name]=wrapped;return true}catch(_e){return false}
  }

  function install(){
    const baseOk=wrapGlobal('baseCoins');
    const candidatesOk=wrapGlobal('candidateCoins');
    installed=baseOk||candidatesOk||installed;
    if(installed){
      try{
        if(typeof render==='function'&&typeof DATA!=='undefined'&&DATA)render();
      }catch(_e){}
    }else{
      setTimeout(install,25);
    }
  }

  globalThis.Wallet500ActivityGate={
    minPairVolume24hUsd:MIN_PAIR_VOLUME_24H_USD,
    pairVolume24h,
    activityEligible,
    install
  };

  setTimeout(install,0);
  setInterval(install,30000);
})();
