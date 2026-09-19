# Wallet500 Cohort Research

Generated: 2026-09-19T16:38:31.640186+00:00
Source snapshot: 2026-09-19T16:31:59.026262+00:00

## Baseline
- N=359 ROI=-0.7215% P/L=$-2.590241

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3356% delta=0.3859pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3351pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2794pp
- turnover<=2: N=285 ROI=-0.7026% delta=0.0189pp
- liq>=100k: N=232 ROI=-0.7101% delta=0.0114pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7101% delta=0.0114pp
- vol>=50k: N=359 ROI=-0.7215% delta=0.0pp
- tx>=100: N=328 ROI=-0.8181% delta=-0.0966pp
- vol>=25k: N=330 ROI=-0.839% delta=-0.1175pp
- liq>=75k: N=286 ROI=-0.9256% delta=-0.2041pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
