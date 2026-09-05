from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
OUTPUT = DATA / "candidate-evidence-envelope.json"
VERSION = 2
MODE = "RESEARCH_ONLY_CANDIDATE_EVIDENCE_ENVELOPE_V1"
MIN_MARKET_AGE_DAYS = 180
MIN_EXECUTION_LIQUIDITY_USD = 50_000.0
MAX_AGE = {"revival":7200,"holder":7200,"wallet":7200,"registry":7200,"precursor":5400,"waking":5400,"cex":2700,"pre_t0":7200}
STRONG_PRECURSOR = {"HIGH_CONVICTION_PRECURSOR","PRE_BREAKOUT_CANDIDATE","EARLY_REVIVAL_WATCH"}
STRONG_WAKING = {"WAKING_CONFIRMED_RESEARCH","WAKING_STRONG_RESEARCH"}


def load(p: Path, default: Any) -> Any:
    try:
        return json.loads(p.read_text()) if p.exists() and p.stat().st_size else default
    except Exception:
        return default


def num(v: Any, d: float = 0.0) -> float:
    try: return float(d if v is None else v)
    except (TypeError, ValueError): return float(d)


def opt(v: Any) -> float | None:
    try: return None if v is None else float(v)
    except (TypeError, ValueError): return None


def integer(v: Any, d: int = 0) -> int:
    try: return int(d if v is None else v)
    except (TypeError, ValueError): return d


def dt(v: Any) -> datetime | None:
    try:
        x = datetime.fromisoformat(str(v).replace("Z","+00:00"))
        return x if x.tzinfo else x.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def fresh(payload: dict, name: str, now: datetime) -> dict:
    stamp = next((payload.get(k) for k in ("generated_at","updated_at","source_generated_at") if payload.get(k)), None)
    parsed = dt(stamp)
    age = None if parsed is None else max(0.0,(now-parsed.astimezone(timezone.utc)).total_seconds())
    return {"generated_at":stamp,"age_seconds":None if age is None else round(age,1),"max_age_seconds":MAX_AGE[name],"fresh":age is not None and age <= MAX_AGE[name]}


def rows(payload: Any, *keys: str) -> list[dict]:
    if not isinstance(payload, dict): return []
    for k in keys:
        v = payload.get(k)
        if isinstance(v, list): return [x for x in v if isinstance(x,dict)]
        if isinstance(v, dict): return [x for x in v.values() if isinstance(x,dict)]
    return []


def token(r: dict) -> str:
    return str(r.get("token_address") or r.get("token") or r.get("mint") or "").strip()


def pair(r: dict) -> str:
    return str(r.get("pair_address") or r.get("dex_pair_address") or r.get("exact_pair") or "").strip()


def index(rs: list[dict]) -> dict[str,dict]:
    return {token(r):r for r in rs if token(r)}


def registry_index(payload: dict) -> dict[str,dict]:
    out = {}
    for r in rows(payload,"event_bridge"):
        t = token(r)
        if t and (t not in out or str(r.get("waking_t0") or "") > str(out[t].get("waking_t0") or "")): out[t]=r
    return out


def pret0_index(payload: dict) -> dict[str,dict]:
    out={}
    for r in rows(payload,"active_deep_watch")+rows(payload,"records"):
        t,p=token(r),pair(r)
        if t and p: out[f"{t}|{p.lower()}"]=r
    return out


def holder_lane(r: dict | None, is_fresh: bool) -> dict:
    r=r or {}; truth=str(r.get("holder_truth_status") or "").upper()
    verified=bool(is_fresh and r.get("growth_eligible") is True and r.get("holder_count") is not None and "VERIFIED" in truth)
    r24=r.get("holder_growth_24h_ready") is True; r7=r.get("holder_growth_7d_ready") is True
    g24=r.get("holder_growth_24h_count"); g7=r.get("holder_growth_7d_count")
    positive=verified and ((r24 and num(g24)>0) or (r7 and num(g7)>0))
    return {"verified":verified,"positive":positive,"status":truth or "MISSING","source":r.get("source") or r.get("provider"),
            "metrics":{"holder_count":r.get("holder_count"),"growth_24h_ready":r24,"growth_24h_count":g24,"growth_24h_pct":r.get("holder_growth_24h_pct"),
                       "growth_7d_ready":r7,"growth_7d_count":g7,"growth_7d_pct":r.get("holder_growth_7d_pct")}}


