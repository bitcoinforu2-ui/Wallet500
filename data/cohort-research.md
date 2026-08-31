# Wallet500 Cohort Research

Generated: 2026-08-31T20:07:58.471874+00:00
Source snapshot: 2026-08-31T20:07:56.522990+00:00

## Baseline
- N=157 ROI=-17.9278% P/L=$-28.146638

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=52 ROI=5.416% delta=23.3438pp
- liq>=250k: N=69 ROI=4.813% delta=22.7408pp
- liq>=500k: N=41 ROI=-4.2977% delta=13.6301pp
- liq>=100k: N=113 ROI=-5.9281% delta=11.9997pp
- turnover<=1: N=93 ROI=-6.1718% delta=11.756pp
- liq>=100k & tx>=250: N=83 ROI=-6.3441% delta=11.5837pp
- tx>=500: N=70 ROI=-6.7917% delta=11.1361pp
- liq>=100k & vol>=50k: N=93 ROI=-7.4329% delta=10.4949pp
- liq>=75k: N=131 ROI=-13.9804% delta=3.9474pp
- vol>=25k: N=144 ROI=-19.5701% delta=-1.6423pp

## Missed-star scan
- Candidates: 652
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 43, 'LIQ_LT_50K': 582, 'VOL_LT_15K': 408, 'TX_LT_50': 335}

Research only; validate prospectively before changing production gates.
