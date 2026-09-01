# Paid Attention Liquidity Quarantine Policy

Paid visibility is a discovery/research trigger only. It never creates BUY or PRE-ALPHA by itself.

## Active Paid Attention Watch
- Exact Solana mint + exact locked pair only.
- Live exact-pair liquidity must be verified and >= $50,000.
- Existing timing, Waking confirmation, holder/wallet/social/whale and risk rules remain unchanged.

## Warning / Learning Quarantine
- Live liquidity < $10,000: `PAID_ATTENTION_PUMP_DUMP_LEARNING`.
- Live liquidity $10,000-$49,999.99: `PAID_ATTENTION_LOW_LIQUIDITY_LEARNING`.
- Live liquidity unavailable/unverified: `PAID_ATTENTION_LIQUIDITY_UNVERIFIED`.
- T0 liquidity >= $50,000 followed by live liquidity < $10,000 is preserved as `POST_PROMOTION_LIQUIDITY_COLLAPSE` evidence.
- T0 liquidity >= $50,000 followed by live liquidity $10,000-$49,999.99 is preserved as `POST_PROMOTION_LIQUIDITY_DRAIN` evidence.

Quarantined rows stay in the learning archive and remain available for pump/dump pattern analysis, but are excluded from the active Paid Attention Watch and cannot affect PRE-ALPHA, BUY, or production portfolio logic.

## Re-entry principle
A quarantined pair is not restored because of one liquidity spike. Re-entry requires fresh verified exact-pair liquidity above the research floor plus the normal survival/confirmation gates on subsequent observations.
