import json
from urllib.request import Request, urlopen


class SolanaAdapter:
    chain = "solana"

    def __init__(self, rpc_url: str, timeout: int = 20):
        self.rpc_url = rpc_url
        self.timeout = timeout
        self._id = 0

    def rpc(self, method: str, params: list):
        self._id += 1
        body = json.dumps({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}).encode()
        req = Request(self.rpc_url, data=body, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=self.timeout) as r:
            data = json.loads(r.read().decode())
        if "error" in data:
            raise RuntimeError(f"Solana RPC {method}: {data['error']}")
        return data.get("result")

    def signatures_for_address(self, address: str, limit: int = 20):
        return self.rpc("getSignaturesForAddress", [address, {"limit": limit, "commitment": "confirmed"}]) or []

    def transaction(self, signature: str):
        return self.rpc("getTransaction", [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}])

    def balance(self, address: str) -> float:
        result = self.rpc("getBalance", [address, {"commitment": "confirmed"}]) or {}
        return float(result.get("value", 0)) / 1_000_000_000

    def token_accounts(self, owner: str):
        result = self.rpc("getTokenAccountsByOwner", [owner, {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"}, {"encoding": "jsonParsed"}]) or {}
        return result.get("value", [])
