# Wallet500 Cohort Research

Generated: 2026-09-01T00:11:26.132492+00:00
Source snapshot: 2026-09-01T00:11:24.629732+00:00

## Baseline
- N=168 ROI=-18.7066% P/L=$-31.42717

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=56 ROI=4.8566% delta=23.5632pp
- liq>=250k: N=73 ROI=4.7733% delta=23.4799pp
- liq>=500k: N=42 ROI=-3.7916% delta=14.915pp
- turnover<=1: N=98 ROI=-6.2188% delta=12.4878pp
- liq>=100k: N=122 ROI=-6.956% delta=11.7506pp
- liq>=100k & tx>=250: N=91 ROI=-8.4271% delta=10.2795pp
- liq>=100k & vol>=50k: N=100 ROI=-9.5231% delta=9.1835pp
- tx>=500: N=77 ROI=-9.7744% delta=8.9322pp
- liq>=75k: N=142 ROI=-15.2705% delta=3.4361pp
- tx>=100: N=145 ROI=-20.7881% delta=-2.0815pp

## Missed-star scan
- Candidates: 688
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 46, 'LIQ_LT_50K': 610, 'VOL_LT_15K': 436, 'TX_LT_50': 354}

Research only; validate prospectively before changing production gates.
