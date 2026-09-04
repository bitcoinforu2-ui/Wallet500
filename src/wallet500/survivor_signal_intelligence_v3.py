from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import median

DATA = Path("data")
WATCH = DATA / "survivor-wave-watch.json"
STATE = DATA / "survivor-signal-enhancer-state.json"
OUT = DATA / "survivor-signal-intelligence-v3.json"


def load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def dump(path: Path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def f(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def clamp(v, lo=0, hi=100):
    return max(lo, min(hi, int(round(v))))


def med(values):
    vals = [f(x) for x in values]
    vals = [x for x in vals if x is not None]
    return median(vals) if vals else None


def ratio(a, b):
    a, b = f(a), f(b)
    if a is None or b in (None, 0):
        return None
    return a / b


def token_key(row):
    return f"{str(row.get('chain')).lower()}:{str(row.get('token')).lower()}:{str(row.get('pair_address')).lower()}"


def buy_quality(row):
    buys = f(row.get("buys_h1"))
    sells = f(row.get("sells_h1"))
    bsr = f(row.get("buy_sell_ratio_h1"))
    coverage = {
        "buy_sell_count": "VERIFIED_AGGREGATE" if buys is not None and sells is not None else "INSUFFICIENT_COVERAGE",
        "buy_sell_usd": "INSUFFICIENT_COVERAGE",
        "unique_buyers": "INSUFFICIENT_COVERAGE",
        "median_trade_size": "INSUFFICIENT_COVERAGE",
    }
    score = 0
    reasons = []
    if bsr is not None:
        if bsr >= 1.5: score += 45; reasons.append("STRONG_BUY_COUNT_PRESSURE")
        elif bsr >= 1.25: score += 35; reasons.append("BUY_COUNT_PRESSURE")
        elif bsr >= 1.05: score += 15; reasons.append("MILD_BUY_COUNT_PRESSURE")
        elif bsr < 0.9: score -= 20; reasons.append("SELL_COUNT_PRESSURE")
    if buys is not None and sells is not None and buys + sells >= 200:
        score += 15; reasons.append("MEANINGFUL_TX_SAMPLE")
    return {
        "score": clamp(score),
        "status": "PARTIAL_COUNT_BASED_ONLY" if bsr is not None else "INSUFFICIENT_COVERAGE",
        "reasons": reasons,
        "coverage": coverage,
        "warning": "No buy/sell USD or unique-buyer source is currently available; count pressure is not treated as capital flow.",
    }


def relative_anomaly(row, history):
    cur_turn = f(row.get("turnover_h1")); cur_vol = f(row.get("volume_h1_usd")); cur_bsr = f(row.get("buy_sell_ratio_h1"))
    prior = history[:-1][-5:] if history else []
    if len(prior) < 2:
        return {"status": "INSUFFICIENT_HISTORY", "score": 0, "history_n": len(prior)}
    mt = med([x.get("turnover_h1") for x in prior]); mv = med([x.get("volume_h1_usd") for x in prior]); mb = med([x.get("buy_sell_ratio_h1") for x in prior])
    tr = ratio(cur_turn, mt); vr = ratio(cur_vol, mv); br = ratio(cur_bsr, mb)
    score = 0; reasons = []
    if tr is not None and tr >= 2: score += 40; reasons.append("TURNOVER_2X_BASELINE")
    elif tr is not None and tr >= 1.5: score += 25; reasons.append("TURNOVER_1_5X_BASELINE")
    if vr is not None and vr >= 2: score += 30; reasons.append("VOLUME_2X_BASELINE")
    elif vr is not None and vr >= 1.5: score += 20; reasons.append("VOLUME_1_5X_BASELINE")
    if br is not None and br >= 1.2: score += 20; reasons.append("BUY_PRESSURE_ABOVE_BASELINE")
    return {"status": "RELATIVE_ANOMALY" if score >= 50 else "NORMAL_RANGE", "score": clamp(score),
            "history_n": len(prior), "turnover_vs_median": round(tr,3) if tr is not None else None,
            "volume_vs_median": round(vr,3) if vr is not None else None,
            "buy_ratio_vs_median": round(br,3) if br is not None else None, "reasons": reasons}


def anti_dna(row, history):
    p1=f(row.get("price_change_h1_pct")); p6=f(row.get("price_change_h6_pct")); p24=f(row.get("price_change_h24_pct"))
    bsr=f(row.get("buy_sell_ratio_h1")); liq=f(row.get("liquidity_usd")); vol=f(row.get("volume_h1_usd")); turn=f(row.get("turnover_h1"))
    prior = history[-2] if len(history) >= 2 else None
    score=0; reasons=[]
    if bsr is not None and bsr < 0.9: score += 25; reasons.append("SELL_PRESSURE")
    if p1 is not None and p1 < -12: score += 20; reasons.append("SHARP_H1_DECLINE")
    if p6 is not None and p6 < -25: score += 15; reasons.append("DEEP_H6_DECLINE")
    if p24 is not None and p24 < -45: score += 15; reasons.append("DEEP_H24_DECLINE")
    if prior:
        prev_liq=f(prior.get("liquidity_usd"))
        if liq is not None and prev_liq not in (None,0) and liq/prev_liq < 0.85:
            score += 25; reasons.append("LIQUIDITY_BLEED_GT15PCT")
    if turn is not None and turn >= 0.75 and bsr is not None and bsr < 1.0:
        score += 15; reasons.append("HIGH_TURNOVER_WITHOUT_BUY_DOMINANCE")
    if vol is not None and liq not in (None,0) and vol/liq >= 2.5 and bsr is not None and bsr <= 1.05:
        score += 15; reasons.append("HIGH_ACTIVITY_WEAK_DIRECTIONAL_QUALITY")
    return {"score": clamp(score), "status": "FAILURE_DNA_HIGH" if score >= 60 else "FAILURE_DNA_MEDIUM" if score >= 35 else "FAILURE_DNA_LOW", "reasons": reasons}


def exitability(row, history):
    liq=f(row.get("liquidity_usd")); turn=f(row.get("turnover_h1")); prior=history[-2] if len(history)>=2 else None
    if liq is None:
        return {"status":"INSUFFICIENT_COVERAGE","score":0,"simulated_slippage":"INSUFFICIENT_COVERAGE"}
    score=0; reasons=[]
    if liq >= 500000: score += 50; reasons.append("DEEP_LIQUIDITY")
    elif liq >= 200000: score += 40; reasons.append("GOOD_LIQUIDITY")
    elif liq >= 100000: score += 30; reasons.append("MODERATE_LIQUIDITY")
    elif liq >= 50000: score += 20; reasons.append("MINIMUM_SURVIVAL_LIQUIDITY")
    if prior:
        pl=f(prior.get("liquidity_usd"))
        if pl not in (None,0):
            d=(liq/pl-1)*100
            if d >= -5: score += 25; reasons.append("LIQUIDITY_STABLE")
            elif d < -15: score -= 20; reasons.append("LIQUIDITY_DETERIORATING")
    if turn is not None and 0.1 <= turn <= 2.0: score += 15; reasons.append("ACTIVE_BUT_NOT_EXTREME_TURNOVER")
    return {"score":clamp(score),"status":"EXITABILITY_PROXY_STRONG" if score>=70 else "EXITABILITY_PROXY_OK" if score>=45 else "EXITABILITY_PROXY_WEAK",
            "reasons":reasons,"simulated_slippage":"INSUFFICIENT_COVERAGE","note":"Proxy only; no order-book/route slippage simulation source connected."}


def volume_authenticity(row):
    b=f(row.get("buys_h1")); s=f(row.get("sells_h1")); turn=f(row.get("turnover_h1")); bsr=f(row.get("buy_sell_ratio_h1"))
    score=50; reasons=[]
    if b is None or s is None or turn is None:
        return {"status":"INSUFFICIENT_COVERAGE","score":None,"reasons":[],"coverage":"No transaction-level flow graph"}
    n=b+s
    if n >= 200: score += 10; reasons.append("BROAD_TX_COUNT")
    if bsr is not None and (bsr >= 1.25 or bsr <= 0.8): score += 10; reasons.append("DIRECTIONAL_IMBALANCE_PRESENT")
    if turn > 3: score -= 20; reasons.append("EXTREME_TURNOVER_REVIEW")
    return {"status":"AGGREGATE_ONLY_REVIEW","score":clamp(score),"reasons":reasons,
            "coverage":"INSUFFICIENT_FOR_WASH_TRADING_PROOF","warning":"Cannot certify organic volume without transaction-level wallet graph and repeated-size analysis."}


def whale_cluster_quality(row):
    holder = row.get("holder_delta_since_prior_hourly_snapshot")
    org = row.get("organic_acceleration_score")
    kol = row.get("kol_independent_groups")
    return {"status":"INSUFFICIENT_COVERAGE","whale_intent":"INSUFFICIENT_COVERAGE","independent_buyer_clusters":"INSUFFICIENT_COVERAGE",
            "holder_delta":holder,"organic_acceleration_score":org,"kol_independent_groups":kol,
            "note":"No timestamp-safe wallet-flow/cluster source is connected to this hourly survivor feed."}


def catalyst_quality(row):
    listing=int(f(row.get("listing_evidence_count")) or 0); kol=f(row.get("kol_independent_groups")); org=f(row.get("organic_acceleration_score"))
    score=0; reasons=[]
    if listing>0: score+=30; reasons.append("LISTING_EVIDENCE_PRESENT_UNGRADED")
    if kol is not None and kol>=2: score+=25; reasons.append("KOL_CONVERGENCE")
    if org is not None and org>=60: score+=25; reasons.append("ORGANIC_SOCIAL_ACCELERATION")
    return {"score":clamp(score),"status":"PARTIAL" if reasons else "INSUFFICIENT_COVERAGE","reasons":reasons,
            "warning":"Listing credibility remains ungraded unless source-level provenance is available."}


def net_opportunity(row, anti, rel, buyq, exitq):
    pre=f((row.get("pre_high") or {}).get("score")) or f(row.get("research_confidence")) or 0
    pos = pre*0.45 + rel.get("score",0)*0.25 + buyq.get("score",0)*0.15 + exitq.get("score",0)*0.15
    net = clamp(pos - anti.get("score",0)*0.55)
    if anti.get("score",0)>=60: stage="RISK_SUPPRESSED"
    elif net>=75: stage="PRE_WAVE_PRIORITY"
    elif net>=55: stage="PRE_HIGH_PRIORITY"
    elif net>=35: stage="WATCH"
    else: stage="LOW_PRIORITY"
    return {"score":net,"stage":stage,"positive_component":round(pos,1),"anti_dna_penalty":round(anti.get("score",0)*0.55,1)}


def main():
    watch=load(WATCH,{})
    state=load(STATE,{"tokens":{}})
    rows=[]
    stage_counts={}
    for row in watch.get("tokens") or []:
        hist=((state.get("tokens") or {}).get(token_key(row)) or {}).get("history") or []
        bq=buy_quality(row); ra=relative_anomaly(row,hist); ad=anti_dna(row,hist); ex=exitability(row,hist); va=volume_authenticity(row); wc=whale_cluster_quality(row); cq=catalyst_quality(row)
        net=net_opportunity(row,ad,ra,bq,ex)
        layer={"buy_quality":bq,"relative_anomaly":ra,"failure_anti_dna":ad,"exitability":ex,"volume_authenticity":va,"whale_cluster_quality":wc,"catalyst_quality":cq,"net_opportunity":net,
               "pre_wave_probability":{"status":"INSUFFICIENT_SAMPLE","probability":None},"time_to_wave":{"status":"INSUFFICIENT_SAMPLE","bucket":None}}
        row["intelligence_v3"]=layer
        row["net_opportunity_score"]=net["score"]
        row["net_opportunity_stage"]=net["stage"]
        stage_counts[net["stage"]]=stage_counts.get(net["stage"],0)+1
        rows.append({"chain":row.get("chain"),"token":row.get("token"),"pair_address":row.get("pair_address"),"net_opportunity_score":net["score"],"net_opportunity_stage":net["stage"],"intelligence_v3":layer})
    watch["research_layers_v3"]={"version":"SURVIVOR_SIGNAL_INTELLIGENCE_V3","research_only":True,"production_gates_changed":False,
        "features":["BUY_QUALITY_PARTIAL","RELATIVE_ANOMALY","FAILURE_ANTI_DNA","EXITABILITY_PROXY","VOLUME_AUTHENTICITY_GUARD","WHALE_CLUSTER_COVERAGE_GUARD","CATALYST_QUALITY_PARTIAL","NET_OPPORTUNITY","PRE_WAVE_PROBABILITY_GATED","TIME_TO_WAVE_GATED"],
        "stage_counts":stage_counts,"probability_policy":"No probability or time-to-wave estimate until forward-validation sample is sufficient and calibrated.",
        "coverage_policy":"Unverified wallet, whale, cluster, USD-flow, slippage and transaction-graph fields remain INSUFFICIENT_COVERAGE."}
    dump(WATCH,watch)
    dump(OUT,{"version":3,"generated_at":watch.get("generated_at"),"research_only":True,"production_gates_changed":False,"stage_counts":stage_counts,"tokens":rows})
    print(json.dumps({"enhanced_v3":len(rows),"stage_counts":stage_counts,"production_gates_changed":False}))


if __name__ == "__main__":
    main()