def wallet_lane(r: dict | None, expected: str, is_fresh: bool) -> dict:
    r=r or {}; c=r.get("coverage") if isinstance(r.get("coverage"),dict) else {}; w=r.get("windows") if isinstance(r.get("windows"),dict) else {}
    h=w.get("h1") if isinstance(w.get("h1"),dict) else {}; rp=pair(r); pair_ok=bool(expected and rp and rp.lower()==expected.lower())
    verified=bool(is_fresh and pair_ok and c.get("coverage_quality")=="ACCEPTABLE" and c.get("coverage_gap") is not True and num(c.get("last_run_resolution_pct"))>=num(c.get("minimum_resolution_pct"),80))
    resolved=integer(h.get("resolved_swaps")); first=integer(h.get("first_seen_buyers_since_monitor_t0")); acc=integer(h.get("net_accumulating_wallets")); dist=integer(h.get("net_distributing_wallets")); ratio=num(h.get("wallet_buy_sell_ratio"))
    positive=verified and resolved>=6 and first>=3 and acc>=3 and acc-dist>=1 and ratio>=1.15
    return {"verified":verified,"positive":positive,"pair_match":pair_ok,"status":"VERIFIED_ACCUMULATION" if positive else ("VERIFIED_NO_ACCUMULATION" if verified else "MISSING_OR_PARTIAL"),
            "metrics":{"resolution_pct":c.get("last_run_resolution_pct"),"resolved_swaps_h1":resolved,"unique_traders_h1":h.get("unique_traders"),"first_seen_buyers_h1":first,"net_accumulating_wallets_h1":acc,"net_distributing_wallets_h1":dist,"wallet_buy_sell_ratio_h1":ratio}}


def smart_lane(r: dict | None, expected: str, is_fresh: bool) -> dict:
    r=r or {}; rp=pair(r); ok=bool(expected and rp and rp.lower()==expected.lower()); verified=bool(is_fresh and ok and r); q=integer(r.get("historically_qualified_pre_waking_buyers"))
    return {"verified":verified,"positive":verified and q>0,"status":"QUALIFIED_PRE_WAKING_BUYERS_PRESENT" if verified and q>0 else ("VERIFIED_NONE" if verified else "MISSING"),
            "metrics":{"verified_wallets_seen":r.get("verified_wallets_seen"),"historically_qualified_pre_waking_buyers":q if verified else None,"waking_t0":r.get("waking_t0")}}


def cex_lane(r: dict | None, expected: str, is_fresh: bool) -> dict:
    r=r or {}; rp=pair(r); pair_ok=bool(expected and rp and rp.lower()==expected.lower())
    verified=bool(is_fresh and pair_ok and (r.get("identity_status")=="DEX_VERIFIED" or r.get("identity_verified") is True) and r.get("market_age_verified") is True and integer(r.get("market_age_min_days"))>=MIN_MARKET_AGE_DAYS)
    score=num(r.get("cex_revival_score")); conf=integer(r.get("coherent_confirmations")); positive=verified and score>=35 and conf>=2
    return {"verified":verified,"positive":positive,"status":"VERIFIED_CEX_REVIVAL" if positive else ("VERIFIED_NO_SIGNAL" if verified else "MISSING"),"metrics":{"score":score if r else None,"coherent_confirmations":conf if r else None}}


def precursor_lane(r: dict | None, expected: str, is_fresh: bool) -> dict:
    r=r or {}; ident=r.get("identity") if isinstance(r.get("identity"),dict) else {}; rp=pair(r); ok=bool(expected and rp and rp.lower()==expected.lower())
    verified=bool(is_fresh and ok and ident.get("exact_mint_verified") is True and ident.get("exact_pair_verified") is True); status=str(r.get("status") or "")
    return {"verified":verified,"positive":verified and status in STRONG_PRECURSOR,"status":status or "MISSING","metrics":{"confidence_adjusted_score":r.get("confidence_adjusted_score"),"available_evidence_score":r.get("normalized_score_available_evidence"),"evidence_coverage_pct":r.get("evidence_coverage_pct")}}


