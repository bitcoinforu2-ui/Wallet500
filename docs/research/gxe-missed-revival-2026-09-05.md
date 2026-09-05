# GXE missed-revival learning case — 2026-09-05

Status: `MISSED_RESEARCH_REVIVAL / NOT_PROVEN_EXECUTABLE_WINNER`

This record is diagnostic only. It MUST NOT be counted retroactively as a Wallet500 REAL ALERT, paper entry, win, or track-record call.

## User-observed move

At approximately 2026-09-05 21:10 Asia/Jerusalem (18:10 UTC), the user supplied a live GXE/USDT spot screenshot showing approximately +177.05% and a displayed price near 0.00017000 USDT. The visible order book was thin and spread-heavy, so the screenshot proves a price move but does not by itself prove safe executable liquidity.

## Exact identity

- Project: PROJECT XENO / XENO Governance Token
- Symbol: GXE
- Contract: `0x510975eda48a97e0ca228dd04d1217292487bea6`
- Networks publicly documented: Ethereum / BNB Smart Chain
- Gate startup/trading history dates to April 2023, well beyond the Wallet500 180-day veteran threshold.

Public identity references:
- https://www.gate.com/announcements/article/30433
- https://etherscan.io/token/0x510975eda48a97e0ca228dd04d1217292487bea6
- https://www.coingecko.com/en/coins/project-xeno

## What Wallet500 missed

The exact GXE contract was absent from the production repository before this case. The CEX Spot collector already covered Gate, MEXC, OKX and KuCoin, but two generic gaps prevented reliable early research promotion:

1. `data/cex-spot-revival-radar.json` on main was still timestamped 2026-09-05T07:23:03Z near the time of the user-observed 18:10Z move. Per-scan acceleration therefore lacked a reliably published 15-minute baseline.
2. The veteran DEX bridge accepted CEX Spot watches only when an exact symbol identity had already been manually seeded in `data/cex-identity-registry.json`. GXE was not seeded. Symbol-only promotion was correctly forbidden, but there was no strict automatic path from a new Spot watch to exact identity research.

## Repair

PR #85 adds a generic repair, not a GXE exception:

- dynamic CEX Spot identity resolution: strict CoinGecko identity coherence -> >=180d age evidence -> exact chain+contract -> exact-address DEX pair;
- fail closed on ambiguity or provider failure;
- self-register an identity seed only after all strict exact-identity checks pass;
- never overwrite a conflicting existing registry entry;
- independent 15-minute CEX Spot fast lane that persists radar/state so acceleration is measured from a fresh baseline;
- regression tests for the GXE-class gap.

## Hard gates unchanged

- symbol-only is never actionable;
- CEX-only is never a REAL ALERT;
- exact on-chain identity and exact DEX pair remain mandatory;
- execution-pool liquidity >= $50K remains mandatory for production eligibility;
- survival, holder/cluster and manipulation gates remain mandatory;
- no automatic real-money execution;
- this historical case is never rewritten into the official track record.

## Learning conclusion

GXE demonstrates a **coverage/identity/freshness false negative**, not evidence that Wallet500 should loosen its trading gates. A thin CEX spike should be surfaced early as research when identity can be verified, while remaining blocked from REAL ALERT/BUY unless exact executable liquidity and all production truth gates pass.
