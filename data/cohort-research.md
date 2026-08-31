# Wallet500 Cohort Research

Generated: 2026-08-31T01:06:42.033027+00:00
Source snapshot: 2026-08-31T01:06:40.572959+00:00

## Baseline
- N=72 ROI=-17.5163% P/L=$-12.611742

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=32 ROI=-4.2003% delta=13.316pp
- liq>=250k: N=40 ROI=-4.3212% delta=13.1951pp
- liq>=500k: N=27 ROI=-5.8011% delta=11.7152pp
- turnover<=1: N=51 ROI=-7.0376% delta=10.4787pp
- liq>=100k: N=55 ROI=-8.7238% delta=8.7925pp
- liq>=100k & vol>=50k: N=48 ROI=-10.1033% delta=7.413pp
- liq>=100k & tx>=250: N=37 ROI=-11.158% delta=6.3583pp
- liq>=75k: N=61 ROI=-14.1744% delta=3.3419pp
- vol>=100k: N=43 ROI=-14.4754% delta=3.0409pp
- turnover<=2: N=62 ROI=-15.3827% delta=2.1336pp

## Missed-star scan
- Candidates: 438
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 33, 'LIQ_LT_50K': 385, 'VOL_LT_15K': 284, 'TX_LT_50': 242}

Research only; validate prospectively before changing production gates.
