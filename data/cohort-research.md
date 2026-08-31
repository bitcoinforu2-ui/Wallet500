# Wallet500 Cohort Research

Generated: 2026-08-31T03:48:02.181303+00:00
Source snapshot: 2026-08-31T03:48:00.988910+00:00

## Baseline
- N=80 ROI=-20.1418% P/L=$-16.113409

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=33 ROI=-3.6754% delta=16.4664pp
- liq>=250k: N=42 ROI=-4.4535% delta=15.6883pp
- liq>=500k: N=29 ROI=-5.9446% delta=14.1972pp
- liq>=100k: N=60 ROI=-8.8713% delta=11.2705pp
- liq>=100k & vol>=50k: N=53 ROI=-9.4657% delta=10.6761pp
- liq>=100k & tx>=250: N=41 ROI=-9.6957% delta=10.4461pp
- turnover<=1: N=54 ROI=-10.2286% delta=9.9132pp
- vol>=100k: N=48 ROI=-16.3387% delta=3.8031pp
- liq>=75k: N=69 ROI=-16.6979% delta=3.4439pp
- tx>=500: N=35 ROI=-18.0327% delta=2.1091pp

## Missed-star scan
- Candidates: 463
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 34, 'LIQ_LT_50K': 410, 'VOL_LT_15K': 300, 'TX_LT_50': 249}

Research only; validate prospectively before changing production gates.
