# Wallet500 Cohort Research

Generated: 2026-09-24T11:27:32.019500+00:00
Source snapshot: 2026-09-24T11:20:53.688560+00:00

## Baseline
- N=359 ROI=-0.7656% P/L=$-2.748608

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3792pp
- turnover<=1: N=193 ROI=-0.4177% delta=0.3479pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3235pp
- turnover<=2: N=285 ROI=-0.7582% delta=0.0074pp
- vol>=50k: N=359 ROI=-0.7656% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7784% delta=-0.0128pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7784% delta=-0.0128pp
- tx>=100: N=328 ROI=-0.8663% delta=-0.1007pp
- vol>=25k: N=330 ROI=-0.887% delta=-0.1214pp
- liq>=75k: N=286 ROI=-0.981% delta=-0.2154pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
