# Wallet500 Cohort Research

Generated: 2026-09-21T09:08:08.274844+00:00
Source snapshot: 2026-09-21T09:01:04.853320+00:00

## Baseline
- N=359 ROI=-0.7393% P/L=$-2.653915

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3686% delta=0.3707pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.3529pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.2972pp
- turnover<=2: N=285 ROI=-0.725% delta=0.0143pp
- liq>=100k: N=232 ROI=-0.7376% delta=0.0017pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7376% delta=0.0017pp
- vol>=50k: N=359 ROI=-0.7393% delta=0.0pp
- tx>=100: N=328 ROI=-0.8375% delta=-0.0982pp
- vol>=25k: N=330 ROI=-0.8583% delta=-0.119pp
- liq>=75k: N=286 ROI=-0.9479% delta=-0.2086pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