def waking_lane(r: dict | None, expected: str, is_fresh: bool) -> dict:
    r=r or {}; rp=pair(r); ok=bool(expected and rp and rp.lower()==expected.lower()); status=str(r.get("confirmation_status") or ""); verified=bool(is_fresh and ok and r)
    return {"verified":verified,"positive":verified and status in STRONG_WAKING,"status":status or "MISSING","metrics":{"confirmation_score":r.get("confirmation_score")}}


def social_lane(p: dict | None, w: dict | None, pf: bool, wf: bool) -> dict:
    p=p or {}; w=w or {}; ps=(p.get("evidence_snapshot") or {}).get("social") or {}; ws=(w.get("channels") or {}).get("social") or {}; cs=[]
    if pf and ps.get("verified") is True: cs.append(ps)
    if wf and ws.get("verified") is True: cs.append(ws)
    if not cs: return {"verified":False,"positive":False,"status":"MISSING","metrics":{}}
    best=max(cs,key=lambda x:num(x.get("score"))); sig=best.get("signals") if isinstance(best.get("signals"),list) else []; score=num(best.get("score"))
    return {"verified":True,"positive":score>=55 or bool(sig),"status":"VERIFIED_MULTI_SOURCE_SOCIAL","source":best.get("source"),"metrics":{"score":score,"signals":sig}}


def concentration_lane(r: dict | None, is_fresh: bool) -> dict:
    r=r or {}; f=r.get("families") if isinstance(r.get("families"),dict) else {}; c=f.get("concentration") if isinstance(f.get("concentration"),dict) else {}; verified=bool(is_fresh and c.get("verified") is True)
    return {"verified":verified,"positive":False,"role":"RISK_CONTEXT_ONLY_NEVER_POSITIVE_ALPHA","status":c.get("status") or "MISSING","metrics":{"top1_pct":c.get("top1_pct"),"top5_pct":c.get("top5_pct"),"top10_pct":c.get("top10_pct"),"top20_pct":c.get("top20_pct"),"concentration_risk_score":c.get("concentration_risk_score")}}


def risk_blockers(revival: dict, pre: dict | None, pre_fresh: bool) -> list[str]:
    out=[]; comp=revival.get("revival_score_components") if isinstance(revival.get("revival_score_components"),dict) else {}; lc=opt(comp.get("liquidity_change_pct"))
    if lc is not None and lc<=-75: out.append("LIQUIDITY_COLLAPSE_75PCT")
    status=str(revival.get("watch_status") or "")
    if status in {"FAILED_SURVIVAL","PUMP_DUMP_RISK","LATE_MOVE_DO_NOT_CHASE"}: out.append(status)
    c24,c7=opt(revival.get("change_24h_pct")),opt(revival.get("change_7d_pct"))
    if (c24 is not None and c24>=35) or (c7 is not None and c7>=85): out.append("LATE_MOVE_DO_NOT_CHASE")
    c=concentration_lane(pre,pre_fresh)
    if c.get("verified") is True and num((c.get("metrics") or {}).get("concentration_risk_score"))>=90: out.append("EXTREME_CONCENTRATION_RISK")
    return sorted(set(out))


