# Wallet500 Cohort Research

Generated: 2026-10-04T12:58:40.068373+00:00
Source snapshot: 2026-10-04T12:52:07.412406+00:00

## Baseline
- N=359 ROI=-0.8033% P/L=$-2.88371

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4169pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3612pp
- turnover<=1: N=193 ROI=-0.4877% delta=0.3156pp
- vol>=50k: N=359 ROI=-0.8033% delta=0.0pp
- turnover<=2: N=285 ROI=-0.8056% delta=-0.0023pp
- liq>=100k: N=232 ROI=-0.8366% delta=-0.0333pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8366% delta=-0.0333pp
- tx>=100: N=328 ROI=-0.9075% delta=-0.1042pp
- vol>=25k: N=330 ROI=-0.9279% delta=-0.1246pp
- liq>=75k: N=286 ROI=-1.0283% delta=-0.225pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
