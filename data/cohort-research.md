# Wallet500 Cohort Research

Generated: 2026-08-31T19:23:57.256599+00:00
Source snapshot: 2026-08-31T19:23:55.506603+00:00

## Baseline
- N=154 ROI=-17.9222% P/L=$-27.600234

## Best post-hoc counterfactuals (min 5 retained)
- liq>=250k & vol>=100k: N=51 ROI=6.2015% delta=24.1237pp
- liq>=250k: N=67 ROI=4.2016% delta=22.1238pp
- turnover<=1: N=91 ROI=-5.3621% delta=12.5601pp
- liq>=500k: N=40 ROI=-5.6417% delta=12.2805pp
- liq>=100k: N=111 ROI=-6.6805% delta=11.2417pp
- tx>=500: N=69 ROI=-6.8824% delta=11.0398pp
- liq>=100k & vol>=50k: N=92 ROI=-7.3988% delta=10.5234pp
- liq>=100k & tx>=250: N=82 ROI=-7.6695% delta=10.2527pp
- liq>=75k: N=129 ROI=-14.6319% delta=3.2903pp
- vol>=25k: N=141 ROI=-19.762% delta=-1.8398pp

## Missed-star scan
- Candidates: 640
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 46, 'LIQ_LT_50K': 567, 'VOL_LT_15K': 400, 'TX_LT_50': 331}

Research only; validate prospectively before changing production gates.
