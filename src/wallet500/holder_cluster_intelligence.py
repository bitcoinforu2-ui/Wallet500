from __future__ import annotations

"""Holder / cluster intelligence foundation.

This module is deliberately evidence-first: unknown holder data is never converted
into a reassuring zero. Providers can feed verified holder rows later; until then
Trust Score remains unavailable rather than fabricated.
"""

from collections import defaultdict
from typing import Iterable


def _pct(value, total):
    try:
        value=float(value); total=float(total)
        return (value/total)*100.0 if total>0 else None
    except (TypeError, ValueError):
        return None


def analyze_holders(holders: Iterable[dict] | None, total_supply=None) -> dict:
    rows=[x for x in (holders or []) if isinstance(x,dict)]
    if not rows:
        return {"status":"NO_VERIFIED_HOLDER_DATA","trust_score":None,"holder_count":None,
                "top1_pct":None,"top5_pct":None,"top10_pct":None,"top20_pct":None,
                "effective_cluster_pct":None,"risk_flags":["HOLDER_DATA_UNAVAILABLE"]}

    clean=[]
    for x in rows:
        if x.get("excluded") or x.get("is_lp") or x.get("is_burn"):
            continue
        bal=x.get("balance")
        pct=x.get("supply_pct")
        if pct is None and total_supply not in (None,0): pct=_pct(bal,total_supply)
        try: pct=float(pct)
        except (TypeError,ValueError): continue
        clean.append({**x,"supply_pct":max(0.0,pct)})
    clean.sort(key=lambda x:x["supply_pct"],reverse=True)
    if not clean:
        return {"status":"NO_VERIFIED_HOLDER_DATA","trust_score":None,"holder_count":0,
                "top1_pct":None,"top5_pct":None,"top10_pct":None,"top20_pct":None,
                "effective_cluster_pct":None,"risk_flags":["NO_NON_EXCLUDED_HOLDERS"]}

    def top(n): return round(sum(x["supply_pct"] for x in clean[:n]),4)
    clusters=defaultdict(float)
    for x in clean:
        cid=x.get("cluster_id")
        if cid: clusters[str(cid)]+=x["supply_pct"]
    max_cluster=max(clusters.values(),default=0.0)
    top1,top5,top10,top20=top(1),top(5),top(10),top(20)
    effective=max(top1,max_cluster)
    flags=[]; penalty=0
    if top1>=20: flags.append("SINGLE_HOLDER_GE_20PCT"); penalty+=35
    elif top1>=10: flags.append("SINGLE_HOLDER_GE_10PCT"); penalty+=18
    if top10>=60: flags.append("TOP10_GE_60PCT"); penalty+=30
    elif top10>=40: flags.append("TOP10_GE_40PCT"); penalty+=15
    if max_cluster>=25: flags.append("CONNECTED_CLUSTER_GE_25PCT"); penalty+=35
    elif max_cluster>=15: flags.append("CONNECTED_CLUSTER_GE_15PCT"); penalty+=18
    trust=max(0,min(100,100-penalty))
    level="CRITICAL" if trust<35 else "HIGH_RISK" if trust<60 else "CAUTION" if trust<80 else "DISTRIBUTED"
    return {"status":"VERIFIED","trust_score":trust,"distribution_level":level,
            "holder_count":len(clean),"top1_pct":top1,"top5_pct":top5,"top10_pct":top10,
            "top20_pct":top20,"effective_cluster_pct":round(effective,4),
            "largest_connected_cluster_pct":round(max_cluster,4),"risk_flags":flags}
