"""The owner's own email address must never reach the public mirror.

Five tracked files carry it today (HANDOFF.md, RUN-ME-FIRST.md, docs/verified.md,
scripts/make_demo_assets.py, tests/test_bootstrap.py), and every one of those files is
copied into the mirror. It belongs with REDACTIONS: a quiet, always-applied
substitution, the same tier as the order ids and gallery tokens. It must NOT be added
to FORBIDDEN, because FORBIDDEN exists for secret-shaped values and prints "ROTATE THE
ORIGINAL IF REAL" — an address that is supposed to live in the private repository is
not a leaked credential, and reporting it as one would make every future mirror refresh
exit non-zero for a value that was never wrong to have here.
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OWNER_EMAIL = "OWNER_EMAIL_REDACTED"


def script():
    spec = importlib.util.spec_from_file_location(
        "make_public_mirror", ROOT / "scripts" / "make_public_mirror.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_owner_email_is_redacted():
    mod = script()
    text = f"gcp_account = {OWNER_EMAIL}\nrua=mailto:{OWNER_EMAIL}"
    redacted = mod.redact(text)
    assert OWNER_EMAIL not in redacted


def test_unrelated_email_passes_through_untouched():
    mod = script()
    text = "support contact: someone-else@example.com"
    assert mod.redact(text) == text


def test_owner_email_is_redacted_even_right_after_a_literal_backslash_n():
    """tests/test_bootstrap.py carries the address straight after a literal \\n
    inside a Python string, so a word-boundary anchor in front of the pattern would
    silently miss it (the 'n' from '\\n' and the 'k' from the address are both word
    characters, so there is no boundary between them)."""
    mod = script()
    text = 'lambda a, **kw: "kevin@limeralda.com\\n' + OWNER_EMAIL + '"'
    assert OWNER_EMAIL not in mod.redact(text)


def test_script_source_does_not_carry_the_address_as_one_substring():
    """This script is itself a tracked file with no DROP rule excluding it, so it is
    copied into the public mirror. Its own source must never spell the address out as
    one contiguous substring, or the mirror would leak it regardless of REDACTIONS."""
    source = (ROOT / "scripts" / "make_public_mirror.py").read_text(encoding="utf-8")
    assert OWNER_EMAIL not in source


def test_owner_email_is_quiet_not_forbidden(tmp_path):
    """copy_file must redact it silently, not report it as a FORBIDDEN finding."""
    mod = script()
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "notes.md").write_text(f"to {OWNER_EMAIL}\n", encoding="utf-8")
    target = tmp_path / "out"
    real_root = mod.ROOT
    mod.ROOT = source_dir
    try:
        findings = mod.copy_file("notes.md", target)
    finally:
        mod.ROOT = real_root
    assert findings == []
    written = (target / "notes.md").read_text(encoding="utf-8")
    assert OWNER_EMAIL not in written
