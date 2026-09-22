"""RateLimiter.check keys the per-subnet ceiling on the address split at the third
dot, which only means anything for an IPv4 /24. An IPv6 address has no dots at all,
so the current code falls through to `subnet = ip` -- the full address -- and every
one of the 2**64 addresses inside a single /64 becomes its own "subnet" of one.

Measured against the real RateLimiter before this fix: 399 distinct addresses picked
from one /64, three tries each (RateLimiter.per_client's default at the time), got 300
free previews through -- not the 20 the per-subnet ceiling promises, but the entire
daily_global budget, because nothing between "one visitor" and "everyone today" ever
engaged. That reproduction is `test_a_single_ipv6_slash_64_used_to_drain_the_whole_daily_budget`
below: it pins the vulnerability first, then (once app/guards.py's `_network()` keys
the subnet bucket on the /64 instead of the full address) the same 399 addresses are
capped at rl.per_subnet, exactly like a /24 already was.

Two held-out cases sit alongside it: the existing IPv4 /24 behaviour must be
unchanged, and a value that is not an address at all (a hostname, an empty string)
must never raise inside a check that guards the paid image budget.
"""

import ipaddress
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.guards import MemoryCounter, RateLimiter  # noqa: E402

DAY = 86400.0


def limiter(**kw):
    clock = lambda: 0.0  # noqa: E731
    return RateLimiter(counter=MemoryCounter(now=clock), now=clock, salt="s", **kw)


def _addresses_in_one_v6_slash_64(n: int) -> list[str]:
    """`n` distinct host addresses inside a single /64 -- one visitor's own home
    network, not `n` different networks."""
    network = ipaddress.ip_network("2001:db8:1234:5678::/64")
    return [str(network[i + 1]) for i in range(n)]


# ---------------------------------------------------------------- the reproduction


def test_a_single_ipv6_slash_64_used_to_drain_the_whole_daily_budget():
    """399 addresses, one real /64, RateLimiter.per_client's value at the time (3)
    tries each. After the fix this is capped at rl.per_subnet (20); it is asserted
    here because the whole point of this test is to have shown, unfixed, that far
    more than 20 previews got through -- the entire daily_global budget, 300, exactly
    what was measured. The subnet ceiling binds well before per_client does, so the
    reproduction still holds at per_client's current, lower value."""
    rl = limiter()
    addresses = _addresses_in_one_v6_slash_64(399)
    allowed = 0
    for i, addr in enumerate(addresses):
        for _ in range(3):  # matches the original measurement, not today's rl.per_client
            ok, _ = rl.check(addr, f"ua{i}")
            allowed += ok
    assert allowed == rl.per_subnet == 20, (
        f"{allowed} previews got through one /64 -- the subnet key is not narrowing "
        f"IPv6 addresses to their /64"
    )


# ---------------------------------------------------------------- held-out cases


def test_ipv4_slash_24_rotation_is_still_capped_at_twenty():
    """Unchanged behaviour: a /24 is still cheap to rent and still capped."""
    rl = limiter()
    allowed = 0
    for i in range(200):
        ok, _ = rl.check(f"198.51.100.{i % 256}", f"ua{i}")
        allowed += ok
    assert allowed == rl.per_subnet == 20


def test_an_address_that_does_not_parse_never_raises_and_still_gets_through():
    """An empty header, a hostname, anything malformed -- `ipaddress` will refuse
    it, and `check` must leave it as-is rather than throw inside the money path."""
    rl = limiter()
    ok, why = rl.check("not-an-address-at-all", "ua")
    assert (ok, why) == (True, "ok")
    ok2, why2 = rl.check("", "ua-empty")
    assert (ok2, why2) == (True, "ok")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
