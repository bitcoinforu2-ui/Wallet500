import base64

import pytest
from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.message import MessageV0
from solders.null_signer import NullSigner
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction

from wallet500.cryptoyeezus_signer import sign_order_transaction


def unsigned_order(wallet: Keypair, other: Keypair):
    ix = Instruction(
        Pubkey.new_unique(),
        b"copy-test",
        [AccountMeta(other.pubkey(), True, False)],
    )
    message = MessageV0.try_compile(wallet.pubkey(), [ix], [], Hash.new_unique())
    tx = VersionedTransaction(message, [NullSigner(wallet.pubkey()), NullSigner(other.pubkey())])
    return {"transaction": base64.b64encode(bytes(tx)).decode("ascii")}, tx


def test_signer_replaces_only_copy_wallet_signature():
    wallet = Keypair()
    other = Keypair()
    order, original = unsigned_order(wallet, other)
    encoded = sign_order_transaction(order, str(wallet), str(wallet.pubkey()))
    signed = VersionedTransaction.from_bytes(base64.b64decode(encoded))
    checks = signed.verify_with_results()
    assert checks[0] is True
    assert checks[1] is False
    assert signed.signatures[1] == original.signatures[1]


def test_signer_rejects_wrong_secret():
    wallet = Keypair()
    other = Keypair()
    wrong = Keypair()
    order, _ = unsigned_order(wallet, other)
    with pytest.raises(RuntimeError, match="does not match"):
        sign_order_transaction(order, str(wrong), str(wallet.pubkey()))
