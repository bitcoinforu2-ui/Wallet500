# Wallet500 Cohort Research

Generated: 2026-08-31T15:06:27.308416+00:00
Source snapshot: 2026-08-31T15:06:25.568170+00:00

## Baseline
- N=133 ROI=-20.5646% P/L=$-27.350907

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=47 ROI=-0.4721% delta=20.0925pp
- liq>=250k: N=60 ROI=-1.0031% delta=19.5615pp
- liq>=500k: N=39 ROI=-5.8383% delta=14.7263pp
- turnover<=1: N=78 ROI=-6.0686% delta=14.496pp
- liq>=100k: N=98 ROI=-9.0723% delta=11.4923pp
- liq>=100k & vol>=50k: N=83 ROI=-10.0006% delta=10.564pp
- liq>=100k & tx>=250: N=72 ROI=-10.4247% delta=10.1399pp
- tx>=500: N=61 ROI=-12.68% delta=7.8846pp
- liq>=75k: N=113 ROI=-16.7345% delta=3.8301pp
- vol>=25k: N=125 ROI=-21.9346% delta=-1.37pp

## Missed-star scan
- Candidates: 605
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 44, 'LIQ_LT_50K': 536, 'VOL_LT_15K': 387, 'TX_LT_50': 319}

Research only; validate prospectively before changing production gates.