def adaptive(revival: dict, independent: dict[str,dict], pair_verified: bool, pair_positive: bool, precursor: dict, waking: dict) -> dict:
    comp=revival.get("revival_score_components") if isinstance(revival.get("revival_score_components"),dict) else {}; vc=opt(comp.get("pair_volume_change_pct")); lc=opt(comp.get("liquidity_change_pct"))
    c24,c7=opt(revival.get("change_24h_pct")),opt(revival.get("change_7d_pct")); rev=num(revival.get("revival_score_verified")); pos=[k for k,v in independent.items() if v.get("positive") is True]
    vel=0.0; per=0.0; sig=[]; fam=set()
    if vc is not None:
        if vc>=50: vel+=35; sig.append("PAIR_VOLUME_VELOCITY_GE_50PCT"); fam.add("volume")
        elif vc>=20: vel+=25; sig.append("PAIR_VOLUME_VELOCITY_GE_20PCT"); fam.add("volume")
        elif vc>=10: vel+=15; sig.append("PAIR_VOLUME_VELOCITY_GE_10PCT"); fam.add("volume")
        elif vc<=-40: vel-=15; sig.append("PAIR_VOLUME_DECELERATION_LE_40PCT")
    if lc is not None:
        if lc>=15: vel+=20; sig.append("LIQUIDITY_VELOCITY_GE_15PCT"); fam.add("liquidity")
        elif lc>=0: vel+=10; sig.append("LIQUIDITY_STABLE_OR_RISING"); fam.add("liquidity")
        elif lc<=-25: vel-=20; sig.append("LIQUIDITY_DRAIN_LE_25PCT")
    if pos: vel+=min(36,18*len(pos)); sig += [f"POSITIVE_{x}" for x in pos]; fam.update(x.lower() for x in pos)
    if precursor.get("positive") is True: vel+=10; sig.append("PRECURSOR_LANE_POSITIVE"); fam.add("precursor")
    if waking.get("positive") is True: vel+=10; sig.append("WAKING_CONFIRMATION_POSITIVE"); fam.add("waking")
    if pair_verified: per+=35; sig.append("EXACT_PAIR_PERSISTENCE_VERIFIED"); fam.add("pair_survival")
    if pair_positive: per+=25; sig.append("LIQUIDITY_RETENTION_PERSISTENT"); fam.add("pair_survival")
    if lc is not None and lc>=0: per+=15
    if len(pos)>=2: per+=15; sig.append("MULTI_LANE_PERSISTENCE")
    if c24 is not None and -10<=c24<20: per+=10; sig.append("PRICE_NOT_EXTENDED_24H")
    bonus=10 if 50<=rev<65 else (5 if rev>=65 else 0)
    if bonus==10: sig.append("PRE_WAKING_REVIVAL_SETUP"); fam.add("market_setup")
    late=bool((c24 is not None and c24>=35) or (c7 is not None and c7>=85))
    if late: vel-=20; sig.append("LATE_MOVE_RISK")
    vel=max(0,min(100,vel)); per=max(0,min(100,per)); score=max(0,min(100,.65*vel+.35*per+bonus))
    return {"anomaly_score":round(score,2),"velocity_score":round(vel,2),"persistence_score":round(per,2),"signal_family_count":len(fam),"signal_families":sorted(fam),"signals":sorted(set(sig)),
            "pair_volume_change_pct":vc,"liquidity_change_pct":lc,"positive_independent_count":len(pos),"late_move_risk":late,"velocity_positive":vel>=35,"persistence_positive":per>=55,
            "anomaly_positive":score>=35 and len(fam)>=2 and not late,"method":"FORWARD_SNAPSHOT_VELOCITY_PERSISTENCE_PROXY_V1"}


