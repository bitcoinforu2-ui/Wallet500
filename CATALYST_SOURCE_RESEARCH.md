# Wallet500 Catalyst Wire — Source Research

Research refresh: 2026-09-06. Purpose: detect official high-impact events **before market-response metrics become useful**.

## Truth rule

For listing / expected listing / roadmap / pre-market / call-auction / official catalyst events, these inputs have **zero weight in the Catalyst Wire trigger**: volume acceleration, liquidity growth, holder growth, wallet growth. They remain useful later for confirmation/execution, but not for detecting the catalyst itself.

Telegram eligibility is: current Wallet500 preliminary identity/safety/veteran pass + official event evidence + source URL + forward-only first-seen event. No automatic trade.

## Tier A — machine/exchange-native precursor surfaces

| Source | Surface | Why it matters | Wire implementation |
|---|---|---|---|
| OKX | Public instruments REST + `instruments` WebSocket | New listing state/listTime is exposed; OKX documents listing updates and preopen→live lifecycle | REST instrument-diff connected now; WebSocket is next persistent-runtime optimization |
| Gate | `/api/v4/spot/currency_pairs` | `type=premarket`, `buy_start`, `sell_start`, `trade_status` | Connected |
| KuCoin | `/api/v2/symbols` + Call Auction channels | `callauctionIsEnabled`, auction stage times, `tradingStartTime` | REST state connected; auction WS is persistent-runtime optimization |
| Bybit | instruments-info / Pre-Market | instrument status/launch time, PreLaunch/PendingOpen product states | Connected |
| Bitget | `/api/v2/public/annoucements` + public symbols | official announcement API explicitly exposes `coin_listings`; symbol state is secondary confirmation | Both connected |
| Coinbase | Exchange products | New product registry is machine-readable | Connected as forward diff; @CoinbaseMarkets remains official social confirmation |
| LBank | public currency-pair registry | New pair appearance can precede/confirm a listing article | Connected |
| WEEX | exchangeInfo | Public instrument registry; older V2 also exposes `displayNew` | Connected |
| Upbit | authenticated Announcement WebSocket | `announcement` realtime CREATED/UPDATED events; `trade` category covers new trading support | Public notice fallback connected. True realtime adapter requires persistent authenticated runtime and is explicitly surfaced as degraded until provisioned |

## Tier B — official announcement / roadmap / social surfaces

Connected official surfaces: MEXC Spot/Futures + official Telegram, Binance New Cryptocurrency Listing + official Telegram, Kraken Listing Roadmap, Bitget Spot/Futures, Bithumb Market Addition notices, CoinEx announcements / Coming Soon concept, HTX new coin listings, LBank announcements, BingX support listings, BitMart new listings, WEEX listing notices, Crypto.com Product News, Upbit public notices.

Important source-specific edges:

- **Kraken Roadmap**: roadmap inclusion can precede the final listing announcement; Kraken states roadmap inclusion is not a guarantee of listing.
- **CoinbaseMarkets**: Coinbase designated @CoinbaseMarkets as the single official source for spot/futures/perpetual listing announcements.
- **Binance Alpha / HODLer Airdrops / Launchpool / Megadrop**: Binance explicitly describes Alpha as a pre-listing token selection pool. These are catalyst evidence, not automatic buy signals.
- **MEXC / LBank / BingX / BitMart / WEEX**: listing notices frequently publish the future trading-open time, creating measurable lead time before trading begins.

## Tier C — official project-event lane

The existing Wallet500 verified social engine feeds Catalyst Wire when official/exact attribution exists for: partnership/integration, mainnet, buyback/token burn, migration, hard fork, rebrand/contract swap, TGE. Generic mentions or influencer chatter do not qualify by themselves.

## Latency policy

1. Machine state / realtime exchange announcement first.
2. Official exchange social/announcement second.
3. Official project social catalyst third.
4. News/aggregators may corroborate but **never outrank an official source** and cannot create a Telegram event on their own.

GitHub Actions is a scheduled runtime, not a permanent socket process. Current production cadence is every 5 minutes plus upstream workflow triggers. True sub-minute WebSocket sources require a persistent worker; the dashboard exposes this gap rather than pretending it is realtime.

## Anti-hindsight

The first Catalyst Wire run establishes source/event baselines and sends no historical Telegram alerts. Only a previously unseen event observed after baseline can alert. This prevents old listing pages from being reclassified as live discoveries.
