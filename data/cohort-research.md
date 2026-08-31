# Wallet500 Cohort Research

Generated: 2026-08-31T11:37:59.571675+00:00
Source snapshot: 2026-08-31T11:37:58.049857+00:00

## Baseline
- N=121 ROI=-22.2882% P/L=$-26.968711

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=54 ROI=-4.0815% delta=18.2067pp
- liq>=250k & vol>=100k: N=43 ROI=-4.5182% delta=17.77pp
- turnover<=1: N=73 ROI=-6.0061% delta=16.2821pp
- liq>=500k: N=34 ROI=-6.4348% delta=15.8534pp
- liq>=100k: N=86 ROI=-10.196% delta=12.0922pp
- liq>=100k & vol>=50k: N=72 ROI=-11.6496% delta=10.6386pp
- liq>=100k & tx>=250: N=63 ROI=-12.7076% delta=9.5806pp
- tx>=500: N=53 ROI=-16.793% delta=5.4952pp
- liq>=75k: N=101 ROI=-18.6235% delta=3.6647pp
- turnover<=2: N=99 ROI=-22.7492% delta=-0.461pp

## Missed-star scan
- Candidates: 571
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 43, 'LIQ_LT_50K': 504, 'VOL_LT_15K': 362, 'TX_LT_50': 300}

Research only; validate prospectively before changing production gates.
