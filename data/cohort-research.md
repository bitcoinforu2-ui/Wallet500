# Wallet500 Cohort Research

Generated: 2026-09-20T01:25:05.566871+00:00
Source snapshot: 2026-09-20T01:18:56.364818+00:00

## Baseline
- N=359 ROI=-1.0073% P/L=$-3.616364

## Best post-hoc counterfactuals (min 5 retained)
- turnover<=1: N=193 ROI=-0.3491% delta=0.6582pp
- liq>=250k: N=128 ROI=-0.3864% delta=0.6209pp
- liq>=500k: N=174 ROI=-0.4421% delta=0.5652pp
- liq>=100k: N=232 ROI=-0.7214% delta=0.2859pp
- liq>=100k & vol>=50k: N=232 ROI=-0.7214% delta=0.2859pp
- liq>=75k: N=286 ROI=-0.9348% delta=0.0725pp
- tx>=500: N=184 ROI=-0.9524% delta=0.0549pp
- tx>=250: N=283 ROI=-0.9726% delta=0.0347pp
- liq>=100k & tx>=250: N=182 ROI=-0.9943% delta=0.013pp
- vol>=50k: N=359 ROI=-1.0073% delta=0.0pp

## Missed-star scan
- Candidates: 1165
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 71, 'LIQ_LT_15K': 1047, 'VOL_LT_15K': 723, 'TX_LT_50': 588}

Research only; validate prospectively before changing production gates.
