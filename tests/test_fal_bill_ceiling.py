"""What the rate limiter is actually for: a hard ceiling on the fal bill.

The free preview is the only way to make StudioFace call fal without being paid
first. Every paid generation is bounded by money already received; every preview is
not. So the worst-case daily fal spend of the whole service is decided by one number,
RateLimiter.daily_global, and by whether the three ceilings compose the way the
docstring claims. That is arithmetic, and arithmetic can be tested.

This is the offline half of the proof. The other half — that the shared counter stays
atomic when many Cloud Run instances hit it at once — is tests/test_counter_atomicity.py,
which needs the emulator and runs in CI.

The ceiling in calls is exact: 300 preview calls per UTC day. Converting it to euros
needs fal's price for a 0.5K image, which is NOT in docs/verified.md (only $0.08 per
1K image is, 2026-09-16). Taking the 1K price as an upper bound, 300 x $0.08 = $24/day
worst case. The monthly GCP budget alert that flips the kill switch is 40 EUR
(infra/variables.tf), and it does not cover fal at all — fal is a separate vendor with
a separate balance. That is why issue #1 exists.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.guards import MemoryCounter, RateLimiter  # noqa: E402

DAY = 86400.0


def limiter(clock):
    return RateLimiter(counter=MemoryCounter(now=clock), salt="s", now=clock)


def flood(rl, subnets: int, ips_each: int, tries_each: int) -> int:
    """Every distinct client the attacker can be, trying as often as it likes."""
    allowed = 0
    for _ in range(tries_each):
        for s in range(subnets):
            for i in range(ips_each):
                # s picks the /24, i picks the host inside it. Getting this the
                # other way round silently turns "one subnet" into "many".
                ok, _ = rl.check(f"10.{s}.0.{i}", f"ua-{s}-{i}")
                allowed += ok
    return allowed


# ---------------------------------------------------------------- the ceiling


def test_no_number_of_clients_gets_more_than_the_daily_global_out_of_fal():
    """40 subnets x 10 IPs x 5 tries = 2000 attempts, and a theoretical subnet-capped
    capacity of 800. The global ceiling must be what actually binds."""
    rl = limiter(lambda: 0.0)
    assert rl.daily_global == 300
    assert flood(rl, subnets=40, ips_each=10, tries_each=5) == 300


def test_one_client_alone_gets_three():
    rl = limiter(lambda: 0.0)
    assert flood(rl, subnets=1, ips_each=1, tries_each=50) == rl.per_client == 3


def test_one_subnet_alone_gets_twenty_however_many_addresses_it_rotates_through():
    """The reason the subnet ceiling exists: a single /24 is cheap to rent."""
    rl = limiter(lambda: 0.0)
    assert flood(rl, subnets=1, ips_each=200, tries_each=1) == rl.per_subnet == 20


# ---------------------------------------------------------------- composition


def test_a_client_refused_by_its_own_cap_does_not_spend_global_budget():
    """guards.RateLimiter says narrow ceilings are checked first so a rejected client
    never consumes global budget. If that were wrong, an attacker capped at 3 could
    still burn all 300 global slots and deny previews to everyone else."""
    clock = lambda: 0.0  # noqa: E731
    rl = limiter(clock)
    for _ in range(100):
        rl.check("10.0.0.1", "ua")  # 3 allowed, 97 refused at the client ceiling
    assert rl.counter.store[f"g:{int(0 // DAY)}"][0] == 3


def test_the_ceiling_is_per_utc_day_and_starts_again_the_next_one():
    """Empty -> full -> empty. The bill is bounded per day, not for all time."""
    now = [0.0]
    rl = limiter(lambda: now[0])
    assert flood(rl, subnets=40, ips_each=10, tries_each=5) == 300
    now[0] += DAY
    assert flood(rl, subnets=40, ips_each=10, tries_each=5) == 300


def test_the_three_hundred_and_first_innocent_client_of_the_day_is_refused():
    """Held-out check, and the one that would bite in real life. These 300 callers are
    each alone in their own /24 and each well inside every narrow ceiling, so only the
    global one can stop them — and it must, or the ceiling is not a ceiling. It also
    means a busy legitimate day locks out real customers: 300/day is a bill guard, not
    a capacity plan, and the thing that actually stops spend is store.killswitch, which
    the budget alert flips and /api/preview checks BEFORE it reaches the limiter."""
    rl = limiter(lambda: 0.0)
    for n in range(rl.daily_global):
        ok, why = rl.check(f"10.{n // 250}.{n % 250}.1", f"ua{n}")
        assert ok, f"client {n} refused with {why} before the global ceiling was reached"
    assert rl.check("172.16.4.9", "ua-brand-new") == (False, "daily_cap")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
