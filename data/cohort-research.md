# Wallet500 Cohort Research

Generated: 2026-09-22T01:11:09.140695+00:00
Source snapshot: 2026-09-22T01:04:12.486092+00:00

## Baseline
- N=359 ROI=-0.7317% P/L=$-2.626976

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3546% delta=0.3771pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3453pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2896pp
- turnover<=2: N=285 ROI=-0.7155% delta=0.0162pp
- liq>=100k: N=232 ROI=-0.7259% delta=0.0058pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7259% delta=0.0058pp
- vol>=50k: N=359 ROI=-0.7317% delta=0.0pp
- tx>=100: N=328 ROI=-0.8293% delta=-0.0976pp
- vol>=25k: N=330 ROI=-0.8501% delta=-0.1184pp
- liq>=75k: N=286 ROI=-0.9385% delta=-0.2068pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
