from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA=Path('data'); EVM={'ethereum','eth','bsc','bnb','base','arbitrum','optimism','polygon','avalanche'}
def load(p:Path,d:Any):
    try:return json.loads(p.read_text()) if p.exists() and p.stat().st_size else d
    except Exception:return d
def write(p:Path,x:Any):p.write_text(json.dumps(x,indent=2,ensure_ascii=False),encoding='utf-8')
def norm_key(v):
    s=str(v or ''); parts=s.split(':')
    if len(parts)>=3 and parts[0].lower() in EVM:return ':'.join([parts[0].lower(),parts[1].lower(),parts[2].lower()])
    return s
def enrich_positions(positions,records,candidates):
    rec={norm_key(x.get('key')):x for x in records if isinstance(x,dict) and x.get('key')};can={norm_key(x.get('key')):x for x in candidates if isinstance(x,dict) and x.get('key')};out=[]
    for pos in positions:
        if not isinstance(pos,dict):continue
        x=dict(pos);k=norm_key(x.get('key'));r=rec.get(k);c=can.get(k)
        if r:
            x['entry_signal_dna']=r.get('t0_signal_dna');x['entry_revival_phase']=r.get('t0_revival_phase');x['entry_wallet_intent']=r.get('t0_wallet_intent');x['entry_expected_value']=r.get('t0_expected_value');x['signal_dna_t0_at']=r.get('t0_at');x['signal_dna_immutable_t0']=r.get('immutable_t0') is True
        elif c:
            x['entry_signal_dna']=c.get('signal_dna');x['entry_revival_phase']=c.get('revival_phase');x['entry_wallet_intent']=c.get('wallet_intent');x['entry_expected_value']=c.get('expected_value');x['signal_dna_t0_at']=c.get('observed_at');x['signal_dna_immutable_t0']=False
        out.append(x)
    return out
def run(root:Path=DATA):
    ledger=load(root/'real-alert-10usd-ledger.json',{});summary=load(root/'real-alert-10usd-summary.json',{});dna=load(root/'signal-dna-ledger.json',{});sig=load(root/'signal-intelligence.json',{});records=dna.get('records') or [];candidates=sig.get('candidates') or [];stamp=datetime.now(timezone.utc).isoformat();positions=enrich_positions(list(summary.get('positions') or []),records,candidates);summary['positions']=positions;summary['signal_intelligence_enriched_at']=stamp
    by={str(x.get('key')):x for x in positions if isinstance(x,dict)};ledger['positions']=[by.get(str(x.get('key')),x) for x in list(ledger.get('positions') or []) if isinstance(x,dict)];ledger['signal_intelligence_enriched_at']=stamp;write(root/'real-alert-10usd-summary.json',summary);write(root/'real-alert-10usd-ledger.json',ledger);return {'positions':len(positions),'enriched':sum(1 for x in positions if x.get('entry_signal_dna'))}
if __name__=='__main__':print(json.dumps(run(),indent=2))
