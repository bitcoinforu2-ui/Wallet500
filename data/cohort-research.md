# Wallet500 Cohort Research

Generated: 2026-08-30T17:54:23.210231+00:00
Source snapshot: 2026-08-30T17:54:22.895048+00:00

## Baseline
- N=36 ROI=-0.3482% P/L=$-0.125336

## Best post-hoc counterfactuals (min 5 retained)
- pre-runup<=10%: N=19 ROI=0.6926% delta=1.0408pp
- pre-runup<=25%: N=22 ROI=0.5982% delta=0.9464pp
- pre-runup<=50%: N=23 ROI=0.5722% delta=0.9204pp
- pre-runup<=100%: N=23 ROI=0.5722% delta=0.9204pp
- liq>=500k: N=18 ROI=0.0684% delta=0.4166pp
- liq>=250k: N=25 ROI=0.0492% delta=0.3974pp
- liq>=250k & vol>=100k: N=20 ROI=0.0232% delta=0.3714pp
- turnover<=1: N=27 ROI=0.0054% delta=0.3536pp
- turnover<=2: N=29 ROI=0.005% delta=0.3532pp
- liq>=75k: N=32 ROI=-0.1109% delta=0.2373pp

## Missed-star scan
- Candidates: 364
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 28, 'LIQ_LT_50K': 317, 'VOL_LT_15K': 234, 'TX_LT_50': 202}

Research only; validate prospectively before changing production gates.
