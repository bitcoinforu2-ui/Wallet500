from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DATA = Path("data")
INPUT = DATA / "smart-buyer-observations.json"
OUTPUT = DATA / "smart-buyer-conviction.json"
VERSION = 1

SEVERE_FLAGS = {"dev", "developer", "bundler", "wash_trader", "wash", "rat", "rat_trader"}
STRONG_FLAGS = {"sniper"}
FRESH_FLAGS = {"fresh_wallet", "fresh"}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _num(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    parsed = _num(value)
    return max(0, int(parsed)) if parsed is not None else None


def _bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _ratio(value: Any) -> float | None:
    parsed = _num(value)
    if parsed is None:
        return None
    if parsed > 1.0:
        parsed /= 100.0
    return _clamp(parsed)


def _percent_fraction(value: Any) -> float | None:
    parsed = _num(value)
    if parsed is None:
        return None
    return _clamp(parsed / 100.0)


def _flag_set(value: Any) -> frozenset[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set, frozenset)):
        return frozenset()
    return frozenset(str(x).strip().lower().replace("-", "_") for x in value if str(x).strip())


def _norm_chain(value: Any) -> str:
    return str(value or "").strip().lower()


def _identity_key(chain: Any, token: Any) -> str | None:
    c = _norm_chain(chain)
    t = str(token or "").strip()
    if not c or not t:
        return None
    if c in {
        "ethereum", "bsc", "base", "arbitrum", "optimism", "polygon",
        "avalanche", "fantom", "linea", "zksync", "mantle", "scroll", "blast",
    }:
        t = t.lower()
    return f"{c}:{t}"


def _mean(values: Iterable[float], default: float = 0.5) -> float:
    values = list(values)
    return sum(values) / len(values) if values else default


@dataclass(frozen=True)
class BuyerObservation:
    wallet: str
    buy_usd: float | None = None
    sell_usd: float | None = None
    current_position_usd: float | None = None
    realized_pnl_30d: float | None = None
    win_rate_30d: float | None = None
    trades_30d: int | None = None
    winners_2x_30d: int | None = None
    winners_5x_30d: int | None = None
    hold_minutes: float | None = None
    entry_move_pct: float | None = None
    supply_pct: float | None = None
    is_accumulating: bool | None = None
    flags: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "BuyerObservation":
        accumulating = _bool(row.get("is_accumulating"))
        supply_pct = _percent_fraction(
            row.get("supply_pct")
            if "supply_pct" in row
            else row.get("supply_share_pct")
        )
        if supply_pct is None and "supply_ratio" in row:
            supply_pct = _ratio(row.get("supply_ratio"))
        return cls(
            wallet=str(row.get("wallet") or row.get("address") or "").strip(),
            buy_usd=_num(row.get("buy_usd") if "buy_usd" in row else row.get("bought_usd")),
            sell_usd=_num(row.get("sell_usd") if "sell_usd" in row else row.get("sold_usd")),
            current_position_usd=_num(
                row.get("current_position_usd")
                if "current_position_usd" in row
                else row.get("position_usd")
            ),
            realized_pnl_30d=_num(
                row.get("realized_pnl_30d")
                if "realized_pnl_30d" in row
                else row.get("pnl_30d")
            ),
            win_rate_30d=_ratio(
                row.get("win_rate_30d")
                if "win_rate_30d" in row
                else row.get("win_rate")
            ),
            trades_30d=_int(row.get("trades_30d") if "trades_30d" in row else row.get("trades")),
            winners_2x_30d=_int(
                row.get("winners_2x_30d")
                if "winners_2x_30d" in row
                else row.get("winners_2x")
            ),
            winners_5x_30d=_int(
                row.get("winners_5x_30d")
                if "winners_5x_30d" in row
                else row.get("winners_5x")
            ),
            hold_minutes=_num(row.get("hold_minutes")),
            entry_move_pct=_num(
                row.get("entry_move_pct")
                if "entry_move_pct" in row
                else row.get("entry_price_move_pct")
            ),
            supply_pct=supply_pct,
            is_accumulating=accumulating,
            flags=_flag_set(row.get("flags") or row.get("labels")),
        )


