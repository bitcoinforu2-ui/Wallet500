# Wallet500 Cohort Research

Generated: 2026-09-19T03:38:41.117985+00:00
Source snapshot: 2026-09-19T03:32:06.560750+00:00

## Baseline
- N=359 ROI=-0.7585% P/L=$-2.722894

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3721pp
- turnover<=1: N=193 ROI=-0.4043% delta=0.3542pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3164pp
- turnover<=2: N=285 ROI=-0.7492% delta=0.0093pp
- vol>=50k: N=359 ROI=-0.7585% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7673% delta=-0.0088pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7673% delta=-0.0088pp
- tx>=100: N=328 ROI=-0.8585% delta=-0.1pp
- vol>=25k: N=330 ROI=-0.8792% delta=-0.1207pp
- liq>=75k: N=286 ROI=-0.972% delta=-0.2135pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
