from urllib.error import HTTPError, URLError

from wallet500.hybrid_onchain_evidence import (
    RpcEvidenceError,
    STATUS_ERROR,
    STATUS_RATE_LIMITED,
    STATUS_UNAVAILABLE,
    _classify_exception,
    _endpoint_label,
    concentration_score,
)


def test_holder_distribution_score_rewards_lower_concentration():
    clean_score, clean_risk, clean_signals = concentration_score(4.0, 28.0)
    concentrated_score, concentrated_risk, concentrated_signals = concentration_score(24.0, 66.0)
    assert clean_score == 100.0
    assert clean_risk == 0.0
    assert "TOP1_OWNER_LT_10PCT" in clean_signals
    assert "TOP10_OWNERS_LT_40PCT" in clean_signals
    assert concentrated_score == 35.0
    assert concentrated_risk == 65.0
    assert "TOP1_OWNER_GE_20PCT" in concentrated_signals
    assert "TOP10_OWNERS_GE_60PCT" in concentrated_signals


def test_holder_score_is_bounded():
    score, risk, _ = concentration_score(100.0, 100.0)
    assert 0.0 <= score <= 100.0
    assert 0.0 <= risk <= 100.0
    assert score + risk == 100.0


def test_http_429_is_explicit_rate_limited():
    exc = HTTPError("https://rpc.invalid", 429, "Too Many Requests", {}, None)
    assert _classify_exception(exc) == STATUS_RATE_LIMITED


def test_network_failure_is_unavailable():
    assert _classify_exception(URLError("temporary connection failure")) == STATUS_UNAVAILABLE
    assert _classify_exception(TimeoutError("timed out")) == STATUS_UNAVAILABLE


def test_generic_failure_is_error():
    assert _classify_exception(RuntimeError("malformed account data")) == STATUS_ERROR


def test_typed_rpc_error_preserves_status():
    assert _classify_exception(RpcEvidenceError(STATUS_RATE_LIMITED, "429")) == STATUS_RATE_LIMITED
    assert _classify_exception(RpcEvidenceError(STATUS_UNAVAILABLE, "node unavailable")) == STATUS_UNAVAILABLE


def test_endpoint_label_never_leaks_secret_path_or_query():
    label = _endpoint_label("https://rpc.example.com/v1/secret-key?api-key=topsecret")
    assert label == "rpc.example.com"
    assert "secret" not in label
