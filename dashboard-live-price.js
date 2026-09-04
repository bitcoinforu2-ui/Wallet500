(function(g){
  'use strict';
  const EVM=new Set(['ethereum','eth','bsc','bnb','base','arbitrum','polygon','optimism','avalanche']);
  const chainId=c=>({eth:'ethereum',ethereum:'ethereum',bsc:'bsc',bnb:'bsc',sol:'solana',solana:'solana',base:'base',arbitrum:'arbitrum',polygon:'polygon',optimism:'optimism',avalanche:'avalanche'}[String(c||'').toLowerCase()]||String(c||'').toLowerCase());
  const norm=(c,v)=>{const s=String(v||'');return EVM.has(chainId(c))?s.toLowerCase():s};
  const pairOf=x=>x?.pair_address||x?.pair||x?.dex_pair_address||'';
  const tokenOf=x=>x?.token||x?.token_address||x?.mint||x?.address||x?.contract_address||'';
  const key=x=>chainId(x?.chain)+':'+norm(x?.chain,pairOf(x))+':'+norm(x?.chain,tokenOf(x));
  const same=(c,a,b)=>Boolean(a&&b)&&norm(c,a)===norm(c,b);
  const positive=v=>{const n=Number(v);return Number.isFinite(n)&&n>0?n:null};

  function identityMark(chain,target,pair){
    if(!pair||!target||!pair.pairAddress)return null;
    const base=pair.baseToken||{},quote=pair.quoteToken||{};
    let side=null,price=null;
    if(same(chain,target,base.address)){
      side='BASE';price=positive(pair.priceUsd);
    }else if(same(chain,target,quote.address)){
      side='QUOTE';
      const baseUsd=positive(pair.priceUsd),native=positive(pair.priceNative);
      price=baseUsd!==null&&native!==null?baseUsd/native:null;
    }else return null;
    if(price===null||!Number.isFinite(price)||price<=0)return null;
    const mark={...pair,priceUsd:String(price)};
    mark._wallet500Identity={verified:true,contractVersion:2,targetToken:target,targetSide:side,baseTokenAddress:base.address||null,quoteTokenAddress:quote.address||null,rawBasePriceUsd:pair.priceUsd??null,rawPriceNative:pair.priceNative??null};
    return mark;
  }

  async function dexPoll(rows){
    const out=new Map(),groups={};
    for(const x of rows||[]){
      const c=chainId(x?.chain),p=pairOf(x),t=tokenOf(x);
      if(!c||!p||!t)continue;
      (groups[c]||(groups[c]=[])).push({row:x,pair:p,token:t});
    }
    for(const [c,items] of Object.entries(groups)){
      const unique=[...new Set(items.map(x=>norm(c,x.pair)))];
      const fetched=new Map();
      for(let i=0;i<unique.length;i+=30){
        const wanted=unique.slice(i,i+30);
        try{
          const rawPairs=items.filter(x=>wanted.includes(norm(c,x.pair))).map(x=>x.pair);
          const requestPairs=[...new Set(rawPairs)];
          const u='https://api.dexscreener.com/latest/dex/pairs/'+encodeURIComponent(c)+'/'+requestPairs.map(encodeURIComponent).join(',');
          const r=await fetch(u,{cache:'no-store'});if(!r.ok)continue;
          const j=await r.json();
          for(const p of (j.pairs||[])){
            if(!p?.pairAddress)continue;
            fetched.set(norm(c,p.pairAddress),p);
          }
        }catch(_e){}
      }
      for(const item of items){
        const raw=fetched.get(norm(c,item.pair));
        if(!raw||!same(c,raw.pairAddress,item.pair))continue;
        const mark=identityMark(c,item.token,raw);
        if(mark)out.set(key(item.row),mark);
      }
    }
    return {provider:'DEXSCREENER_IDENTITY_VERIFIED_V2',marks:out,received_at:Date.now(),contractVersion:2};
  }

  g.Wallet500LivePrice={chainId,norm,pairOf,tokenOf,key,poll:dexPoll,identityMark,intervalMs:5000,contractVersion:2};
})(window);
