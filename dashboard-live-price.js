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

(function(){
  function installRevivalDesktopFit(){
    if(document.title!=='Wallet500 Revival Solana Expanded' && !document.querySelector('.candidatePanel')) return;
    if(document.getElementById('wallet500-revival-desktop-fit')) return;
    const style=document.createElement('style');
    style.id='wallet500-revival-desktop-fit';
    style.textContent=`
      @media (min-width:901px){
        html,body{height:100%;overflow:hidden}
        body{font-size:11px}
        .wrap{width:100%;max-width:none;height:100vh;box-sizing:border-box;padding:4px 6px;display:flex;flex-direction:column;overflow:hidden}
        .top{position:relative;top:auto;padding:5px 8px;flex:0 0 auto}
        .brand{font-size:17px;line-height:1.05}
        .sub{font-size:9px;margin-top:1px;line-height:1.1}
        .truth{font-size:7.5px;margin-top:2px;line-height:1.15;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .livebar,.rbar{gap:4px;margin-top:3px;flex-wrap:nowrap;overflow:hidden}
        .pill,.rb{padding:2px 5px;font-size:7.5px;white-space:nowrap}
        .dot{width:6px;height:6px}
        .kpis{grid-template-columns:repeat(6,1fr);gap:4px;margin:4px 0;flex:0 0 auto}
        .k{padding:4px 6px;min-height:0}
        .lab{font-size:7.5px;line-height:1}
        .num{font-size:17px;line-height:1;margin-top:2px}
        .note{padding:3px 6px;margin-bottom:3px;font-size:8px;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:0 0 auto}
        .candidatePanel{margin:3px 0;max-height:142px;overflow:auto;flex:0 0 auto}
        .candidateHead{padding:4px 6px;gap:5px;position:sticky;top:0;background:#141108;z-index:2}
        .candidateTitle{font-size:11px;line-height:1}
        .candidateSub{font-size:7.5px;line-height:1.1}
        .candidateGrid{grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:3px;padding:4px}
        .candidateCard{padding:4px 5px}
        .cTop{gap:4px}
        .cSym{font-size:11px}
        .badge{font-size:7px;padding:2px 4px}
        .cMetrics{grid-template-columns:repeat(4,1fr);gap:3px;margin-top:4px}
        .cm{padding-top:2px}
        .cm b{font-size:9px;line-height:1}
        .cm span{font-size:7px;line-height:1}
        .why{margin-top:3px;font-size:7px;line-height:1.1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .research{padding:3px 6px;margin-bottom:3px;font-size:8px;line-height:1.15;flex:0 0 auto;white-space:nowrap;overflow:hidden}
        .research .rbar{display:inline-flex;vertical-align:middle;margin:0 0 0 6px;max-width:62%;overflow:hidden}
        .controls{grid-template-columns:2fr repeat(3,1fr);gap:3px;margin:3px 0;flex:0 0 auto}
        .controls input,.controls select{padding:4px 6px;font-size:9px;min-height:26px}
        .sectionTitle{font-size:10px;margin:3px 0 2px;line-height:1;flex:0 0 auto}
        .tablebox{flex:1 1 auto;min-height:0;overflow:auto;overscroll-behavior:contain}
        .table{width:100%;min-width:0!important;table-layout:fixed;font-size:clamp(13px,1vw,16px)}
        .table th,.table td{padding:5px 2px;line-height:1.18;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .table th{top:0;font-size:clamp(12px,.92vw,15px)}
        .table th:nth-child(1),.table td:nth-child(1){width:2.3%}
        .table th:nth-child(2),.table td:nth-child(2){width:7.2%}
        .table th:nth-child(3),.table td:nth-child(3){width:5.5%}
        .table th:nth-child(4),.table td:nth-child(4){width:6.1%}
        .table th:nth-child(7),.table td:nth-child(7){width:5.8%}
        .table th:nth-child(13),.table td:nth-child(13){width:5.8%}
        .table th:nth-child(19),.table td:nth-child(19){width:6.0%}
        .table th:nth-child(20),.table td:nth-child(20){width:7.0%}
        .table th:nth-child(21),.table td:nth-child(21){width:4.5%}
        .table th:nth-child(22),.table td:nth-child(22){width:3.5%}
        .score{font-size:18px}
        .bar{width:34px;height:3px;margin-left:2px}
        .cov,.status,.sig,.conf{font-size:12px}
        .conf{font-weight:900;text-align:center!important}
        .foot{padding:2px;font-size:7px;line-height:1;flex:0 0 auto;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      }
      @media (min-width:901px) and (max-height:820px){
        .candidatePanel{max-height:116px}
        .candidateGrid{grid-template-columns:repeat(auto-fit,minmax(160px,1fr))}
        .candidateSub{display:none}
        .note{display:none}
        .research{font-size:7.5px}
      }
    `;
    document.head.appendChild(style);
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',installRevivalDesktopFit,{once:true});
  else installRevivalDesktopFit();
})();
