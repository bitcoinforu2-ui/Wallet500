# Wallet500 Cohort Research

Generated: 2026-09-20T04:52:52.274316+00:00
Source snapshot: 2026-09-20T04:46:47.378899+00:00

## Baseline
- N=359 ROI=-1.0324% P/L=$-3.706159

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.646pp
- turnover<=1: N=193 ROI=-0.3957% delta=0.6367pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.5903pp
- liq>=100k: N=232 ROI=-0.7601% delta=0.2723pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7601% delta=0.2723pp
- liq>=75k: N=286 ROI=-0.9662% delta=0.0662pp
- tx>=500: N=184 ROI=-1.0012% delta=0.0312pp
- tx>=250: N=283 ROI=-1.0043% delta=0.0281pp
- vol>=50k: N=359 ROI=-1.0324% delta=0.0pp
- liq>=100k & tx>=250: N=182 ROI=-1.0436% delta=-0.0112pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
