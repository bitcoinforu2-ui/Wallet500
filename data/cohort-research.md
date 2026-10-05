# Wallet500 Cohort Research

Generated: 2026-10-05T07:53:39.185651+00:00
Source snapshot: 2026-10-05T07:47:06.171478+00:00

## Baseline
- N=359 ROI=-0.8029% P/L=$-2.882486

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4165pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3608pp
- turnover<=1: N=193 ROI=-0.487% delta=0.3159pp
- vol>=50k: N=359 ROI=-0.8029% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8052% delta=-0.0023pp
- liq>=100k: N=232 ROI=-0.8361% delta=-0.0332pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8361% delta=-0.0332pp
- tx>=100: N=328 ROI=-0.9072% delta=-0.1043pp
- vol>=25k: N=330 ROI=-0.9276% delta=-0.1247pp
- liq>=75k: N=286 ROI=-1.0278% delta=-0.2249pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