@dataclass(frozen=True)
class SmartBuyerConvictionResult:
    available: bool
    score: float
    confidence: float
    wallet_count: int
    qualified_wallets: int
    components: dict[str, float]
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["confidence"] = round(self.confidence, 3)
        payload["score"] = round(self.score, 1)
        payload["components"] = {k: round(v, 1) for k, v in self.components.items()}
        payload["reasons"] = list(self.reasons)
        payload["warnings"] = list(self.warnings)
        return payload


def _metric_completeness(obs: BuyerObservation) -> float:
    metrics = (
        obs.buy_usd,
        obs.sell_usd,
        obs.current_position_usd,
        obs.realized_pnl_30d,
        obs.win_rate_30d,
        obs.trades_30d,
        obs.entry_move_pct,
        obs.supply_pct,
    )
    return sum(x is not None for x in metrics) / len(metrics)


def _quality(obs: BuyerObservation) -> float:
    parts: list[tuple[float, float]] = []

    if obs.win_rate_30d is not None:
        trades = obs.trades_30d or 0
        prior_strength = 16.0
        shrunk = (obs.win_rate_30d * trades + 0.5 * prior_strength) / (trades + prior_strength)
        parts.append((shrunk, 0.42))

    if obs.realized_pnl_30d is not None:
        pnl_score = 0.5 + 0.5 * math.tanh(obs.realized_pnl_30d / 15_000.0)
        parts.append((_clamp(pnl_score), 0.33))

    trades = obs.trades_30d or 0
    if trades > 0 and (obs.winners_2x_30d is not None or obs.winners_5x_30d is not None):
        x2 = obs.winners_2x_30d or 0
        x5 = obs.winners_5x_30d or 0
        hit_rate = _clamp((x2 + 2.5 * x5) / max(8.0, float(trades) * 0.35))
        parts.append((hit_rate, 0.25))

    if not parts:
        score = 0.5
    else:
        denom = sum(weight for _, weight in parts)
        score = sum(value * weight for value, weight in parts) / denom

    if obs.flags & SEVERE_FLAGS:
        score *= 0.25
    elif obs.flags & STRONG_FLAGS:
        score *= 0.55
    return _clamp(score)


def _timing(obs: BuyerObservation) -> float:
    move = obs.entry_move_pct
    if move is None:
        return 0.5
    if move <= 0:
        return 1.0
    if move <= 25:
        return 0.95
    if move <= 50:
        return 0.78
    if move <= 100:
        return 0.55
    if move <= 200:
        return 0.30
    return 0.12


def _retention(obs: BuyerObservation) -> float:
    parts: list[float] = []
    if obs.buy_usd is not None and obs.buy_usd > 0 and obs.current_position_usd is not None:
        parts.append(_clamp(obs.current_position_usd / obs.buy_usd))
    if obs.buy_usd is not None and obs.buy_usd > 0 and obs.sell_usd is not None:
        parts.append(_clamp(1.0 - obs.sell_usd / obs.buy_usd))
    if obs.is_accumulating is not None:
        parts.append(0.9 if obs.is_accumulating else 0.25)
    return _mean(parts)


def _flow(obs: BuyerObservation, liquidity_usd: float | None) -> float:
    if obs.buy_usd is None:
        return 0.5
    net = max(0.0, obs.buy_usd - max(0.0, obs.sell_usd or 0.0))
    if net <= 0:
        return 0.1
    if liquidity_usd and liquidity_usd > 0:
        fraction = net / liquidity_usd
        return _clamp(math.log1p(fraction * 100.0) / math.log1p(10.0))
    return _clamp(math.log1p(net) / math.log1p(25_000.0))


def _sample_reliability(obs: BuyerObservation) -> float:
    if obs.trades_30d is None:
        return 0.55
    return _clamp(math.log1p(obs.trades_30d) / math.log1p(60.0), 0.15, 1.0)


