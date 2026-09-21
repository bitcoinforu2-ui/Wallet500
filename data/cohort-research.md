# Wallet500 Cohort Research

Generated: 2026-09-21T05:53:08.813050+00:00
Source snapshot: 2026-09-21T05:46:16.261760+00:00

## Baseline
- N=359 ROI=-0.74% P/L=$-2.656772

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3701% delta=0.3699pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3536pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2979pp
- turnover<=2: N=285 ROI=-0.726% delta=0.014pp
- liq>=100k: N=232 ROI=-0.7388% delta=0.0012pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7388% delta=0.0012pp
- vol>=50k: N=359 ROI=-0.74% delta=0.0pp
- tx>=100: N=328 ROI=-0.8383% delta=-0.0983pp
- vol>=25k: N=330 ROI=-0.8592% delta=-0.1192pp
- liq>=75k: N=286 ROI=-0.9489% delta=-0.2089pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
