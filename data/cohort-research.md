# Wallet500 Cohort Research

Generated: 2026-09-18T16:26:43.977765+00:00
Source snapshot: 2026-09-18T16:20:08.511557+00:00

## Baseline
- N=359 ROI=-0.8089% P/L=$-2.904119

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4225pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3668pp
- turnover<=1: N=193 ROI=-0.4982% delta=0.3107pp
- vol>=50k: N=359 ROI=-0.8089% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8128% delta=-0.0039pp
- liq>=100k: N=232 ROI=-0.8454% delta=-0.0365pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8454% delta=-0.0365pp
- tx>=100: N=328 ROI=-0.9138% delta=-0.1049pp
- vol>=25k: N=330 ROI=-0.9341% delta=-0.1252pp
- liq>=75k: N=286 ROI=-1.0354% delta=-0.2265pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
