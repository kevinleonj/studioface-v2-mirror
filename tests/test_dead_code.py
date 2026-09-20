"""Tests for scripts/dead_code.py, including the meta-test that proves each rule can fail."""

import sys
from pathlib import Path

# The one line B0.1 allows adapting: this repository's tests reach scripts/ by path, the
# way tests/test_export_freshness.py:30 does. There is no scripts/__init__.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from dead_code import find_dead_code, strip_comments  # noqa: E402


def write(root: Path, relative: str, text: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def build_clean_project(root: Path) -> None:
    page = (
        "import { Hero } from '../components/Hero'\n"
        'export default function Page(){return <Hero className="sf-frame"/>}\n'
    )
    write(root, "app/page.tsx", page)
    hero = 'export function Hero(){return <img src="/muestras/a.jpg"/>}\n'
    write(root, "components/Hero.tsx", hero)
    write(root, "app/globals.css", ".sf-frame{color:red}\n")
    write(root, "public/muestras/a.jpg", "x")


def test_clean_project_reports_nothing(tmp_path: Path) -> None:
    build_clean_project(tmp_path)
    assert all(not items for items in find_dead_code(tmp_path, set()).values())


def test_every_rule_can_fail(tmp_path: Path) -> None:
    build_clean_project(tmp_path)
    write(tmp_path, "components/Orphan.tsx", "export function Orphan(){return null}\n")
    write(tmp_path, "app/extra.css", ".sf-dead{color:blue}\n")
    write(tmp_path, "public/unused.png", "x")
    report = find_dead_code(tmp_path, set())
    assert report["orphan_modules"] == ["components/Orphan.tsx"]
    assert "components/Orphan.tsx:Orphan" in report["unused_exports"]
    assert report["unused_sf_classes"] == ["sf-dead"]
    assert report["unused_public_assets"] == ["public/unused.png"]


def test_commented_import_does_not_keep_a_module_alive(tmp_path: Path) -> None:
    build_clean_project(tmp_path)
    write(tmp_path, "components/Orphan.tsx", "export function Orphan(){return null}\n")
    hero = (
        "// import { Orphan } from './Orphan'\n"
        'export function Hero(){return <img src="/muestras/a.jpg"/>}\n'
    )
    write(tmp_path, "components/Hero.tsx", hero)
    assert "components/Orphan.tsx" in find_dead_code(tmp_path, set())["orphan_modules"]


def test_strip_comments_keeps_urls() -> None:
    assert "https://studioface.app" in strip_comments('const u = "https://studioface.app" // note')


def test_allowlist_silences_one_entry(tmp_path: Path) -> None:
    build_clean_project(tmp_path)
    write(tmp_path, "public/unused.png", "x")
    assert find_dead_code(tmp_path, {"public/unused.png"})["unused_public_assets"] == []
