# Wallet500 Cohort Research

Generated: 2026-09-19T13:51:41.893259+00:00
Source snapshot: 2026-09-19T13:45:22.998841+00:00

## Baseline
- N=359 ROI=-0.7032% P/L=$-2.524527

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3016% delta=0.4016pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3168pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2611pp
- turnover<=2: N=285 ROI=-0.6796% delta=0.0236pp
- liq>=100k: N=232 ROI=-0.6818% delta=0.0214pp
- liq>=100k & vol>=50k: N=232 ROI=-0.6818% delta=0.0214pp
- vol>=50k: N=359 ROI=-0.7032% delta=0.0pp
- tx>=100: N=328 ROI=-0.798% delta=-0.0948pp
- vol>=25k: N=330 ROI=-0.8191% delta=-0.1159pp
- tx>=500: N=184 ROI=-0.9025% delta=-0.1993pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
