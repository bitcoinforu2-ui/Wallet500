# Wallet500 Cohort Research

Generated: 2026-08-31T21:07:46.744021+00:00
Source snapshot: 2026-08-31T21:07:44.763718+00:00

## Baseline
- N=160 ROI=-18.5359% P/L=$-29.657416

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=54 ROI=5.3035% delta=23.8394pp
- liq>=250k: N=71 ROI=4.9134% delta=23.4493pp
- liq>=500k: N=41 ROI=-3.9826% delta=14.5533pp
- liq>=100k: N=116 ROI=-6.9852% delta=11.5507pp
- turnover<=1: N=94 ROI=-7.2357% delta=11.3002pp
- liq>=100k & tx>=250: N=86 ROI=-7.8809% delta=10.655pp
- tx>=500: N=73 ROI=-8.3569% delta=10.179pp
- liq>=100k & vol>=50k: N=96 ROI=-8.6783% delta=9.8576pp
- liq>=75k: N=134 ROI=-14.6282% delta=3.9077pp
- vol>=100k: N=93 ROI=-20.0346% delta=-1.4987pp

## Missed-star scan
- Candidates: 656
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 46, 'LIQ_LT_50K': 582, 'VOL_LT_15K': 411, 'TX_LT_50': 337}

Research only; validate prospectively before changing production gates.