def score_buyers(
    observations: Iterable[BuyerObservation],
    *,
    liquidity_usd: float | None = None,
) -> SmartBuyerConvictionResult:
    buyers = [x for x in observations if x.wallet]
    if not buyers:
        return SmartBuyerConvictionResult(
            available=False,
            score=50.0,
            confidence=0.0,
            wallet_count=0,
            qualified_wallets=0,
            components={},
            reasons=(),
            warnings=("NO_SMART_BUYER_DATA",),
        )

    if not any(_metric_completeness(x) > 0.0 or x.is_accumulating is not None or x.flags for x in buyers):
        return SmartBuyerConvictionResult(
            available=False,
            score=50.0,
            confidence=0.0,
            wallet_count=len(buyers),
            qualified_wallets=0,
            components={},
            reasons=(),
            warnings=("INSUFFICIENT_BUYER_METRICS",),
        )

    qualities = [_quality(x) for x in buyers]
    timings = [_timing(x) for x in buyers]
    retentions = [_retention(x) for x in buyers]
    flows = [_flow(x, liquidity_usd) for x in buyers]

    qualified_idx = [
        i for i, (obs, quality) in enumerate(zip(buyers, qualities))
        if quality >= 0.62 and not (obs.flags & (SEVERE_FLAGS | STRONG_FLAGS))
    ]
    qualified = len(qualified_idx)

    overlap = {0: 0.12, 1: 0.28, 2: 0.55, 3: 0.78}.get(qualified, 1.0)

    quality_component = _mean(qualities)
    timing_component = _mean(timings)
    retention_component = _mean(retentions)
    flow_component = _mean(flows)

    max_supply = max((x.supply_pct or 0.0) for x in buyers)
    combined_supply = min(1.0, sum((x.supply_pct or 0.0) for x in buyers))
    concentration = max(max_supply, combined_supply * 0.55)
    if concentration <= 0.10:
        concentration_penalty = 0.0
    elif concentration <= 0.25:
        concentration_penalty = (concentration - 0.10) / 0.15 * 12.0
    else:
        concentration_penalty = min(30.0, 12.0 + (concentration - 0.25) / 0.25 * 18.0)

    toxic_count = sum(bool(x.flags & (SEVERE_FLAGS | STRONG_FLAGS)) for x in buyers)
    toxic_share = toxic_count / len(buyers)
    toxic_penalty = min(28.0, toxic_share * 35.0)

    base = 100.0 * (
        0.30 * quality_component
        + 0.25 * overlap
        + 0.15 * flow_component
        + 0.15 * timing_component
        + 0.15 * retention_component
    )
    score = _clamp(base - concentration_penalty - toxic_penalty, 0.0, 100.0)

    completeness = _mean(_metric_completeness(x) for x in buyers)
    reliability = _mean(_sample_reliability(x) for x in buyers)
    sample = _clamp(math.log1p(len(buyers)) / math.log1p(8.0), 0.0, 1.0)
    confidence = _clamp(0.45 * sample + 0.30 * completeness + 0.25 * reliability)

    fresh_share = sum(bool(x.flags & FRESH_FLAGS) for x in buyers) / len(buyers)
    confidence *= 1.0 - min(0.35, fresh_share * 0.35)
    confidence *= 1.0 - min(0.30, toxic_share * 0.30)
    if len(buyers) == 1:
        confidence = min(confidence, 0.42)
        score = min(score, 68.0)
    elif qualified <= 1:
        confidence = min(confidence, 0.62)

    reasons: list[str] = []
    warnings: list[str] = []
    if qualified >= 3:
        reasons.append(f"QUALITY_WALLET_OVERLAP_{qualified}")
    elif qualified == 2:
        reasons.append("QUALITY_WALLET_OVERLAP_2")
    if timing_component >= 0.78:
        reasons.append("EARLY_ENTRY_TIMING")
    if retention_component >= 0.70:
        reasons.append("BUYERS_HOLDING_OR_ACCUMULATING")
    if quality_component >= 0.68:
        reasons.append("STRONG_BUYER_HISTORY")
    if len(buyers) == 1:
        warnings.append("SINGLE_WALLET_EVIDENCE")
    if qualified <= 1:
        warnings.append("LOW_INDEPENDENT_WALLET_OVERLAP")
    if toxic_count:
        warnings.append(f"TOXIC_WALLET_FLAGS_{toxic_count}")
    if fresh_share >= 0.5:
        warnings.append("FRESH_WALLET_SAMPLE_LOW_CONFIDENCE")
    if concentration_penalty >= 5.0:
        warnings.append("BUYER_CONCENTRATION_RISK")
    if timing_component <= 0.35:
        warnings.append("LATE_ENTRY_RISK")

    return SmartBuyerConvictionResult(
        available=True,
        score=score,
        confidence=confidence,
        wallet_count=len(buyers),
        qualified_wallets=qualified,
        components={
            "quality": quality_component * 100.0,
            "overlap": overlap * 100.0,
            "flow": flow_component * 100.0,
            "timing": timing_component * 100.0,
            "retention": retention_component * 100.0,
            "concentration_penalty": concentration_penalty,
            "toxic_penalty": toxic_penalty,
        },
        reasons=tuple(reasons),
        warnings=tuple(warnings),
    )


