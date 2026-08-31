# Wallet500 Cohort Research

Generated: 2026-08-31T14:08:00.208037+00:00
Source snapshot: 2026-08-31T14:07:58.467370+00:00

## Baseline
- N=131 ROI=-21.8213% P/L=$-28.585908

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k: N=59 ROI=-3.7917% delta=18.0296pp
- liq>=250k & vol>=100k: N=46 ROI=-4.1496% delta=17.6717pp
- liq>=500k: N=39 ROI=-5.7911% delta=16.0302pp
- turnover<=1: N=77 ROI=-6.2421% delta=15.5792pp
- liq>=100k: N=96 ROI=-10.6792% delta=11.1421pp
- liq>=100k & vol>=50k: N=81 ROI=-11.9293% delta=9.892pp
- liq>=100k & tx>=250: N=71 ROI=-12.4604% delta=9.3609pp
- tx>=500: N=60 ROI=-14.8911% delta=6.9302pp
- liq>=75k: N=111 ROI=-18.2623% delta=3.559pp
- turnover<=2: N=103 ROI=-22.4328% delta=-0.6115pp

## Missed-star scan
- Candidates: 595
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 43, 'LIQ_LT_50K': 527, 'VOL_LT_15K': 381, 'TX_LT_50': 312}

Research only; validate prospectively before changing production gates.
