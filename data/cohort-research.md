# Wallet500 Cohort Research

Generated: 2026-09-19T13:08:57.660219+00:00
Source snapshot: 2026-09-19T13:02:20.654517+00:00

## Baseline
- N=359 ROI=-0.697% P/L=$-2.502078

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.2899% delta=0.4071pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3106pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2549pp
- turnover<=2: N=285 ROI=-0.6717% delta=0.0253pp
- liq>=100k: N=232 ROI=-0.6721% delta=0.0249pp
- liq>=100k & vol>=50k: N=232 ROI=-0.6721% delta=0.0249pp
- vol>=50k: N=359 ROI=-0.697% delta=0.0pp
- tx>=100: N=328 ROI=-0.7912% delta=-0.0942pp
- vol>=25k: N=330 ROI=-0.8123% delta=-0.1153pp
- tx>=500: N=184 ROI=-0.8903% delta=-0.1933pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
