# CryptoYeezus Direct-Wallet Copy — Live Activation

This service watches the Solana source wallet `JCxTzSXz1f8s3UEtYQzaDdBDWneaD6yo1cX38RBf6Rjd` and copies verified BUY swaps at 1% of the source input amount.

## Strategy

- Copy ratio: 1/100 (1%).
- BUY only when the source wallet itself is a signer and the transaction resolves fail-closed to one quote-asset outflow (SOL/USDC/USDT) plus one token inflow.
- Ignore airdrops, dust transfers, plain transfers, LP operations and ambiguous multi-asset flows.
- Primary exit: sell the copied position when either the source wallet sells that mint or an executable Jupiter quote reaches 3x the actual copied entry cost, whichever happens first.
- Track 4x as a shadow comparator.
- Continue counterfactual marking after exit to measure whether the exit was early or protective.
- A real trade exists only when Jupiter `/execute` returns Success and a transaction signature.

## Why GitHub Actions is shadow-only

Wallet500's main live scan runs every 15 minutes. That is useful for research and an immutable ledger, but it is too slow for memecoin execution. Real money must run as a persistent process polling every few seconds (or later via a streaming/webhook provider).

## Required live secrets

Never put these values in the repository or chat.

- `COPY_WALLET_PUBKEY` — public key of the dedicated experiment wallet.
- `COPY_WALLET_SECRET_B58` — private key for that dedicated wallet, stored only in the host's encrypted secret manager.
- `JUPITER_API_KEY` — Jupiter developer API key.
- `SOLANA_RPC_URL` — low-latency Solana RPC endpoint. A dedicated provider is strongly preferred over the public endpoint.
- `COPY_LIVE_ENABLED=true`
- `COPY_DAEMON=true`
- `COPY_POLL_SECONDS=5` (or a provider-appropriate interval).

Optional Telegram notifications use existing `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` secrets.

## Runtime

Build with `Dockerfile.cryptoyeezus-copy` and attach durable storage at `/app/data`.

The `data/cryptoyeezus-copy-ledger.json` file is execution state. Do not run a funded wallet on ephemeral storage: open positions and exit state must survive restarts.

Before funding/arming live execution, run once with `COPY_LIVE_ENABLED=false` to establish the forward boundary. Historical source-wallet activity is not copied.

## Live dependency

`pip install '.[copytrading]'` installs `solders`, used to sign Jupiter Swap V2 versioned transactions locally. The private key never leaves the runtime except as the local signer input; Jupiter receives only the signed transaction.

## Current Jupiter path

Wallet500 uses Jupiter Swap V2 `GET /order` -> local signing -> `POST /execute`. Jupiter handles routing/landing; Wallet500 records the returned signature and actual input/output amounts.
