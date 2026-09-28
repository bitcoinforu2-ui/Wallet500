# Wallet500 Cohort Research

Generated: 2026-09-28T16:14:59.119234+00:00
Source snapshot: 2026-09-28T16:08:37.619518+00:00

## Baseline
- N=359 ROI=-0.8012% P/L=$-2.876364

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4148pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3591pp
- turnover<=1: N=193 ROI=-0.4839% delta=0.3173pp
- vol>=50k: N=359 ROI=-0.8012% delta=0.0pp
- turnover<=2: N=285 ROI=-0.803% delta=-0.0018pp
- liq>=100k: N=232 ROI=-0.8334% delta=-0.0322pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8334% delta=-0.0322pp
- tx>=100: N=328 ROI=-0.9053% delta=-0.1041pp
- vol>=25k: N=330 ROI=-0.9257% delta=-0.1245pp
- liq>=75k: N=286 ROI=-1.0257% delta=-0.2245pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
