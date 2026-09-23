"""Task 95b: IndexNow tells Bing and the engines that share its feed which URLs changed.

IndexNow's key is public by design: it is served as a file at the site root, so it lives
in frontend config (frontend/src/content/indexnow.json), not Secret Manager. The build
writes public/<key>.txt with the key as its only content (frontend/scripts/
write-indexnow-key.mjs, run by npm as `prebuild`).

After verify_production.py passes, the deploy submits only the URLs whose sitemap lastmod
changed versus the sitemap that was live before the deploy (scripts/sitemap_changes.py),
through scripts/indexnow_submit.py, written verbatim from the brief. No test here touches
the network: urlopen is stubbed.

docs/verified.md (task 95 lines): key 8-128 characters of a-z, A-Z, 0-9 and "-"; key file
at the site root; POST {host, key, keyLocation, urlList}; 200 and 202 are accepted.
"""

from __future__ import annotations

import io
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import yaml

from scripts import indexnow_submit, sitemap_changes, verify_production

ROOT = Path(__file__).resolve().parents[1]
KEY_CONFIG = ROOT / "frontend" / "src" / "content" / "indexnow.json"
PREBUILD = ROOT / "frontend" / "scripts" / "write-indexnow-key.mjs"
PACKAGE = ROOT / "frontend" / "package.json"
OUT = ROOT / "frontend" / "out"
DEPLOY = ROOT / ".github" / "workflows" / "deploy.yml"
KEY_RULE = re.compile(r"^[A-Za-z0-9-]{8,128}$")
GOOD_KEY = "0123456789abcdef0123456789abcdef"


def _key() -> str:
    return json.loads(KEY_CONFIG.read_text(encoding="utf-8"))["key"]


# ------------------------------------------------ the key and the file that proves it


def test_the_key_lives_in_frontend_config_and_follows_the_indexnow_rule():
    assert KEY_RULE.match(_key()), "IndexNow: 8-128 of a-z A-Z 0-9 and '-'"


def test_npm_runs_the_key_file_writer_before_every_build():
    scripts = json.loads(PACKAGE.read_text(encoding="utf-8"))["scripts"]
    assert scripts.get("prebuild") == "node scripts/write-indexnow-key.mjs"
    assert PREBUILD.is_file()


@pytest.mark.skipif(not (OUT / "index.html").is_file(), reason="no frontend/out; run the build")
def test_the_built_export_serves_the_key_file_with_only_the_key():
    assert (OUT / f"{_key()}.txt").read_text(encoding="utf-8") == _key()


# ------------------------------------------------ scripts/indexnow_submit.py


class _Response(io.BytesIO):
    def __init__(self, status: int, body: bytes = b""):
        super().__init__(body)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _stub(monkeypatch, key_file: tuple[int, str], post_status: int) -> list[dict]:
    """urlopen stand-in: GET of the key file, then the POST. Returns the POST bodies."""
    posted: list[dict] = []

    def fake(target, timeout):  # noqa: ARG001 - same signature as urlopen
        if isinstance(target, str):
            status, body = key_file
            if status != 200:
                raise urllib.error.HTTPError(target, status, "no", {}, None)
            return _Response(200, body.encode())
        posted.append(json.loads(target.data))
        if post_status >= 400:
            raise urllib.error.HTTPError(target.full_url, post_status, "no", {}, None)
        return _Response(post_status)

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return posted


URLS = ["https://studioface.app/", "https://studioface.app/foto-cv/"]


def test_a_malformed_key_exits_2(monkeypatch):
    monkeypatch.setenv("INDEXNOW_KEY", "short")
    assert indexnow_submit.main(URLS) == 2


def test_a_key_with_forbidden_characters_exits_2(monkeypatch):
    monkeypatch.setenv("INDEXNOW_KEY", "abc_def/ghi.jkl")
    assert indexnow_submit.main(URLS) == 2


def test_mixed_hosts_exit_2(monkeypatch):
    monkeypatch.setenv("INDEXNOW_KEY", GOOD_KEY)
    assert indexnow_submit.main(["https://studioface.app/", "https://example.com/"]) == 2


def test_no_urls_exits_2(monkeypatch):
    monkeypatch.setenv("INDEXNOW_KEY", GOOD_KEY)
    assert indexnow_submit.main([]) == 2


def test_an_absent_key_file_exits_1_and_submits_nothing(monkeypatch):
    monkeypatch.setenv("INDEXNOW_KEY", GOOD_KEY)
    monkeypatch.delenv("INDEXNOW_SKIP_KEY_CHECK", raising=False)
    posted = _stub(monkeypatch, key_file=(404, ""), post_status=202)
    assert indexnow_submit.main(URLS) == 1
    assert posted == []


def test_a_key_file_with_the_wrong_body_exits_1(monkeypatch):
    monkeypatch.setenv("INDEXNOW_KEY", GOOD_KEY)
    monkeypatch.delenv("INDEXNOW_SKIP_KEY_CHECK", raising=False)
    posted = _stub(monkeypatch, key_file=(200, "another-key-entirely"), post_status=202)
    assert indexnow_submit.main(URLS) == 1
    assert posted == []


