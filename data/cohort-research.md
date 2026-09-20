# Wallet500 Cohort Research

Generated: 2026-09-20T03:06:38.721131+00:00
Source snapshot: 2026-09-20T03:01:00.539303+00:00

## Baseline
- N=359 ROI=-1.0109% P/L=$-3.629017

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3557% delta=0.6552pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.6245pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.5688pp
- liq>=100k: N=232 ROI=-0.7268% delta=0.2841pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7268% delta=0.2841pp
- liq>=75k: N=286 ROI=-0.9392% delta=0.0717pp
- tx>=500: N=184 ROI=-0.9593% delta=0.0516pp
- tx>=250: N=283 ROI=-0.977% delta=0.0339pp
- liq>=100k & tx>=250: N=182 ROI=-1.0012% delta=0.0097pp
- vol>=50k: N=359 ROI=-1.0109% delta=0.0pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
