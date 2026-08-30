(function(g){
  const chainId=c=>({eth:'ethereum',ethereum:'ethereum',bsc:'bsc',bnb:'bsc',sol:'solana',solana:'solana',base:'base',arbitrum:'arbitrum',polygon:'polygon',optimism:'optimism',avalanche:'avalanche'}[(c||'').toLowerCase()]||(c||'').toLowerCase());
  const key=x=>chainId(x.chain)+':'+String(x.pair_address||x.pair||'').toLowerCase();
  async function dexPoll(rows){
    const out=new Map(),groups={};
    for(const x of rows||[]){const c=chainId(x.chain),p=String(x.pair_address||x.pair||'');if(!c||!p)continue;(groups[c]||(groups[c]=[])).push(p)}
    for(const [c,arr0] of Object.entries(groups)){
      const arr=[...new Set(arr0.map(x=>x.toLowerCase()))];
      for(let i=0;i<arr.length;i+=30){
        const chunk=arr.slice(i,i+30);
        try{
          const u='https://api.dexscreener.com/latest/dex/pairs/'+encodeURIComponent(c)+'/'+chunk.map(encodeURIComponent).join(',');
          const r=await fetch(u,{cache:'no-store'}); if(!r.ok) continue;
          const j=await r.json();
          for(const p of (j.pairs||[])){if(!p||!p.pairAddress)continue;out.set(c+':'+String(p.pairAddress).toLowerCase(),p)}
        }catch(_e){}
      }
    }
    return {provider:'DEXSCREENER_POLL',marks:out,received_at:Date.now()};
  }
  g.Wallet500LivePrice={chainId,key,poll:dexPoll,intervalMs:5000};
})(window);