def test_a_live_key_and_202_exits_0_with_the_documented_body(monkeypatch):
    monkeypatch.setenv("INDEXNOW_KEY", GOOD_KEY)
    posted = _stub(monkeypatch, key_file=(200, GOOD_KEY), post_status=202)
    assert indexnow_submit.main(URLS) == 0
    assert posted == [
        {
            "host": "studioface.app",
            "key": GOOD_KEY,
            "keyLocation": f"https://studioface.app/{GOOD_KEY}.txt",
            "urlList": URLS,
        }
    ]


def test_a_rejected_submission_exits_1(monkeypatch):
    monkeypatch.setenv("INDEXNOW_KEY", GOOD_KEY)
    _stub(monkeypatch, key_file=(200, GOOD_KEY), post_status=403)
    assert indexnow_submit.main(URLS) == 1


# ------------------------------------------------ scripts/sitemap_changes.py


def _sitemap(*pairs: tuple[str, str]) -> str:
    urls = "".join(f"<url><loc>{u}</loc><lastmod>{d}</lastmod></url>" for u, d in pairs)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    )


A, B, C = (f"https://studioface.app/{p}" for p in ("", "foto-cv/", "sobre-nosotros/"))


def test_an_empty_new_sitemap_changes_nothing():
    assert sitemap_changes.changed_urls(_sitemap((A, "2026-09-22")), _sitemap()) == []


def test_one_new_url_is_a_change():
    old = _sitemap((A, "2026-09-22"))
    new = _sitemap((A, "2026-09-22"), (C, "2026-09-23"))
    assert sitemap_changes.changed_urls(old, new) == [C]


def test_only_urls_whose_lastmod_moved_are_changes():
    old = _sitemap((A, "2026-09-22"), (B, "2026-09-21"), (C, "2026-09-23"))
    new = _sitemap((A, "2026-09-24"), (B, "2026-09-21"), (C, "2026-09-25"))
    assert sitemap_changes.changed_urls(old, new) == [A, C]


def test_an_unreadable_old_sitemap_means_every_url_changed():
    new = _sitemap((A, "2026-09-22"), (B, "2026-09-21"))
    assert sitemap_changes.changed_urls("<html>not a sitemap", new) == [A, B]
    assert sitemap_changes.changed_urls(None, new) == [A, B]


def test_an_unreadable_new_sitemap_is_an_error_not_an_empty_list():
    with pytest.raises(ValueError):
        sitemap_changes.changed_urls(_sitemap((A, "2026-09-22")), "<oops")


# ------------------------------------------------ outside-in, and the deploy order


def test_verify_production_checks_the_key_file(monkeypatch):
    class R:
        def __init__(self, code, text):
            self.status_code, self.text = code, text

    key = _key()
    monkeypatch.setattr(verify_production.httpx, "get", lambda url, **kw: R(200, key))
    assert verify_production.check_indexnow_key_file("https://x")[0] == verify_production.OK
    monkeypatch.setattr(verify_production.httpx, "get", lambda url, **kw: R(404, "no"))
    assert verify_production.check_indexnow_key_file("https://x")[0] == verify_production.FAIL
    monkeypatch.setattr(verify_production.httpx, "get", lambda url, **kw: R(200, "wrong"))
    assert verify_production.check_indexnow_key_file("https://x")[0] == verify_production.FAIL
    assert ("indexnow key file", verify_production.check_indexnow_key_file) in (
        verify_production.HTTP_CHECKS
    )


def _deploy_steps() -> list[dict]:
    return yaml.safe_load(DEPLOY.read_text(encoding="utf-8"))["jobs"]["deploy"]["steps"]


def _where(steps: list[dict], needle: str) -> int:
    found = [i for i, s in enumerate(steps) if needle in str(s.get("run", ""))]
    assert len(found) == 1, (needle, found)
    return found[0]


@pytest.mark.mirror_incompatible(reason="reads .github/workflows, which the mirror does not carry")
def test_the_deploy_captures_before_and_submits_after_verification():
    steps = _deploy_steps()
    capture = _where(steps, "-o sitemap-before.xml")
    deploy = _where(steps, "gcloud run deploy")
    verify = _where(steps, "scripts/verify_production.py")
    submit = _where(steps, "scripts/indexnow_submit.py")
    assert capture < deploy < verify < submit
    assert _where(steps, "scripts/check_gallery_privacy.py") < submit


@pytest.mark.mirror_incompatible(reason="reads .github/workflows, which the mirror does not carry")
def test_an_indexnow_outage_never_turns_a_good_deploy_red():
    step = _deploy_steps()[_where(_deploy_steps(), "scripts/indexnow_submit.py")]
    assert step.get("continue-on-error") is True
    assert "indexnow.json" in step["run"], "the key comes from the frontend config"
