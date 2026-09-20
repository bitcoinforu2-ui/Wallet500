# Wallet500 Cohort Research

Generated: 2026-09-20T11:27:32.891936+00:00
Source snapshot: 2026-09-20T11:21:24.352886+00:00

## Baseline
- N=359 ROI=-1.0326% P/L=$-3.706976

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.6462pp
- turnover<=1: N=193 ROI=-0.3961% delta=0.6365pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.5905pp
- liq>=100k: N=232 ROI=-0.7604% delta=0.2722pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7604% delta=0.2722pp
- liq>=75k: N=286 ROI=-0.9665% delta=0.0661pp
- tx>=500: N=184 ROI=-1.0017% delta=0.0309pp
- tx>=250: N=283 ROI=-1.0046% delta=0.028pp
- vol>=50k: N=359 ROI=-1.0326% delta=0.0pp
- liq>=100k & tx>=250: N=182 ROI=-1.0441% delta=-0.0115pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
