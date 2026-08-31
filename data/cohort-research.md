# Wallet500 Cohort Research

Generated: 2026-08-31T03:08:45.889951+00:00
Source snapshot: 2026-08-31T03:08:44.945775+00:00

## Baseline
- N=77 ROI=-19.855% P/L=$-15.28834

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=33 ROI=-4.664% delta=15.191pp
- liq>=250k: N=42 ROI=-5.1931% delta=14.6619pp
- liq>=500k: N=29 ROI=-6.8497% delta=13.0053pp
- turnover<=1: N=53 ROI=-9.0321% delta=10.8229pp
- liq>=100k: N=58 ROI=-9.559% delta=10.296pp
- liq>=100k & vol>=50k: N=51 ROI=-10.0619% delta=9.7931pp
- liq>=100k & tx>=250: N=39 ROI=-10.2849% delta=9.5701pp
- liq>=75k: N=66 ROI=-16.2286% delta=3.6264pp
- vol>=100k: N=46 ROI=-17.1122% delta=2.7428pp
- tx>=500: N=34 ROI=-18.6468% delta=1.2082pp

## Missed-star scan
- Candidates: 450
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 32, 'LIQ_LT_50K': 399, 'VOL_LT_15K': 297, 'TX_LT_50': 249}

Research only; validate prospectively before changing production gates.
