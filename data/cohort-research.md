# Wallet500 Cohort Research

Generated: 2026-08-31T17:36:18.494469+00:00
Source snapshot: 2026-08-31T17:36:16.605439+00:00

## Baseline
- N=141 ROI=-18.5156% P/L=$-26.10696

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=49 ROI=6.1392% delta=24.6548pp
- liq>=250k: N=62 ROI=4.4699% delta=22.9855pp
- liq>=500k: N=39 ROI=-5.9025% delta=12.6131pp
- turnover<=1: N=82 ROI=-6.5036% delta=12.012pp
- liq>=100k: N=102 ROI=-6.5472% delta=11.9684pp
- liq>=100k & tx>=250: N=75 ROI=-7.0714% delta=11.4442pp
- liq>=100k & vol>=50k: N=86 ROI=-7.1334% delta=11.3822pp
- tx>=500: N=64 ROI=-7.6901% delta=10.8255pp
- liq>=75k: N=118 ROI=-14.649% delta=3.8666pp
- vol>=100k: N=84 ROI=-19.3747% delta=-0.8591pp

## Missed-star scan
- Candidates: 623
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 45, 'LIQ_LT_50K': 551, 'VOL_LT_15K': 395, 'TX_LT_50': 328}

Research only; validate prospectively before changing production gates.
