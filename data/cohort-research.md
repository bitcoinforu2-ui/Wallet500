# Wallet500 Cohort Research

Generated: 2026-08-30T19:37:55.422435+00:00
Source snapshot: 2026-08-30T19:37:54.253865+00:00

## Baseline
- N=50 ROI=-9.1175% P/L=$-4.558769

## Best post-hoc counterfactuals (min 5 retained)
- liq>=500k: N=25 ROI=0.8101% delta=9.9276pp
- liq>=250k & vol>=100k: N=25 ROI=0.6259% delta=9.7434pp
- liq>=250k: N=33 ROI=0.6198% delta=9.7373pp
- turnover<=1: N=37 ROI=-1.8417% delta=7.2758pp
- liq>=100k & vol>=50k: N=35 ROI=-3.4614% delta=5.6561pp
- liq>=100k: N=41 ROI=-3.5156% delta=5.6019pp
- liq>=100k & tx>=250: N=25 ROI=-4.6685% delta=4.449pp
- liq>=75k: N=44 ROI=-5.2038% delta=3.9137pp
- turnover<=2: N=42 ROI=-5.8527% delta=3.2648pp
- vol>=100k: N=32 ROI=-6.149% delta=2.9685pp

## Missed-star scan
- Candidates: 385
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 29, 'LIQ_LT_50K': 335, 'VOL_LT_15K': 250, 'TX_LT_50': 213}

Research only; validate prospectively before changing production gates.
