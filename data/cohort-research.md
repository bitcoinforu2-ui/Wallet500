# Wallet500 Cohort Research

Generated: 2026-09-19T08:28:13.107203+00:00
Source snapshot: 2026-09-19T08:21:44.739817+00:00

## Baseline
- N=359 ROI=-0.6792% P/L=$-2.438404

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.2569% delta=0.4223pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.2928pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2371pp
- liq>=100k: N=232 ROI=-0.6447% delta=0.0345pp
- liq>=100k & vol>=50k: N=232 ROI=-0.6447% delta=0.0345pp
- turnover<=2: N=285 ROI=-0.6493% delta=0.0299pp
- vol>=50k: N=359 ROI=-0.6792% delta=0.0pp
- tx>=100: N=328 ROI=-0.7718% delta=-0.0926pp
- vol>=25k: N=330 ROI=-0.793% delta=-0.1138pp
- tx>=500: N=184 ROI=-0.8557% delta=-0.1765pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
