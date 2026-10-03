"""At-most-once GitHub ref claim for canonical user-watch Telegram events.

Telegram sendMessage has no client idempotency key. Claim an immutable event
ref *before* calling Telegram, so ambiguous HTTP responses or process crashes
cannot automatically resend the same exact episode. If a runner crashes after
claiming but before sending, an operator must reconcile that event; we prefer
a missed notification to a duplicated order-like signal.

Refs are independent of main/data publishing and use GitHub's atomic create:
there is exactly one winner even if independent unified runs overlap.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request

LEASE_ROOT = "wallet500-user-send-leases"
DELIVERED_ROOT = "wallet500-user-send-delivered"


class LeaseAlreadyExists(RuntimeError):
    def __init__(self, delivered: bool):
        self.delivered = delivered
        super().__init__("TELEGRAM_EVENT_ALREADY_DELIVERED" if delivered else "TELEGRAM_SEND_LEASE_UNRESOLVED")


def event_id(identity: str, kind: str, episode: object) -> str:
    identity = str(identity or "").strip()
    kind = str(kind or "").strip().upper()
    episode = str(episode or "").strip()
    if not identity or kind not in {"PRE_BUY", "FINAL_BUY", "TARGETED_RISK"} or not episode:
        raise ValueError("EXACT_TELEGRAM_EVENT_IDENTITY_AND_EPISODE_REQUIRED")
    canonical = json.dumps([identity, kind, episode], ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _api(token, repo, method, path, payload=None, allowed=(200,)):
    base = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    url = base + "/repos/" + repo + path
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "Wallet500-Telegram-Lease/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        if status not in allowed:
            # Do not log sensitive request URLs or tokens.
            raise RuntimeError(f"TELEGRAM_LEASE_GITHUB_HTTP_{status}") from exc
        raw = exc.read()
    if status not in allowed:
        raise RuntimeError(f"TELEGRAM_LEASE_GITHUB_UNEXPECTED_HTTP_{status}")
    return status, json.loads(raw.decode("utf-8")) if raw else {}


def _credentials():
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not repo or "/" not in repo:
        raise RuntimeError("TELEGRAM_LEASE_GITHUB_CREDENTIALS_UNAVAILABLE_FAIL_CLOSED")
    return token, repo


def claim(identity: str, kind: str, episode: object, request=None) -> dict:
    request = request or _api
    token, repo = _credentials()
    eid = event_id(identity, kind, episode)
    lease_path = "/git/ref/heads/" + LEASE_ROOT + "/" + eid
    delivered_path = "/git/ref/heads/" + DELIVERED_ROOT + "/" + eid
    _, main = request(token, repo, "GET", "/git/ref/heads/main", allowed=(200,))
    sha = str((main.get("object") or {}).get("sha") or "")
    if not sha:
        raise RuntimeError("TELEGRAM_LEASE_MAIN_COMMIT_UNAVAILABLE")
    status, _ = request(
        token, repo, "POST", "/git/refs",
        payload={"ref": "refs/heads/" + LEASE_ROOT + "/" + eid, "sha": sha},
        allowed=(201, 422),
    )
    if status == 422:
        # A 422 can also indicate invalid creation; verify that *our exact*
        # immutable ref actually exists before treating it as a duplicate.
        exists, _ = request(token, repo, "GET", lease_path, allowed=(200, 404))
        if exists != 200:
            raise RuntimeError("TELEGRAM_LEASE_CLAIM_REJECTED_WITHOUT_EXISTING_REF")
        delivered, _ = request(token, repo, "GET", delivered_path, allowed=(200, 404))
        raise LeaseAlreadyExists(delivered == 200)
    return {"id": eid, "sha": sha, "kind": kind, "repo": repo}


def acknowledge(ticket: dict, request=None) -> None:
    request = request or _api
    token, repo = _credentials()
    if ticket.get("repo") != repo:
        raise RuntimeError("TELEGRAM_LEASE_REPO_MISMATCH")
    eid = str(ticket["id"])
    status, _ = request(
        token, repo, "POST", "/git/refs",
        payload={"ref": "refs/heads/" + DELIVERED_ROOT + "/" + eid, "sha": ticket["sha"]},
        allowed=(201, 422),
    )
    if status == 422:
        exists, _ = request(token, repo, "GET",
                            "/git/ref/heads/" + DELIVERED_ROOT + "/" + eid,
                            allowed=(200, 404))
        if exists != 200:
            raise RuntimeError("TELEGRAM_DELIVERED_ACK_REJECTED")


def send_once(identity: str, kind: str, episode: object, text: str, sender) -> dict:
    ticket = claim(identity, kind, episode)
    message_id = sender(text)  # Never called before the durable claim succeeds.
    try:
        acknowledge(ticket)
        status = "DELIVERED_LEDGER_CONFIRMED"
    except Exception:
        # The irreversible send succeeded but delivery-ack persistence is
        # uncertain. Do not retry: the immutable claim blocks the next run.
        status = "SENT_LEDGER_ACK_UNCERTAIN"
        print("::warning::TELEGRAM_DELIVERY_ACK_UNCERTAIN_RECONCILIATION_REQUIRED")
    return {"status": status, "message_id": message_id, "event_id": ticket["id"]}
