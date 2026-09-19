# Wallet500 Cohort Research

Generated: 2026-09-19T01:24:56.764343+00:00
Source snapshot: 2026-09-19T01:18:31.080118+00:00

## Baseline
- N=359 ROI=-0.7877% P/L=$-2.827792

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4013pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3456pp
- turnover<=1: N=193 ROI=-0.4587% delta=0.329pp
- turnover<=2: N=285 ROI=-0.786% delta=0.0017pp
- vol>=50k: N=359 ROI=-0.7877% delta=0.0pp
- liq>=100k: N=232 ROI=-0.8125% delta=-0.0248pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8125% delta=-0.0248pp
- tx>=100: N=328 ROI=-0.8905% delta=-0.1028pp
- vol>=25k: N=330 ROI=-0.911% delta=-0.1233pp
- liq>=75k: N=286 ROI=-1.0087% delta=-0.221pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
