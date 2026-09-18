# Wallet500 Cohort Research

Generated: 2026-09-18T23:04:49.232348+00:00
Source snapshot: 2026-09-18T22:58:01.454479+00:00

## Baseline
- N=359 ROI=-0.7896% P/L=$-2.834731

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4032pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3475pp
- turnover<=1: N=193 ROI=-0.4623% delta=0.3273pp
- turnover<=2: N=285 ROI=-0.7884% delta=0.0012pp
- vol>=50k: N=359 ROI=-0.7896% delta=0.0pp
- liq>=100k: N=232 ROI=-0.8155% delta=-0.0259pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8155% delta=-0.0259pp
- tx>=100: N=328 ROI=-0.8926% delta=-0.103pp
- vol>=25k: N=330 ROI=-0.9131% delta=-0.1235pp
- liq>=75k: N=286 ROI=-1.0111% delta=-0.2215pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
