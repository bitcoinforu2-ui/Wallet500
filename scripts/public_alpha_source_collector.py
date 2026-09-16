from __future__ import annotations
import json,re
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError

ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/'data/alpha-caller-sources.json'; STATE=ROOT/'data/alpha-caller-source-state.json'; INBOX=ROOT/'data/alpha-caller-inbox.json'
UA='Wallet500-PublicAlphaCollector/1.0'
SOL=re.compile(r'(?<![1-9A-HJ-NP-Za-km-z])([1-9A-HJ-NP-Za-km-z]{32,44})(?![1-9A-HJ-NP-Za-km-z])')
EVM=re.compile(r'0x[a-fA-F0-9]{40}')

def now():return datetime.now(timezone.utc).isoformat()
def text(url,timeout=15):
    try:
        with urlopen(Request(url,headers={'User-Agent':UA,'Accept':'text/html,application/xhtml+xml'}),timeout=timeout) as r:return r.read().decode('utf-8','ignore')
    except (HTTPError,URLError,TimeoutError,OSError):return None

def main():
    cfg=json.loads(CFG.read_text()); state=json.loads(STATE.read_text()) if STATE.exists() else {'sources':{},'seen_contracts':{}}
    inbox=json.loads(INBOX.read_text()) if INBOX.exists() else {'version':1,'calls':[]}; calls=inbox.setdefault('calls',[])
    existing={(str(x.get('source')),str(x.get('network')),str(x.get('contract')).lower()) for x in calls}
    added=0; health={}; seen=state.setdefault('seen_contracts',{})
    for s in cfg.get('sources') or []:
        if not s.get('enabled'):continue
        body=text(s['url']); sid=s['id']; observed=now()
        if body is None:
            health[sid]={'status':'ERROR','observed_at':observed};continue
        # Discovery is deliberately conservative: source observation time is NOT represented as the caller's original call time.
        candidates=[]
        for ca in set(EVM.findall(body)):candidates.append(('eth',ca))
        for ca in set(SOL.findall(body)):
            if len(ca)>=32 and not ca.startswith('http'):candidates.append(('solana',ca))
        accepted=0
        for network,ca in candidates[:250]:
            key=f'{sid}:{network}:{ca.lower()}'
            if key in seen:continue
            seen[key]={'first_seen_at':observed,'source_url':s['url']}
            # Keep discovery separate from caller credit. Caller=source consensus and confidence is capped.
            row={'caller':'SWARM_PUBLIC_DISCOVERY','source':'SWARM Public Terminal','contract':ca,'network':network,'called_at':observed,'source_url':s['url'],'caller_strength':25,'caller_confidence':min(45,float(s.get('confidence_cap',45))),'timestamp_semantics':'WALLET500_FIRST_SEEN_NOT_ORIGINAL_CALL','discovery_only':True}
            ek=(row['source'],network,ca.lower())
            if ek not in existing:
                calls.append(row);existing.add(ek);added+=1;accepted+=1
        health[sid]={'status':'OK','observed_at':observed,'raw_candidates':len(candidates),'new_discoveries':accepted,'timestamp_semantics':'wallet500_first_seen'}
    # Bound inbox growth; reputation history is persisted separately after gating.
    if len(calls)>2000: inbox['calls']=calls[-2000:]
    inbox['updated_at']=now(); INBOX.write_text(json.dumps(inbox,indent=2,ensure_ascii=False)+'\n')
    state['updated_at']=now();state['sources']=health;STATE.write_text(json.dumps(state,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'status':'OK','new_public_discoveries':added,'sources':health,'free_only':True}))
if __name__=='__main__':main()
