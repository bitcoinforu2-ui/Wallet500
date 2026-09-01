# Wallet500 Cohort Research

Generated: 2026-09-01T00:37:30.254446+00:00
Source snapshot: 2026-09-01T00:37:28.618029+00:00

## Baseline
- N=168 ROI=-19.5034% P/L=$-32.765741

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=56 ROI=5.0152% delta=24.5186pp
- liq>=250k: N=73 ROI=4.9227% delta=24.4261pp
- liq>=500k: N=42 ROI=-3.5435% delta=15.9599pp
- turnover<=1: N=98 ROI=-6.7096% delta=12.7938pp
- liq>=100k: N=122 ROI=-7.0553% delta=12.4481pp
- liq>=100k & tx>=250: N=91 ROI=-8.1256% delta=11.3778pp
- liq>=100k & vol>=50k: N=100 ROI=-9.2539% delta=10.2495pp
- tx>=500: N=77 ROI=-9.6008% delta=9.9026pp
- liq>=75k: N=142 ROI=-16.0046% delta=3.4988pp
- vol>=25k: N=155 ROI=-21.4171% delta=-1.9137pp

## Missed-star scan
- Candidates: 696
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 45, 'LIQ_LT_50K': 617, 'VOL_LT_15K': 438, 'TX_LT_50': 356}

Research only; validate prospectively before changing production gates.
