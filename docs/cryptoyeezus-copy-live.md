# CryptoYeezus Direct-Wallet Copy — Paper/Shadow Only

This experiment observes the Solana source wallet `JCxTzSXz1f8s3UEtYQzaDdBDWneaD6yo1cX38RBf6Rjd` and measures a hypothetical 1% copy strategy.

## Safety policy

- This experiment is permanently paper/shadow-only.
- Real-money wallet signing and transaction submission are prohibited.
- `allow_live_execution` must remain `false`.
- The dedicated live guard exits unconditionally and must not be bypassed.
- No private key is required or permitted for this experiment.
- GitHub Actions and external runtimes must not arm real-money execution.

## Measurement rules

- Forward-only: the first observation establishes a boundary; historical source-wallet activity is never booked as a simulated entry.
- A BUY is measured only when the source wallet itself signs a transaction that resolves fail-closed to one quote-asset outflow (SOL/USDC/USDT) and one token inflow.
- Airdrops, dust, plain transfers, LP operations and ambiguous multi-asset flows are ignored.
- Paper size is floor(source input raw amount × 1%).
- Paper exit is the first executable 3x quote or the first verified source-wallet sell, whichever occurs first.
- 4x remains a shadow comparator; post-exit marks are research-only and must never rewrite the recorded entry or exit.

The experiment may use public quote data to measure hypothetical execution quality, but a quote is not a trade and must never be reported as real PnL or a live fill.
