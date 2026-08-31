# Wallet500 Cohort Research

Generated: 2026-08-31T13:51:26.392926+00:00
Source snapshot: 2026-08-31T13:51:24.686899+00:00

## Baseline
- N=128 ROI=-22.3452% P/L=$-28.601804

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=58 ROI=-4.0748% delta=18.2704pp
- liq>=250k & vol>=100k: N=46 ROI=-4.5323% delta=17.8129pp
- liq>=500k: N=38 ROI=-6.2184% delta=16.1268pp
- turnover<=1: N=76 ROI=-6.3698% delta=15.9754pp
- liq>=100k: N=93 ROI=-11.2911% delta=11.0541pp
- liq>=100k & vol>=50k: N=79 ROI=-12.5992% delta=9.746pp
- liq>=100k & tx>=250: N=69 ROI=-13.4648% delta=8.8804pp
- tx>=500: N=58 ROI=-15.751% delta=6.5942pp
- liq>=75k: N=108 ROI=-18.9836% delta=3.3616pp
- turnover<=2: N=102 ROI=-22.4741% delta=-0.1289pp

## Missed-star scan
- Candidates: 592
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 42, 'LIQ_LT_50K': 524, 'VOL_LT_15K': 380, 'TX_LT_50': 311}

Research only; validate prospectively before changing production gates.
