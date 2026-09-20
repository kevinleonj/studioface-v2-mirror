"""Scanning source safely, because four tests were asleep in one day.

Not a test file. A helper every source-scanning assertion goes through.

## Why this exists

Two bug classes, both of which produce a test that passes against every offender it was
written to catch, and both of which look correct in a diff.

1. **Reading the prose instead of the code.** `test_header` searched the header for
   "fixed" and "sticky", words that appear in the comment explaining why it is neither.
   `test_bootstrap` grepped for `core.hooksPath`, which its own comment names.
   `test_the_wait` caught `<Progress value={60}>` inside the note recording its deletion.

2. **A regex whose `\\b` reached the file as a literal `\\x08`.** `<Button\\x08([^>]*?)>`
   matches nothing and passed against four 32px controls on the money path.

`Scanner` answers both: it refuses a pattern containing a control character at
construction, and it carries worked examples of what it must catch and what it must
ignore, which `tests/test_source_scanners.py` proves on every run.

## Why string literals are NOT stripped by default

`strip_string_literals` exists and is deliberately opt-in. In JSX the thing we scan
*lives inside* a string literal — `className="aspect-square sm:aspect-[4/5]"` is the
entire subject of half the layout tests — so blanket stripping would blind them. It is
right in exactly one shape: scanning Python where a matching literal is the tool's own
catalogue, the way `design_audit.py` lists the emoji it hunts for.

A helper that is wrong by default is worse than no helper, so the default is comments
only, and the exception has to be asked for by name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# `//` inside a string is not a comment. `https://studioface.app` on a line with a real
# trailing comment must keep the URL and lose the comment, so line comments are matched
# only when the `//` is not preceded by a `:` — the one case that actually bites here.
_TS_COMMENT = re.compile(r"\{/\*.*?\*/\}|/\*.*?\*/|(?<!:)//[^\n]*", re.S)
_PY_COMMENT = re.compile(r"(?<![\"'])#[^\n]*")
_SH_COMMENT = re.compile(r"(?<![\"'$])#[^\n]*")
_STRING = re.compile(r'"(?:[^"\\\n]|\\.)*"' r"|'(?:[^'\\\n]|\\.)*'" r"|`(?:[^`\\]|\\.)*`", re.S)

_COMMENTS = {"ts": _TS_COMMENT, "tsx": _TS_COMMENT, "js": _TS_COMMENT, "css": _TS_COMMENT}
_COMMENTS |= {"py": _PY_COMMENT, "sh": _SH_COMMENT, "yml": _SH_COMMENT, "yaml": _SH_COMMENT}

# Every C0 control character except tab, newline and carriage return. \x08 is the one
# that started this, but nothing in that range belongs in a pattern we wrote.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

REGISTRY: dict[str, Scanner] = {}


def strip_comments(text: str, *, language: str) -> str:
    """Remove comments, keep everything else. The default for every source scan."""
    pattern = _COMMENTS.get(language)
    if pattern is None:
        raise ValueError(f"no comment syntax known for {language!r}")
    return pattern.sub("", text)


def strip_string_literals(text: str) -> str:
    """Opt-in, and wrong for JSX. See the module docstring before reaching for it."""
    return _STRING.sub('""', text)


@dataclass
class Scanner:
    """A source-scanning pattern that can prove it still works.

    `catches` and `ignores` are not documentation. tests/test_source_scanners.py runs
    every one of them, so a pattern that has rotted into matching nothing — or into
    matching everything — fails there rather than passing quietly in the test that
    depends on it.
    """

    name: str
    pattern: str
    catches: tuple[str, ...]
    ignores: tuple[str, ...]
    fixture: str = "offenders.tsx"
    language: str = "ts"
    strips_comments: bool = True
    flags: int = re.S
    register: bool = True
    compiled: re.Pattern = field(init=False)

    def __post_init__(self) -> None:
        found = _CONTROL.search(self.pattern)
        if found:
            raise ValueError(
                f"{self.name}: pattern holds a control character "
                f"{found.group(0)!r} at offset {found.start()}. This is the \\b that "
                f"became \\x08 — it matches nothing and passes against everything."
            )
        self.compiled = re.compile(self.pattern, self.flags)
        if not self.catches or not self.ignores:
            raise ValueError(f"{self.name}: a scanner needs both catches and ignores")
        if self.register:
            if self.name in REGISTRY:
                raise ValueError(f"{self.name}: registered twice")
            REGISTRY[self.name] = self

    def findall(self, text: str) -> list:
        return self.compiled.findall(text)

    def scan(self, text: str) -> list:
        """Strip comments first, then match. The one-call form for a test to use."""
        if self.strips_comments:
            text = strip_comments(text, language=self.language)
        return self.findall(text)
