# Wallet500 Cohort Research

Generated: 2026-09-02T05:14:00.914359+00:00
Source snapshot: 2026-09-02T05:13:57.632567+00:00

## Baseline
- N=326 ROI=3.8213922603052123e+37% P/L=$1.2457738768594992e+38

## Best post-hoc counterfactuals (min 5 retained)
- pre-runup<=10%: N=148 ROI=8.417391059861481e+37% delta=4.595998799556269e+37pp
- pre-runup<=25%: N=167 ROI=7.459723813529936e+37% delta=3.6383315532247237e+37pp
- pre-runup<=50%: N=168 ROI=7.415320695592257e+37% delta=3.5939284352870444e+37pp
- pre-runup<=100%: N=168 ROI=7.415320695592257e+37% delta=3.5939284352870444e+37pp
- turnover<=1: N=177 ROI=7.038270490731634e+37% delta=3.2168782304264214e+37pp
- turnover>=0.5: N=183 ROI=6.807507523822399e+37% delta=2.986115263517187e+37pp
- turnover<=2: N=255 ROI=4.885387752390193e+37% delta=1.0639954920849807e+37pp
- liq>=75k: N=264 ROI=4.718840442649618e+37% delta=8.974481823444053e+36pp
- turnover>=0.25: N=271 ROI=4.596951575127304e+37% delta=7.755593148220916e+36pp
- tx>=100: N=297 ROI=4.194524837910772e+37% delta=3.731325776055597e+36pp

## Missed-star scan
- Candidates: 1091
- Gate reasons now: {'BASE_GATE_NOW_PASS_OTHER_OR_TIMING': 72, 'LIQ_LT_50K': 974, 'VOL_LT_15K': 676, 'TX_LT_50': 541}

Research only; validate prospectively before changing production gates.