def _load(path: Path, default: Any) -> Any:
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _token_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    rows = payload.get("tokens")
    if isinstance(rows, list):
        return [x for x in rows if isinstance(x, dict)]
    return []


def build(data_dir: str | Path = DATA) -> dict[str, Any]:
    data = Path(data_dir)
    payload = _load(data / INPUT.name, {})
    rows: list[dict[str, Any]] = []
    for token in _token_rows(payload):
        chain = token.get("chain") or token.get("network") or payload.get("chain") or payload.get("network")
        address = token.get("token_address") or token.get("address") or token.get("mint")
        key = _identity_key(chain, address)
        if not key:
            continue
        buyer_rows = token.get("buyers")
        if buyer_rows is None:
            buyer_rows = token.get("observations")
        buyers = [
            BuyerObservation.from_dict(x)
            for x in (buyer_rows or [])
            if isinstance(x, dict)
        ]
        result = score_buyers(buyers, liquidity_usd=_num(token.get("liquidity_usd")))
        row = {
            "identity_key": key,
            "chain": _norm_chain(chain),
            "token_address": str(address).strip(),
            "symbol": token.get("symbol"),
            **result.to_dict(),
        }
        rows.append(row)

    chains = sorted({x["chain"] for x in rows if x.get("chain")})
    return {
        "version": VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": INPUT.name,
        "network": chains[0] if len(chains) == 1 else None,
        "chains": chains,
        "truth_contract": {
            "whale_size_alone_is_not_smart_money": True,
            "win_rate_is_sample_shrunk": True,
            "single_wallet_confidence_is_capped": True,
            "missing_data_is_unavailable_not_negative": True,
            "score_and_confidence_are_separate": True,
            "toxic_wallet_flags_reduce_conviction": True,
            "fresh_wallet_reduces_confidence_not_hard_blocks": True,
        },
        "counts": {
            "tokens": len(rows),
            "available": sum(1 for x in rows if x["available"]),
            "high_conviction": sum(
                1 for x in rows
                if x["available"] and x["score"] >= 75.0 and x["confidence"] >= 0.65
            ),
        },
        "tokens": rows,
    }


def index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row["identity_key"]: row
        for row in payload.get("tokens") or []
        if isinstance(row, dict) and row.get("identity_key")
    }


def run(data_dir: str | Path = DATA) -> dict[str, Any]:
    data = Path(data_dir)
    payload = build(data)
    _write(data / OUTPUT.name, payload)
    return payload


def main() -> None:
    print(json.dumps(run()["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
