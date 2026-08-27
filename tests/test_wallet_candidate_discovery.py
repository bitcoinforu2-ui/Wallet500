from wallet500.wallet_candidate_discovery import extract_signers, discover_solana_candidate_wallets


def test_extract_signers_only_returns_explicit_signers():
    tx = {
        "transaction": {
            "message": {
                "accountKeys": [
                    {"pubkey": "walletA", "signer": True},
                    {"pubkey": "pool", "signer": False},
                    {"pubkey": "walletB", "signer": True},
                    {"pubkey": "walletA", "signer": True},
                ]
            }
        }
    }
    assert extract_signers(tx) == ["walletA", "walletB"]


class FakeAdapter:
    def signatures_for_address(self, address, limit=10):
        assert address == "pool"
        return [
            {"signature": "s1", "blockTime": 100},
            {"signature": "s2", "blockTime": 200},
        ]

    def transaction(self, signature):
        keys = {
            "s1": [
                {"pubkey": "walletA", "signer": True},
                {"pubkey": "pool", "signer": False},
            ],
            "s2": [
                {"pubkey": "walletA", "signer": True},
                {"pubkey": "walletB", "signer": True},
            ],
        }
        return {"blockTime": 100 if signature == "s1" else 200, "transaction": {"message": {"accountKeys": keys[signature]}}}


def test_discovery_counts_verified_pool_transaction_signers():
    out = discover_solana_candidate_wallets(
        FakeAdapter(),
        {"chain": "solana", "token": "mint", "pair_address": "pool"},
        signatures_limit=2,
    )
    assert out["error"] is None
    assert out["signatures_seen"] == 2
    assert out["transactions_loaded"] == 2
    assert out["wallets"][0]["address"] == "walletA"
    assert out["wallets"][0]["signer_appearances"] == 2
    assert out["wallets"][0]["verified"] is True
