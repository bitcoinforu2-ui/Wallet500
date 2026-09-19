# Wallet500 Cohort Research

Generated: 2026-09-19T18:28:56.413522+00:00
Source snapshot: 2026-09-19T18:22:30.852773+00:00

## Baseline
- N=359 ROI=-0.7237% P/L=$-2.597996

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3396% delta=0.3841pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3373pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2816pp
- turnover<=2: N=285 ROI=-0.7053% delta=0.0184pp
- liq>=100k: N=232 ROI=-0.7135% delta=0.0102pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7135% delta=0.0102pp
- vol>=50k: N=359 ROI=-0.7237% delta=0.0pp
- tx>=100: N=328 ROI=-0.8204% delta=-0.0967pp
- vol>=25k: N=330 ROI=-0.8414% delta=-0.1177pp
- liq>=75k: N=286 ROI=-0.9284% delta=-0.2047pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
