# Wallet500 Cohort Research

Generated: 2026-09-25T15:31:11.061661+00:00
Source snapshot: 2026-09-25T15:23:56.624564+00:00

## Baseline
- N=359 ROI=-0.7782% P/L=$-2.793915

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.3918pp
- turnover<=1: N=193 ROI=-0.4411% delta=0.3371pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3361pp
- turnover<=2: N=285 ROI=-0.7741% delta=0.0041pp
- vol>=50k: N=359 ROI=-0.7782% delta=0.0pp
- liq>=100k: N=232 ROI=-0.7979% delta=-0.0197pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7979% delta=-0.0197pp
- tx>=100: N=328 ROI=-0.8802% delta=-0.102pp
- vol>=25k: N=330 ROI=-0.9007% delta=-0.1225pp
- liq>=75k: N=286 ROI=-0.9969% delta=-0.2187pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
