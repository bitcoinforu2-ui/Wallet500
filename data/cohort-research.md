# Wallet500 Cohort Research

Generated: 2026-08-30T18:49:13.541825+00:00
Source snapshot: 2026-08-30T18:49:12.652474+00:00

## Baseline
- N=44 ROI=-2.4826% P/L=$-1.09234

## Best post-hoc counterfactuals (min 5 retained)
- pre-runup<=10%: N=24 ROI=1.4183% delta=3.9009pp
- pre-runup<=50%: N=31 ROI=0.9429% delta=3.4255pp
- pre-runup<=100%: N=31 ROI=0.9429% delta=3.4255pp
- liq>=500k: N=22 ROI=0.7811% delta=3.2637pp
- pre-runup<=25%: N=30 ROI=0.7684% delta=3.251pp
- liq>=250k: N=29 ROI=0.599% delta=3.0816pp
- liq>=250k & vol>=100k: N=24 ROI=0.1399% delta=2.6225pp
- turnover<=1: N=32 ROI=0.0217% delta=2.5043pp
- turnover<=2: N=36 ROI=0.0193% delta=2.5019pp
- liq>=75k: N=38 ROI=-0.3881% delta=2.0945pp

## Missed-star scan
- Candidates: 373
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 29, 'LIQ_LT_50K': 323, 'VOL_LT_15K': 242, 'TX_LT_50': 209}

Research only; validate prospectively before changing production gates.
