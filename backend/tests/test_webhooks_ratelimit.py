"""P6d: webhook signatures, retries (offline fake sender) and the rate limiter."""
import json

from app.services.ratelimit import RateLimiter
from app.services.webhooks import SIGNATURE_HEADER, FakeSender, deliver, sign, verify_signature

SECRET = "whsec_test_only"


def test_signature_round_trip_and_tamper_detection():
    body = b'{"event":"plan.completed"}'
    header = sign(SECRET, body, 1_000_000)
    assert verify_signature(SECRET, body, header, now=1_000_010)
    assert not verify_signature(SECRET, body + b" ", header, now=1_000_010)  # body changed
    assert not verify_signature("other", body, header, now=1_000_010)  # wrong secret
    assert not verify_signature(SECRET, body, header, now=1_000_000 + 301)  # replay after tolerance
    forged = header.replace("t=1000000", "t=1000200")  # new timestamp, old MAC
    assert not verify_signature(SECRET, body, forged, now=1_000_200)
    for bad in (None, "", "garbage", "t=x,v1=y", "v1=abc"):
        assert not verify_signature(SECRET, body, bad, now=1_000_000)


def test_delivery_is_signed_and_succeeds_first_time():
    sender = FakeSender()
    res = deliver(sender, "https://example.invalid/hook", SECRET, "plan.completed", {"plan_id": "p1"},
                  sleep=lambda s: None, clock=lambda: 1_000_000)
    assert res.delivered and res.attempts == 1 and res.errors == []
    call = sender.calls[0]
    assert json.loads(call["body"]) == {"event": "plan.completed", "data": {"plan_id": "p1"}}
    assert verify_signature(SECRET, call["body"], call["headers"][SIGNATURE_HEADER], now=1_000_000)


def test_delivery_retries_5xx_429_and_network_errors_with_backoff():
    waits = []
    sender = FakeSender(script=[500, ConnectionError("refused"), 429, 204])
    res = deliver(sender, "u", SECRET, "e", {}, backoff_s=(1, 2, 4), sleep=waits.append, clock=lambda: 5)
    assert res.delivered and res.attempts == 4 and res.last_status == 204
    assert waits == [1, 2, 4] and len(res.errors) == 3


def test_delivery_gives_up_and_reports_failure():
    sender = FakeSender(script=[503, 503, 503, 503, 200])
    res = deliver(sender, "u", SECRET, "e", {}, backoff_s=(1, 2, 4), sleep=lambda s: None)
    assert not res.delivered and res.attempts == 4 and res.last_status == 503
    assert len(sender.calls) == 4


def test_client_errors_are_not_retried():
    sender = FakeSender(script=[400])
    res = deliver(sender, "u", SECRET, "e", {}, sleep=lambda s: None)
    assert not res.delivered and res.attempts == 1 and len(sender.calls) == 1


def test_rate_limiter_burst_refill_and_per_key_buckets():
    now = [0.0]
    rl = RateLimiter(per_minute=60, burst=3, clock=lambda: now[0])
    assert [rl.check("a")[0] for _ in range(4)] == [True, True, True, False]
    allowed, retry = rl.check("a")
    assert not allowed and 0 < retry <= 1.0
    assert rl.check("b")[0]  # another key has its own bucket
    now[0] += 1.0  # 1 token per second
    assert rl.check("a")[0] and not rl.check("a")[0]
