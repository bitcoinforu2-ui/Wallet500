from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIVE_SCAN = ROOT / ".github" / "workflows" / "live-scan.yml"
PRODUCTION_TELEGRAM = ROOT / ".github" / "workflows" / "telegram-production-alerts.yml"
SAFE_TELEGRAM_LAUNCHER = ROOT / "scripts" / "run_telegram_production_safe.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_live_scan_is_decision_producer_not_user_facing_telegram_sender():
    live = _text(LIVE_SCAN)
    assert "python -m wallet500.telegram_alerts" not in live
    assert "scripts/run_telegram_with_intelligence_shadow.py" not in live
    assert "run_telegram_production_safe.py" not in live
    assert "TELEGRAM_BOT_TOKEN" not in live
    assert "TELEGRAM_CHAT_ID" not in live
    assert "wallet500-verified-snapshot" in live


def test_production_telegram_waits_for_verified_publisher_and_uses_safe_guarded_wrapper():
    production = _text(PRODUCTION_TELEGRAM)
    safe_launcher = _text(SAFE_TELEGRAM_LAUNCHER)
    assert '"Wallet500 Verified Snapshot Publisher"' in production
    assert "github.event.workflow_run.conclusion == 'success'" in production
    assert "Verify fresh coherent production decision snapshot before user-facing delivery" in production
    assert "WALLET500_REAL_ALERT_INPUT: pre-alert-forensics-real-alerts.json" in production
    assert "run: python scripts/run_telegram_production_safe.py" in production
    assert "run: python scripts/run_telegram_with_intelligence_shadow.py" not in production
    assert "Persist Telegram dedupe, pre-alert evidence and delivery report atomically" in production
    assert "scripts/atomic_publish.py" in production
    assert "load_json_fail_closed" in safe_launcher
    assert "atomic_write_json" in safe_launcher
    assert "run_telegram_with_intelligence_shadow" in safe_launcher
