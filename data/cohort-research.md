# Wallet500 Cohort Research

Generated: 2026-08-31T15:40:57.005303+00:00
Source snapshot: 2026-08-31T15:40:55.183527+00:00

## Baseline
- N=134 ROI=-20.5077% P/L=$-27.480376

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=47 ROI=-0.4399% delta=20.0678pp
- liq>=250k: N=60 ROI=-0.8453% delta=19.6624pp
- liq>=500k: N=39 ROI=-5.6039% delta=14.9038pp
- turnover<=1: N=78 ROI=-5.9686% delta=14.5391pp
- liq>=100k: N=98 ROI=-8.878% delta=11.6297pp
- liq>=100k & vol>=50k: N=83 ROI=-9.9175% delta=10.5902pp
- liq>=100k & tx>=250: N=72 ROI=-10.4635% delta=10.0442pp
- tx>=500: N=61 ROI=-13.0415% delta=7.4662pp
- liq>=75k: N=113 ROI=-16.6816% delta=3.8261pp
- vol>=25k: N=126 ROI=-21.9632% delta=-1.4555pp

## Missed-star scan
- Candidates: 616
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 45, 'LIQ_LT_50K': 546, 'VOL_LT_15K': 389, 'TX_LT_50': 321}

Research only; validate prospectively before changing production gates.