def build(data_dir: Path = DATA, now: datetime | None = None) -> dict:
    now=now or datetime.now(timezone.utc)
    src={n:load(data_dir/f, {}) for n,f in {"revival":"revival-1000-latest.json","holder":"revival-holder-latest.json","wallet":"revival-prewaking-wallet-evidence.json","registry":"revival-wallet-registry.json","precursor":"revival-precursor-latest.json","waking":"waking-confirmation-latest.json","cex":"cex-revival-radar.json","pre_t0":"revival-pre-t0-evidence.json"}.items()}
    fr={n:fresh(src[n],n,now) for n in src}; hidx=index(rows(src["holder"],"coins","tokens")); widx=index(rows(src["wallet"],"tokens")); ridx=registry_index(src["registry"])
    pidx=index(rows(src["precursor"],"targets")); wkidx=index(rows(src["waking"],"targets")); cidx=index(rows(src["cex"],"alerts")); preidx=pret0_index(src["pre_t0"]); out=[]
    for r in rows(src["revival"],"coins"):
        t,p=token(r),pair(r)
        if not t or not p: continue
        exact_id=r.get("network_verified") is True and str(r.get("network") or "").lower()=="solana"; exact_pair=r.get("dex_link_type")=="DEXSCREENER_VERIFIED_PAIR"
        age=integer(r.get("market_age_min_days")); age_ok=r.get("market_age_verified") is True and age>=MIN_MARKET_AGE_DAYS; liq=num(r.get("dex_pair_liquidity_usd")); liq_ok=liq>=MIN_EXECUTION_LIQUIDITY_USD
        rev=num(r.get("revival_score_verified")); watch=str(r.get("watch_status") or ""); market=watch=="WAKING_MARKET_ONLY" or rev>=65
        hl=holder_lane(hidx.get(t),fr["holder"]["fresh"]); wl=wallet_lane(widx.get(t),p,fr["wallet"]["fresh"]); sl=smart_lane(ridx.get(t),p,fr["registry"]["fresh"]); cl=cex_lane(cidx.get(t),p,fr["cex"]["fresh"])
        pl=precursor_lane(pidx.get(t),p,fr["precursor"]["fresh"]); kl=waking_lane(wkidx.get(t),p,fr["waking"]["fresh"]); sol=social_lane(pidx.get(t),wkidx.get(t),fr["precursor"]["fresh"],fr["waking"]["fresh"]); pre=preidx.get(f"{t}|{p.lower()}"); con=concentration_lane(pre,fr["pre_t0"]["fresh"])
        comp=r.get("revival_score_components") if isinstance(r.get("revival_score_components"),dict) else {}; ps_verified=exact_pair and comp.get("same_pair_as_previous") is True; lc=opt(comp.get("liquidity_change_pct")); ps_positive=bool(ps_verified and (lc is None or lc>-50))
        independent={"HOLDER_GROWTH":hl,"WALLET_ACCUMULATION":wl,"SMART_MONEY":sl,"CEX_REVIVAL":cl,"VERIFIED_SOCIAL":sol}; verified=sorted(k for k,v in independent.items() if v.get("verified") is True); positive=sorted(k for k,v in independent.items() if v.get("positive") is True)
        risk=risk_blockers(r,pre,fr["pre_t0"]["fresh"]); hard=bool(exact_id and exact_pair and age_ok and fr["revival"]["fresh"] and not risk); base=bool(hard and liq_ok); vf=(2 if exact_id and exact_pair else 0)+len(verified); ad=adaptive(r,independent,ps_verified,ps_positive,pl,kl)
        ready=bool(base and market and positive and vf>=3 and not ad["late_move_risk"]); pre_ready=bool(base and not market and len(positive)>=2 and vf>=4 and ps_positive and ad["anomaly_score"]>=45 and not ad["late_move_risk"]); anomaly_watch=bool(base and not market and not pre_ready and ad["anomaly_positive"])
        if ready: status,tier="EVIDENCE_READY","WAKING_EVIDENCE_READY"
        elif pre_ready: status,tier="VERIFIED_WATCH","PRE_WAKING_EVIDENCE_READY"
        elif anomaly_watch: status,tier="VERIFIED_WATCH","ANOMALY_WATCH"
        elif base and market: status,tier="VERIFIED_WATCH","WAKING_MARKET_WATCH"
        elif base: status,tier="DEEP_WATCH","BASELINE_DEEP_WATCH"
        else: status,tier="BLOCKED_TRUTH","HARD_TRUTH_BLOCKED"
        blockers=[]
        if not fr["revival"]["fresh"]: blockers.append("REVIVAL_SOURCE_STALE")
        if not exact_id: blockers.append("EXACT_IDENTITY_REQUIRED")
        if not exact_pair: blockers.append("EXACT_PAIR_REQUIRED")
        if not age_ok: blockers.append("MARKET_AGE_180D_REQUIRED")
        if not liq_ok: blockers.append("EXECUTION_LIQUIDITY_LT_50K")
        blockers+=risk
        pending=[]
        if hard and not market: pending.append("MARKET_CONFIRMATION_PENDING")
        if hard and not positive: pending.append("INDEPENDENT_EVIDENCE_PENDING")
        if hard and not ps_verified: pending.append("PAIR_SURVIVAL_CONFIRMATION_PENDING")
        if hard and not hl["verified"]: pending.append("HOLDER_GROWTH_VERIFICATION_PENDING")
        if hard and not wl["verified"]: pending.append("WALLET_COVERAGE_PENDING")
        rescue=bool(hard and ((not liq_ok and liq>=10_000) or status=="DEEP_WATCH") and not ad["late_move_risk"]); delegated="reawakening-shadow.json" if rescue and not liq_ok else None
        out.append({"key":f"solana:{t}:{p.lower()}","chain":"solana","network":"solana","token_address":t,"symbol":r.get("symbol"),"pair_address":p,"dex_url":r.get("dex_link"),"status":status,"discovery_tier":tier,"production_effect":False,"automatic_buy":False,
                    "truth":{"exact_identity_verified":exact_id,"exact_pair_verified":exact_pair,"market_age_verified_180d_plus":age_ok,"market_age_days":age if age_ok else None,"execution_pool_liquidity_usd":liq,"execution_liquidity_floor_passed":liq_ok,"revival_source_fresh":fr["revival"]["fresh"]},
                    "market":{"revival_score_verified":rev,"watch_status":watch,"market_positive":market,"price_usd":r.get("price_usd"),"liquidity_usd":liq,"volume_24h_usd":r.get("dex_pair_volume_24h_usd"),"drawdown_from_ath_pct":r.get("drawdown_from_ath_pct"),"change_24h_pct":r.get("change_24h_pct"),"change_7d_pct":r.get("change_7d_pct"),"liquidity_change_pct":comp.get("liquidity_change_pct"),"pair_volume_change_pct":comp.get("pair_volume_change_pct")},
                    "adaptive_discovery":ad,"families":{"holder_growth":hl,"wallet_accumulation":wl,"smart_money":sl,"cex_revival":cl,"precursor":pl,"waking_confirmation":kl,"social":sol,"pair_survival":{"verified":ps_verified,"positive":ps_positive,"status":"SURVIVED_PREVIOUS_EXACT_PAIR" if ps_verified else "PENDING"},"concentration":con},
                    "coverage":{"verified_independent_lanes":verified,"positive_independent_lanes":positive,"verified_independent_count":len(verified),"positive_independent_count":len(positive),"verified_family_count":vf,"evidence_ready":ready,"pre_waking_evidence_ready":pre_ready,"anomaly_watch":anomaly_watch,"market_confirmation_pending":not market},
                    "rescue_shadow":{"eligible":rescue,"reason":"LIQUIDITY_ONLY_OR_NEAR_LIQUIDITY_REJECT_RECHECK" if rescue and not liq_ok else ("EARLY_SIGNAL_NOT_YET_CONFIRMED_KEEP_FORWARD_WATCH" if rescue else None),"observation_horizons_hours":[6,24,72] if rescue else [],"delegated_to":delegated,"no_hindsight":True},
                    "blockers":sorted(set(blockers)),"pending_confirmations":sorted(set(pending))})
    sp={"EVIDENCE_READY":0,"VERIFIED_WATCH":1,"DEEP_WATCH":2,"BLOCKED_TRUTH":3}; tp={"WAKING_EVIDENCE_READY":0,"PRE_WAKING_EVIDENCE_READY":1,"ANOMALY_WATCH":2,"WAKING_MARKET_WATCH":3,"BASELINE_DEEP_WATCH":4,"HARD_TRUTH_BLOCKED":5}
    out.sort(key=lambda x:(sp.get(x["status"],9),tp.get(x["discovery_tier"],9),-integer(x["coverage"]["positive_independent_count"]),-num(x["adaptive_discovery"]["anomaly_score"]),-num(x["market"]["revival_score_verified"]),-num(x["market"]["liquidity_usd"])))
    count=lambda pred:sum(1 for x in out if pred(x))
    counts={"universe_with_exact_pair":len(out),"evidence_ready":count(lambda x:x["status"]=="EVIDENCE_READY"),"verified_watch":count(lambda x:x["status"]=="VERIFIED_WATCH"),"deep_watch":count(lambda x:x["status"]=="DEEP_WATCH"),"blocked_truth":count(lambda x:x["status"]=="BLOCKED_TRUTH"),
            "pre_waking_evidence_ready":count(lambda x:x["discovery_tier"]=="PRE_WAKING_EVIDENCE_READY"),"anomaly_watch":count(lambda x:x["discovery_tier"]=="ANOMALY_WATCH"),"waking_market_watch":count(lambda x:x["discovery_tier"]=="WAKING_MARKET_WATCH"),"baseline_deep_watch":count(lambda x:x["discovery_tier"]=="BASELINE_DEEP_WATCH"),
            "rescue_shadow_eligible":count(lambda x:x["rescue_shadow"]["eligible"]),"market_confirmation_pending":count(lambda x:"MARKET_CONFIRMATION_PENDING" in x["pending_confirmations"]),"independent_evidence_pending":count(lambda x:"INDEPENDENT_EVIDENCE_PENDING" in x["pending_confirmations"]),
            "adaptive_anomaly_positive":count(lambda x:x["adaptive_discovery"]["anomaly_positive"]),"adaptive_velocity_positive":count(lambda x:x["adaptive_discovery"]["velocity_positive"]),"adaptive_persistence_positive":count(lambda x:x["adaptive_discovery"]["persistence_positive"]),
            "with_verified_holder_growth_lane":count(lambda x:x["families"]["holder_growth"]["verified"]),"with_positive_holder_growth":count(lambda x:x["families"]["holder_growth"]["positive"]),"with_verified_wallet_lane":count(lambda x:x["families"]["wallet_accumulation"]["verified"]),"with_positive_wallet_accumulation":count(lambda x:x["families"]["wallet_accumulation"]["positive"]),"with_positive_smart_money":count(lambda x:x["families"]["smart_money"]["positive"]),"with_positive_cex":count(lambda x:x["families"]["cex_revival"]["positive"])}
    return {"version":VERSION,"mode":MODE,"generated_at":now.isoformat(),"production_change":False,"production_portfolio_impact":"NONE","automatic_buy":False,
            "funnel_policy":{"discovery":"PERMISSIVE_EARLY_ANOMALY_AND_MULTI_LANE_WATCH","confirmation":"MARKET_WAKING_IS_LATE_CONFIRMATION_NOT_EARLY_DISCOVERY_GATE","real_alert":"UNCHANGED_STRICT_DOWNSTREAM_GATE","rescue":"KEEP_EARLY_FALSE_NEGATIVES_ON_FORWARD_SHADOW_WATCH"},
            "truth_contract":{"focus":"VETERAN_COIN_REVIVAL_ONLY","minimum_market_age_days":MIN_MARKET_AGE_DAYS,"minimum_execution_pool_liquidity_usd":MIN_EXECUTION_LIQUIDITY_USD,"exact_identity_required":True,"exact_pair_required":True,"missing_evidence_never_positive":True,"stale_evidence_never_positive":True,"concentration_is_risk_context_only":True,"evidence_ready_is_research_promotion_not_buy_signal":True,"pre_waking_evidence_ready_is_watch_only":True,"market_waking_required_for_early_watch":False,"evidence_ready_requires_market_confirmation":True,"hard_truth_blockers_separate_from_pending_confirmation":True,"adaptive_velocity_uses_forward_snapshot_deltas_only":True,"real_alert_gate_unchanged":True,"solana_mint_authority_must_be_revoked_null":True,"solana_mintable_tokens_allowed":False,"solana_unknown_mintability_allowed":False,"no_hindsight":True},
            "source_freshness":fr,"counts":counts,"candidates":out}


def run(data_dir: Path = DATA) -> dict:
    payload=build(data_dir); data_dir.mkdir(parents=True,exist_ok=True); (data_dir/OUTPUT.name).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); return payload


def main() -> None:
    p=run(); print(json.dumps({"counts":p["counts"],"source_freshness":p["source_freshness"]},ensure_ascii=False))


if __name__=="__main__": main()
