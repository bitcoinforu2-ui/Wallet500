# Wallet500 Cohort Research

Generated: 2026-08-31T08:36:27.579324+00:00
Source snapshot: 2026-08-31T08:36:26.290749+00:00

## Baseline
- N=109 ROI=-21.5826% P/L=$-23.52503

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=50 ROI=-4.5185% delta=17.0641pp
- liq>=250k & vol>=100k: N=39 ROI=-4.6003% delta=16.9823pp
- liq>=500k: N=32 ROI=-6.8796% delta=14.703pp
- turnover<=1: N=68 ROI=-6.9982% delta=14.5844pp
- liq>=100k: N=77 ROI=-10.2705% delta=11.3121pp
- liq>=100k & vol>=50k: N=63 ROI=-11.8582% delta=9.7244pp
- liq>=100k & tx>=250: N=56 ROI=-12.231% delta=9.3516pp
- tx>=500: N=46 ROI=-15.4337% delta=6.1489pp
- liq>=75k: N=92 ROI=-18.5042% delta=3.0784pp
- turnover<=2: N=92 ROI=-21.9434% delta=-0.3608pp

## Missed-star scan
- Candidates: 525
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 39, 'LIQ_LT_50K': 462, 'VOL_LT_15K': 335, 'TX_LT_50': 280}

Research only; validate prospectively before changing production gates.
