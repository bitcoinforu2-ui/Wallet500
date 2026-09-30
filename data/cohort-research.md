# Wallet500 Cohort Research

Generated: 2026-09-30T23:50:24.359045+00:00
Source snapshot: 2026-09-30T23:43:49.870076+00:00

## Baseline
- N=359 ROI=-0.7991% P/L=$-2.868608

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4127pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.357pp
- turnover<=1: N=193 ROI=-0.4798% delta=0.3193pp
- vol>=50k: N=359 ROI=-0.7991% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8003% delta=-0.0012pp
- liq>=100k: N=232 ROI=-0.8301% delta=-0.031pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8301% delta=-0.031pp
- tx>=100: N=328 ROI=-0.9029% delta=-0.1038pp
- vol>=25k: N=330 ROI=-0.9234% delta=-0.1243pp
- liq>=75k: N=286 ROI=-1.023% delta=-0.2239pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
