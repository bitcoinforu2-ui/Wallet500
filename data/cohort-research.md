# Wallet500 Cohort Research

Generated: 2026-09-17T14:06:58.420148+00:00
Source snapshot: 2026-09-17T14:00:26.968819+00:00

## Baseline
- N=359 ROI=-0.8122% P/L=$-2.915955

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4258pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3701pp
- turnover<=1: N=193 ROI=-0.5044% delta=0.3078pp
- vol>=50k: N=359 ROI=-0.8122% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8169% delta=-0.0047pp
- liq>=100k: N=232 ROI=-0.8505% delta=-0.0383pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8505% delta=-0.0383pp
- tx>=100: N=328 ROI=-0.9174% delta=-0.1052pp
- vol>=25k: N=330 ROI=-0.9377% delta=-0.1255pp
- liq>=75k: N=286 ROI=-1.0395% delta=-0.2273pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
