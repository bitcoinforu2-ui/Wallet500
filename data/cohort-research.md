# Wallet500 Cohort Research

Generated: 2026-09-20T00:58:41.268663+00:00
Source snapshot: 2026-09-20T00:52:14.756191+00:00

## Baseline
- N=359 ROI=-1.0061% P/L=$-3.611874

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3468% delta=0.6593pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.6197pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.564pp
- liq>=100k: N=232 ROI=-0.7194% delta=0.2867pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7194% delta=0.2867pp
- liq>=75k: N=286 ROI=-0.9332% delta=0.0729pp
- tx>=500: N=184 ROI=-0.95% delta=0.0561pp
- tx>=250: N=283 ROI=-0.971% delta=0.0351pp
- liq>=100k & tx>=250: N=182 ROI=-0.9918% delta=0.0143pp
- vol>=50k: N=359 ROI=-1.0061% delta=0.0pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
