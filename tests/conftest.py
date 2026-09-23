"""One thing only: the mirror_incompatible marker (task 94).

A test marked `@pytest.mark.mirror_incompatible(reason=...)` is skipped only in the
public mirror, recognised by the MIRROR.txt that scripts/make_public_mirror.py writes
at its root and that this private repository never has. Here every marked test runs.
The marked set is pinned in tests/mirror_incompatible.txt; tests/test_mirror_suite.py
fails if the two differ.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MARKER = "mirror_incompatible"


def in_mirror(root: Path) -> bool:
    return (root / "MIRROR.txt").is_file()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        f"{MARKER}(reason): cannot pass in the public mirror because of how the mirror is "
        "built; skipped there only, runs everywhere else",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not in_mirror(ROOT):
        return
    for item in items:
        mark = item.get_closest_marker(MARKER)
        if mark is not None:
            item.add_marker(pytest.mark.skip(reason=f"{MARKER}: {mark.kwargs.get('reason', '')}"))
