# Run me first

This is a public, history-free mirror of a private repository. MIRROR.txt names the
source commit it was built from.

    python -m venv .venv
    .venv\Scripts\activate          (Windows)
    source .venv/bin/activate         (macOS, Linux)
    pip install -e ".[dev]"
    pytest -q

Expected: "0 failed".

The tests listed in tests/mirror_incompatible.txt are skipped here, each with its reason.
They cannot pass in this copy because of how it is built: they read .github/, which the
mirror does not carry; they use values the mirror redacts (Stripe test session ids, the
owner's address); or they need git settings a fresh clone does not have. They run in the
private repository on every push.
