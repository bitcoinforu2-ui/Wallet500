# Wallet500 Cohort Research

Generated: 2026-10-06T21:13:15.504967+00:00
Source snapshot: 2026-10-06T21:06:39.950559+00:00

## Baseline
- N=359 ROI=-0.8076% P/L=$-2.899221

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=128 ROI=-0.3864% delta=0.4212pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.3655pp
- turnover<=1: N=193 ROI=-0.4957% delta=0.3119pp
- vol>=50k: N=359 ROI=-0.8076% delta=0.0pp
- turnover<=2: N=285 ROI=-0.811% delta=-0.0034pp
- liq>=100k: N=232 ROI=-0.8433% delta=-0.0357pp
- liq>=100k & vol>=50k: N=232 ROI=-0.8433% delta=-0.0357pp
- tx>=100: N=328 ROI=-0.9123% delta=-0.1047pp
- vol>=25k: N=330 ROI=-0.9326% delta=-0.125pp
- liq>=75k: N=286 ROI=-1.0337% delta=-0.2261pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
