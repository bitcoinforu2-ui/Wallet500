# Wallet500 Cohort Research

Generated: 2026-09-19T20:43:50.288729+00:00
Source snapshot: 2026-09-19T20:37:52.476031+00:00

## Baseline
- N=359 ROI=-1.0026% P/L=$-3.599221

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3403% delta=0.6623pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.6162pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.5605pp
- liq>=100k: N=232 ROI=-0.714% delta=0.2886pp
- liq>=100k & vol>=50k: N=232 ROI=-0.714% delta=0.2886pp
- liq>=75k: N=286 ROI=-0.9288% delta=0.0738pp
- tx>=500: N=184 ROI=-0.9431% delta=0.0595pp
- tx>=250: N=283 ROI=-0.9665% delta=0.0361pp
- liq>=100k & tx>=250: N=182 ROI=-0.9848% delta=0.0178pp
- vol>=50k: N=359 ROI=-1.0026% delta=0.0pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
