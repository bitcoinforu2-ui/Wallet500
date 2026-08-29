# Wallet500 — Business Model Baseline

Status: Strategic baseline for future productization. Not yet activated for real-money trading.

## Core commercial model

Wallet500 should evolve through these stages:

1. Free Paper Portfolio / track record.
2. Limited live capital.
3. Optional subscription tier for infrastructure/features.
4. Performance fee only on new, net, realized profit.
5. High-Water Mark to prevent charging twice for recovery of prior losses.

## User control model

The user retains control over portfolio-level risk and exit rules. Supported modes should include:

- AUTO: Wallet500 manages entries and exits within predefined risk limits.
- TARGET: user sets portfolio-level profit target and/or maximum loss.
- MANUAL EXIT: Wallet500 manages positions until the user chooses to stop.
- PROFIT LOCK: once a configured profit target is realized, withdraw profit and keep the original capital working.

The engine should manage individual token exits according to its own verified risk/survival rules. The user should always have a Stop / Exit All control.

## Performance fee example

Starting capital: $100.

If the user configures: "When the portfolio realizes $20 net profit, withdraw the profit and keep $100 working":

- Realized net profit: $20.
- Example performance fee at 10%: $2.
- User receives/retains $18 of realized profit after the Wallet500 performance fee, subject to actual network/trading costs.
- The original $100 continues working if the user has selected that behavior.

If the portfolio reaches the user's -10% stop level and exits near $90:

- There is no performance fee because there is no new realized profit.
- The remaining balance belongs to the user and can be withdrawn, held, or restarted at the user's decision.

## High-Water Mark rule

Performance fees must only apply to new profit above the applicable prior fee-bearing high-water mark.

Example:

- $100 -> $120: fee may apply to the new $20 net realized profit.
- Later $120 -> $90 -> $110: no new performance fee merely because the account recovered.
- A new performance fee can only arise on qualifying new profit above the relevant high-water mark.

## Transparency rules

- No hidden spread.
- No fabricated fills.
- No performance fee on unrealized dashboard gains.
- No performance fee on losses or simple recovery of prior losses.
- Fees, gas, slippage and trading costs must be shown separately.
- Every closed or failed position remains in the immutable track record.

Illustrative statement:

Gross Profit
- Network / Gas
- Trading Fees / Slippage
- Wallet500 Performance Fee
= Net Profit to User

## Capacity controls

Live capital should be limited initially. Limits are not only a commercial tiering mechanism; they protect execution quality in low-liquidity markets.

Wallet500 should implement strategy-capacity limits based on exact-pair liquidity and aggregate Wallet500 exposure. The platform must never allow aggregate user orders to become large enough to materially distort the market opportunity being traded.

## Regulatory note

Before any real-money launch, the legal structure, licensing, custody/non-custody design, KYC/AML obligations, marketing restrictions and performance-fee rules must be reviewed for every launch jurisdiction. This document is a product/business baseline, not legal or tax advice.
