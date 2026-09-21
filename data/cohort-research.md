# Wallet500 Cohort Research

Generated: 2026-09-21T02:06:54.447462+00:00
Source snapshot: 2026-09-21T02:00:27.361114+00:00

## Baseline
- N=359 ROI=-0.7373% P/L=$-2.646976

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.365% delta=0.3723pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3509pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2952pp
- turnover<=2: N=285 ROI=-0.7225% delta=0.0148pp
- liq>=100k: N=232 ROI=-0.7346% delta=0.0027pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7346% delta=0.0027pp
- vol>=50k: N=359 ROI=-0.7373% delta=0.0pp
- tx>=100: N=328 ROI=-0.8354% delta=-0.0981pp
- vol>=25k: N=330 ROI=-0.8562% delta=-0.1189pp
- liq>=75k: N=286 ROI=-0.9455% delta=-0.2082pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
