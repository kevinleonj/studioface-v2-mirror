"""Report frontend dead code.

Four rules: orphan modules, unused exports, unused sf- classes, unused public assets.
Dependency-free on purpose (the repository is Python-tooled). The rules are heuristic, so an
allowlist file silences single entries. Exit code 1 when anything is reported. Comments are
stripped before scanning because this project has shipped tests that matched their own comments.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SOURCE_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs")
ENTRY_STEMS = frozenset(
    {
        "page",
        "layout",
        "not-found",
        "error",
        "global-error",
        "loading",
        "template",
        "default",
        "robots",
        "sitemap",
        "manifest",
        "opengraph-image",
        "twitter-image",
        "icon",
        "apple-icon",
        "route",
        "proxy",
        "middleware",
        "instrumentation",
    }
)
CONFIG_PREFIXES = (
    "next.config",
    "postcss.config",
    "eslint.config",
    "playwright.config",
    "tailwind.config",
    "vitest.config",
)
SKIP_DIRS = frozenset(
    {"node_modules", ".next", "out", "dist", "coverage", "test-results", "playwright-report"}
)
SERVED_BY_CONVENTION = frozenset({"favicon.ico", "robots.txt", "sitemap.xml"})
COMMENT_PATTERN = re.compile(r"/\*.*?\*/|(?<![:\"'`\\])//[^\n]*", re.DOTALL)
IMPORT_PATTERN = re.compile(
    r"""(?:from\s+|import\s*\(\s*|require\s*\(\s*|import\s+)["']([^"']+)["']"""
)
EXPORT_PATTERN = re.compile(
    r"export\s+(?:default\s+)?(?:async\s+)?"
    r"(?:function\*?|const|let|var|class|type|interface|enum)\s+([A-Za-z_$][\w$]*)"
)
CLASS_DEFINITION_PATTERN = re.compile(r"\.(sf-[a-z0-9-]+)")


def strip_comments(text: str) -> str:
    """Remove block and line comments while keeping `://` inside URLs."""
    return COMMENT_PATTERN.sub("", text)


def read_without_comments(path: Path) -> str:
    return strip_comments(path.read_text(encoding="utf-8", errors="replace"))


def collect_files(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    return [
        path.resolve()
        for path in root.rglob("*")
        if path.is_file() and path.suffix in suffixes and not SKIP_DIRS.intersection(path.parts)
    ]


def is_entry_file(path: Path) -> bool:
    """True for files the framework or a test runner loads without an import statement."""
    name = path.name
    is_test = ".test." in name or ".spec." in name or name.endswith(".d.ts")
    return path.stem in ENTRY_STEMS or name.startswith(CONFIG_PREFIXES) or is_test


def candidate_paths(base: Path) -> list[Path]:
    with_suffix = [base.with_name(base.name + suffix) for suffix in SOURCE_SUFFIXES]
    as_index = [base / ("index" + suffix) for suffix in SOURCE_SUFFIXES]
    return [base, *with_suffix, *as_index]


def resolve_import(importer: Path, specifier: str, root: Path, known: set[Path]) -> Path | None:
    if specifier.startswith("@/"):
        bases = [root / specifier[2:], root / "src" / specifier[2:]]
    elif specifier.startswith("."):
        bases = [importer.parent / specifier]
    else:
        return None
    for base in bases:
        for candidate in candidate_paths(Path(str(base.resolve()))):
            if candidate in known:
                return candidate
    return None


def find_imported_modules(texts: dict[Path, str], root: Path) -> set[Path]:
    known = set(texts)
    imported: set[Path] = set()
    for path, text in texts.items():
        for specifier in IMPORT_PATTERN.findall(text):
            target = resolve_import(path, specifier, root, known)
            if target is not None:
                imported.add(target)
    return imported


def find_unused_exports(texts: dict[Path, str], root: Path) -> list[str]:
    unused: list[str] = []
    for path, text in texts.items():
        if is_entry_file(path):
            continue
        for name in EXPORT_PATTERN.findall(text):
            word = re.compile(r"(?<![\w$])" + re.escape(name) + r"(?![\w$])")
            is_used_locally = len(word.findall(text)) > 1
            is_used_elsewhere = any(
                word.search(other) for other_path, other in texts.items() if other_path != path
            )
            if not is_used_locally and not is_used_elsewhere:
                unused.append(f"{path.relative_to(root).as_posix()}:{name}")
    return unused


def find_unused_assets(root: Path, haystack: str) -> list[str]:
    public = root / "public"
    if not public.is_dir():
        return []
    return [
        path.relative_to(root).as_posix()
        for path in public.rglob("*")
        if path.is_file() and path.name not in haystack and path.name not in SERVED_BY_CONVENTION
    ]


def find_dead_code(root: Path, allowlist: set[str]) -> dict[str, list[str]]:
    root = root.resolve()
    texts = {path: read_without_comments(path) for path in collect_files(root, SOURCE_SUFFIXES)}
    styles = "\n".join(read_without_comments(path) for path in collect_files(root, (".css",)))
    all_source = "\n".join(texts.values())
    imported = find_imported_modules(texts, root)
    report = {
        "orphan_modules": [
            path.relative_to(root).as_posix()
            for path in texts
            if path not in imported and not is_entry_file(path)
        ],
        "unused_exports": find_unused_exports(texts, root),
        "unused_sf_classes": [
            name for name in set(CLASS_DEFINITION_PATTERN.findall(styles)) if name not in all_source
        ],
        "unused_public_assets": find_unused_assets(root, all_source + styles),
    }
    return {rule: sorted(set(items) - allowlist) for rule, items in report.items()}


def read_allowlist(path: Path) -> set[str]:
    if not path.exists():
        return set()
    lines = path.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path("frontend")
    report = find_dead_code(root, read_allowlist(root / "dead-code-allowlist.txt"))
    for rule, items in report.items():
        print(f"{rule}: {len(items)}")
        for item in items:
            print(f"  {item}")
    return 1 if any(report.values()) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
