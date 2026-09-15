from wallet500.early_revival_contract import ain_golden_identity,build_checkpoint
from wallet500.early_revival_replay import replay

def _row(t,p):
 return build_checkpoint(identity=ain_golden_identity(),observed_at=t,first_price_usd=.10,current_price_usd=p,evidence={},source_fresh=True,exact_pair_verified=True)
def test_replay_preserves_first_detection_and_never_promotes():
 r=replay([_row("2026-09-15T20:10:00+00:00",.126),_row("2026-09-15T20:00:00+00:00",.10)])
 assert r["first_detected_at"]=="2026-09-15T20:00:00+00:00"
 assert r["first_detected_price_usd"]==.10
 assert r["may_rewrite_t0"] is False
 assert r["may_promote_production"] is False
