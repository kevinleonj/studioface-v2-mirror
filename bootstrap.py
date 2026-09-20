"""StudioFace v2 bootstrap. One Python entrypoint, no shell dialects, no shell=True.

    python bootstrap.py                 # real run; idempotent, rerun after any failure
    python bootstrap.py --dry-run       # prints every command it WOULD run, executes nothing
    python bootstrap.py --reset-inputs  # forget saved answers and secrets, ask again

Nothing is asked twice. Plain answers persist in .bootstrap-answers.json (gitignored).
Secrets persist in the OS credential store (Windows Credential Manager / macOS Keychain)
through `keyring`. Google auth is ONE account, chosen explicitly, and Terraform receives a
gcloud access token through GOOGLE_OAUTH_ACCESS_TOKEN (provider and gcs backend both read it),
so there is no Application Default Credentials login and no second Google account can slip in.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import platform
import re
import secrets
import shutil
import subprocess
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
INFRA = os.path.join(ROOT, "infra")
ANSWERS = os.path.join(ROOT, ".bootstrap-answers.json")
KEYRING_SERVICE = "studioface-v2"
DRY = False
WIN = platform.system() == "Windows"
VENV = os.path.join(ROOT, ".venv")
VENV_PY = os.path.join(VENV, "Scripts" if WIN else "bin", "python.exe" if WIN else "python")

sys.path.insert(0, os.path.join(ROOT, "scripts"))
from _exec import resolve  # noqa: E402

# Verified ids: Hashicorp.Terraform, Anthropic.ClaudeCode. Others: `winget search <tool>`.
WINGET = {
    "gcloud": "Google.CloudSDK",
    "gh": "GitHub.cli",
    "terraform": "Hashicorp.Terraform",
    "stripe": "Stripe.StripeCli",
    "node": "OpenJS.NodeJS.LTS",
    "claude": "Anthropic.ClaudeCode",
    "git": "Git.Git",
}
BREW = {
    "gcloud": "brew install --cask google-cloud-sdk",
    "gh": "brew install gh",
    "terraform": "brew tap hashicorp/tap && brew install hashicorp/tap/terraform",
    "stripe": "brew install stripe/stripe-cli/stripe",
    "node": "brew install node@22",
    "claude": "npm install -g @anthropic-ai/claude-code",
    "git": "xcode-select --install",
}
PLAIN = {  # key: (prompt, default, regex)
    "project": ("GCP project id to CREATE", "", r"[a-z][a-z0-9-]{4,28}[a-z0-9]"),
    "domain": ("Domain", "studioface.app", r"[a-z0-9.-]+\.[a-z]{2,}"),
    "gh_owner": ("GitHub owner (username or org)", "", r"[A-Za-z0-9-]+"),
    "cf_account": ("Cloudflare account id", "", r"[0-9a-f]{32}"),
    "cf_zone": ("Cloudflare zone id", "", r"[0-9a-f]{32}"),
    "ga4_id": ("GA4 Measurement ID (G-..., public; Enter to skip)", "unset", r"G-[A-Z0-9]+|unset"),
}
SECRETS = {  # key: (prompt, regex)
    "cf_token": ("Cloudflare API token (Zone:DNS:Edit + Account:Turnstile:Edit)", r".{20,}"),
    "fal_key": ("fal.ai API key", r".{10,}"),
    "resend_key": ("Resend API key", r"re_.+"),
    "stripe_key": ("Stripe SECRET key (sk_test_ for the test run)", r"sk_(test|live)_.+"),
    "ga4_secret": ("GA4 Measurement Protocol API SECRET (not G-...; Enter to skip)", r"(?!G-).+"),
}
OUTPUTS = [
    "turnstile_sitekey",
    "stripe_price_eur",
    "stripe_price_usd",
    "github_repo_https",
    "cloud_run_url",
]
GITIGNORE = [
    "__pycache__/", ".pytest_cache/", ".ruff_cache/", "logs/", "*.log", ".venv/", "*.egg-info/",
    "infra/.terraform/", "infra/*.tfstate*", "infra/terraform.tfvars", ".bootstrap-answers.json",
    "frontend/node_modules/", "frontend/.next/", "frontend/out/", "frontend/.env.production",
    ".env", ".env.*", "!.env.example", ".claude/state/", ".claude/settings.local.json",
    "firebase-debug.log", "frontend/out/",
]  # fmt: skip


# ---------------------------------------------------------------- helpers
def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def say(msg: str) -> None:
    print(f"\n== {msg}", flush=True)


def sh(
    args: list[str],
    *,
    cwd: str = ROOT,
    check: bool = True,
    capture: bool = False,
    input_text: str | None = None,
    env: dict | None = None,
) -> str:
    """Run one command as an argument list; argv[0] resolved through shutil.which (PATHEXT)."""
    shown = " ".join(args) + ("   < (stdin: hidden)" if input_text is not None else "")
    if DRY:
        print(f"   $ {shown}")
        return ""
    r = subprocess.run(
        resolve(args), cwd=cwd, text=True, input=input_text, env=env, capture_output=capture
    )
    if check and r.returncode != 0:
        sys.exit(f"FAILED ({r.returncode}): {shown}\n{(r.stderr or '') if capture else ''}")
    return (r.stdout or "").strip() if capture else ""


def ok(args: list[str], cwd: str = ROOT) -> bool:
    if DRY:
        print(f"   ? {' '.join(args)}")
        return True
    try:
        r = subprocess.run(resolve(args), cwd=cwd, capture_output=True, text=True)
        return r.returncode == 0
    except FileNotFoundError:
        return False


def keyring_or_none():
    try:
        import keyring

        keyring.get_password(KEYRING_SERVICE, "probe")  # raises when no backend is usable
        return keyring
    except Exception as e:  # noqa: BLE001 - any backend failure means "ask every run"
        print(f"   (OS credential store unavailable: {type(e).__name__}; secrets asked each run)")
        return None


# ---------------------------------------------------------------- 1. inputs
def ask_plain(c: dict, key: str) -> None:
    prompt, default, rx = PLAIN[key]
    default = c.get(key) or default
    if DRY:
        c[key] = default or "dry"
        return
    while True:
        v = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip() or default
        if v and re.fullmatch(rx, v):
            c[key] = v
            return
        print(f"   invalid: must match {rx}")


def ask_secret(key: str) -> str:
    prompt, rx = SECRETS[key]
    while True:
        v = getpass.getpass(f"{prompt}: ")
        if key == "ga4_secret" and not v:
            return "unset"
        if re.fullmatch(rx, v):
            return v
        print("   invalid format for this secret; try again")


def pick_google_account(c: dict) -> None:
    """Choose from accounts gcloud already knows; never type an email (typo = wrong account)."""
    if DRY:
        c["gcp_account"] = c.get("gcp_account") or "dry"
        return
    while True:
        known = sh(["gcloud", "auth", "list", "--format=value(account)"], capture=True, check=False)
        accounts = known.split()
        print("   Google account for GCP + Firebase (must own the billing account):")
        for i, a in enumerate(accounts, 1):
            print(f"     {i}) {a}{'   (saved)' if a == c.get('gcp_account') else ''}")
        print("     0) log in with another account (browser)")
        default = (
            str(accounts.index(c["gcp_account"]) + 1) if c.get("gcp_account") in accounts else ""
        )
        pick = input(f"   choose [{default}]: ".replace(" []", "")).strip() or default
        if pick == "0":
            sh(["gcloud", "auth", "login"])
            continue
        if pick.isdigit() and 1 <= int(pick) <= len(accounts):
            c["gcp_account"] = accounts[int(pick) - 1]
            return
        print("   pick a number from the list")


def inputs(reset: bool) -> dict:
    say("1/9 inputs (answers remembered; Enter keeps the shown value)")
    c = {} if reset or DRY or not os.path.exists(ANSWERS) else json.loads(read(ANSWERS))
    for key in PLAIN:
        ask_plain(c, key)
    pick_google_account(c)
    if DRY:
        c.update(dict.fromkeys(SECRETS, "dry-secret"))
        return c
    write(ANSWERS, json.dumps(c, indent=2))
    kr = keyring_or_none()
    for key in SECRETS:
        stored = None if (reset or kr is None) else kr.get_password(KEYRING_SERVICE, key)
        if stored:
            c[key] = stored
            print(f"   {key}: using stored value (--reset-inputs to change)")
            continue
        c[key] = ask_secret(key)
        if kr is not None:
            kr.set_password(KEYRING_SERVICE, key, c[key])
    return c


# ---------------------------------------------------------------- 0. preflight
def preflight() -> None:
    say("0/9 preflight")
    tools = ["gcloud", "gh", "terraform", "stripe", "node", "claude", "git"]
    missing = []
    for t in tools:
        if not shutil.which(t):
            hint = f"winget install --id {WINGET[t]} -e" if WIN else BREW[t]
            missing.append(f"  {t:10s} -> {hint}")
    if missing and not DRY:
        sys.exit("MISSING tools:\n" + "\n".join(missing) + "\nInstall, open a NEW terminal, rerun.")
    names = ", ".join(m.split()[0] for m in missing)
    print("Tools OK." if not missing else f"(dry-run) missing: {names}")
    if not ok(["claude", "auth", "status"]):
        sys.exit("Claude Code is not logged in. Run: claude auth login   then rerun.")


# ---------------------------------------------------------------- 2. logins
def gcp_token() -> str:
    """A fresh 1-hour token for the chosen account. Terraform's google provider and the gcs
    backend both read GOOGLE_OAUTH_ACCESS_TOKEN, so no ADC login exists in this flow."""
    return sh(["gcloud", "auth", "print-access-token"], capture=True) or "dry-token"


def logins(c: dict) -> None:
    acct = c["gcp_account"]
    say(f"2/9 logins as {acct} (existing sessions reused; browser only when missing)")
    sh(["gcloud", "config", "set", "account", acct])  # acct was picked from `gcloud auth list`
    if not ok(["gh", "auth", "status"]):
        sh(["gh", "auth", "login", "--web", "--scopes", "repo,workflow"])
    if "api_key" not in sh(["stripe", "config", "--list"], capture=True, check=False):
        sh(["stripe", "login"])


# ---------------------------------------------------------------- 3. validation
def http_status(url: str, token: str) -> int:
    import httpx

    return httpx.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=20).status_code


def validate(c: dict) -> None:
    say("3/9 validation before anything is created")
    repo = f"{c['gh_owner']}/studioface-v2"
    if not ok(["git", "remote", "get-url", "origin"]) and ok(["gh", "repo", "view", repo]):
        sys.exit(f"GitHub repo {repo} already exists and this folder is not linked to it.")
    print("   github: repo name free (or already linked)")
    if DRY:
        return
    checks = {
        "cf_token": ("https://api.cloudflare.com/client/v4/user/tokens/verify", c["cf_token"]),
        "stripe_key": ("https://api.stripe.com/v1/balance", c["stripe_key"]),
        "resend_key": ("https://api.resend.com/domains", c["resend_key"]),
    }
    for key, (url, token) in checks.items():
        code = http_status(url, token)
        if code != 200:
            kr = keyring_or_none()
            if kr is not None:
                kr.delete_password(KEYRING_SERVICE, key)
            sys.exit(
                f"   {key}: rejected by the vendor (HTTP {code}). Forgotten; rerun and paste it."
            )
        print(f"   {key}: accepted by the vendor")
    acct = sh(["gcloud", "config", "get-value", "account"], capture=True)
    if acct != c["gcp_account"]:
        sys.exit(f"gcloud active account is {acct}, expected {c['gcp_account']}")


# ---------------------------------------------------------------- 4. GCP
def gcp_project(c: dict) -> str:
    say("4/9 GCP project, billing, Terraform state bucket")
    listing = [
        "gcloud",
        "billing",
        "accounts",
        "list",
        "--filter=open=true",
        "--format=value(name)",
    ]
    billing = sh(listing, capture=True).splitlines()
    if not billing and not DRY:
        sys.exit(f"No open billing account is visible to {c['gcp_account']}.")
    acct = billing[0] if billing else "billingAccounts/DRY"
    if not ok(["gcloud", "projects", "describe", c["project"]]):
        sh(["gcloud", "projects", "create", c["project"], "--name", "StudioFace"])
    sh(["gcloud", "billing", "projects", "link", c["project"], "--billing-account", acct])
    sh(["gcloud", "config", "set", "project", c["project"]])
    apis = [
        "storage.googleapis.com",
        "cloudresourcemanager.googleapis.com",
        "serviceusage.googleapis.com",
    ]
    sh(["gcloud", "services", "enable", *apis, "--quiet"])
    bucket = f"gs://{c['project']}-tfstate"
    if not ok(["gcloud", "storage", "buckets", "describe", bucket]):
        flags = ["--location=EU", "--uniform-bucket-level-access"]
        sh(["gcloud", "storage", "buckets", "create", bucket, *flags])
    sh(["gcloud", "storage", "buckets", "update", bucket, "--versioning"])
    return acct.split("/")[-1]


# ---------------------------------------------------------------- 5. terraform
def tf_env(c: dict) -> dict:
    return dict(
        os.environ,
        CLOUDFLARE_API_TOKEN=c["cf_token"],
        STRIPE_API_KEY=c["stripe_key"],
        GITHUB_TOKEN=sh(["gh", "auth", "token"], capture=True) or "dry",
        GOOGLE_OAUTH_ACCESS_TOKEN=gcp_token(),
    )


def has_enabled_version(project: str, name: str) -> bool:
    cmd = [
        "gcloud", "secrets", "versions", "list", name, "--project", project,
        "--filter=state=ENABLED", "--format=value(name)", "--limit=1",
    ]  # fmt: skip
    return bool(sh(cmd, capture=True, check=False))


def put_secret(project: str, name: str, value: str) -> None:
    """Idempotent: a secret with an enabled version is left alone (each version costs $0.06/month).
    --reset-inputs is the way to rotate a value."""
    if not DRY and has_enabled_version(project, name):
        print(f"   secret {name}: enabled version exists, keeping it")
        return
    cmd = [
        "gcloud",
        "secrets",
        "versions",
        "add",
        name,
        "--data-file=-",
        "--project",
        project,
        "--quiet",
    ]
    sh(cmd, input_text=value)
    print(f"   secret {name}: version added")


PHASE_A = [  # everything the Cloud Run service needs to exist BEFORE it is created
    "google_project_service.svc",
    "google_secret_manager_secret.s",
    "stripe_product.headshots",
    "stripe_price.eur",
    "stripe_price.usd",
    "stripe_webhook_endpoint.api",
    "cloudflare_turnstile_widget.preview",
    "google_secret_manager_secret_version.stripe_webhook",
    "google_secret_manager_secret_version.turnstile",
]
USER_SECRETS = {  # Secret Manager name -> answers key; added by bootstrap, never by Terraform
    "fal-key": "fal_key",
    "stripe-secret-key": "stripe_key",
    "resend-api-key": "resend_key",
    "ga4-api-secret": "ga4_secret",
}


def import_existing_dns(c: dict, env: dict) -> None:
    """A pre-existing api.<domain> record (v1 era) makes create fail with Cloudflare 81053.
    Import it so Terraform updates it in place. Import id format: '<zone_id>/<dns_record_id>'."""
    if DRY:
        print("   ? cloudflare dns lookup for api record (import if it exists)")
        return
    if "cloudflare_dns_record.api" in sh(
        ["terraform", "state", "list"], cwd=INFRA, capture=True, check=False, env=env
    ):
        return
    import httpx

    r = httpx.get(
        f"https://api.cloudflare.com/client/v4/zones/{c['cf_zone']}/dns_records",
        params={"name": f"api.{c['domain']}"},
        headers={"Authorization": f"Bearer {c['cf_token']}"},
        timeout=20,
    ).json()
    records = [x for x in r.get("result", []) if x.get("type") in ("A", "AAAA", "CNAME")]
    if not records:
        return
    rid = records[0]["id"]
    print(f"   importing existing DNS record api.{c['domain']} ({records[0]['type']})")
    sh(
        [
            "terraform",
            "import",
            "-input=false",
            "cloudflare_dns_record.api",
            f"{c['cf_zone']}/{rid}",
        ],
        cwd=INFRA,
        env=env,
    )


def untaint_cloud_run(env: dict) -> None:
    """A failed first create leaves the service tainted -> Terraform plans destroy+create. The
    provider refuses the destroy while deletion_protection is still true IN STATE (it only
    becomes false after an apply). Untainting turns the plan into an in-place update, which
    writes deletion_protection=false to state and deploys a fresh revision in one apply."""
    state = sh(["terraform", "state", "list"], cwd=INFRA, capture=True, check=False, env=env)
    if "google_cloud_run_v2_service.api" not in state:
        return
    shown = sh(
        ["terraform", "state", "show", "google_cloud_run_v2_service.api"],
        cwd=INFRA,
        capture=True,
        check=False,
        env=env,
    )
    if "(tainted)" in shown:
        sh(["terraform", "untaint", "google_cloud_run_v2_service.api"], cwd=INFRA, env=env)


GOOGLE_APEX = {
    "216.239.32.21", "216.239.34.21", "216.239.36.21", "216.239.38.21",
    "2001:4860:4802:32::15", "2001:4860:4802:34::15",
    "2001:4860:4802:36::15", "2001:4860:4802:38::15",
}  # fmt: skip


def reconcile_apex_dns(c: dict) -> None:
    """The apex still points at the dead v1 site. Terraform cannot create A/AAAA records next to
    foreign ones (Cloudflare 81053), so any apex A/AAAA/CNAME record whose content is not one of
    Google's Cloud Run addresses is deleted here, and logged. v1 is dead by Kevin's own account."""
    if DRY:
        print("   ? cloudflare apex records: delete non-Google A/AAAA/CNAME")
        return
    import httpx

    base = f"https://api.cloudflare.com/client/v4/zones/{c['cf_zone']}/dns_records"
    hdr = {"Authorization": f"Bearer {c['cf_token']}"}
    r = httpx.get(base, params={"name": c["domain"], "per_page": 100}, headers=hdr, timeout=20)
    for rec in r.json().get("result") or []:
        if rec.get("type") in ("A", "AAAA", "CNAME") and rec.get("content") not in GOOGLE_APEX:
            print(f"   deleting stale apex record {rec['type']} {rec['content']}")
            httpx.delete(f"{base}/{rec['id']}", headers=hdr, timeout=20)


def terraform(c: dict, billing_id: str) -> dict:
    say("5/9 terraform: phase A (secrets, Stripe, Turnstile) -> secret versions -> phase B")
    versions = os.path.join(INFRA, "versions.tf")
    tfvars = {
        "project_id": c["project"],
        "billing_account": billing_id,
        "github_owner": c["gh_owner"],
        "domain": c["domain"],
        "cloudflare_zone_id": c["cf_zone"],
        "cloudflare_account_id": c["cf_account"],
    }
    if not DRY:
        write(versions, re.sub(r'# backend "gcs" \{\}.*', 'backend "gcs" {}', read(versions)))
        body = "".join(f'{k} = "{v}"\n' for k, v in tfvars.items())
        write(os.path.join(INFRA, "terraform.tfvars"), body)
    backend = [
        f"-backend-config=bucket={c['project']}-tfstate",
        "-backend-config=prefix=studioface",
    ]
    sh(["terraform", "init", "-input=false", "-upgrade", *backend], cwd=INFRA, env=tf_env(c))
    targets = [f"-target={t}" for t in PHASE_A]
    sh(["terraform", "apply", "-input=false", "-auto-approve", *targets], cwd=INFRA, env=tf_env(c))
    for name, key in USER_SECRETS.items():
        put_secret(c["project"], name, c[key])
    put_secret(c["project"], "app-token-secret", secrets.token_hex(32))
    put_secret(c["project"], "tasks-token", secrets.token_hex(32))
    env = tf_env(c)
    import_existing_dns(c, env)
    reconcile_apex_dns(c)
    untaint_cloud_run(env)
    sh(["terraform", "apply", "-input=false", "-auto-approve"], cwd=INFRA, env=env)
    env = tf_env(c)
    out = {}
    for k in OUTPUTS:
        out[k] = (
            sh(["terraform", "output", "-raw", k], cwd=INFRA, capture=True, env=env) or f"dry-{k}"
        )
    return out


# ---------------------------------------------------------------- 6. secrets + public config
def secrets_and_config(c: dict, o: dict, billing_id: str) -> None:
    say("6/9 public values -> GitHub variables")
    repo = f"{c['gh_owner']}/studioface-v2"
    public = {
        "PUBLIC_DOMAIN": c["domain"],
        "NEXT_PUBLIC_API_URL": f"https://api.{c['domain']}",
        "NEXT_PUBLIC_TURNSTILE_SITEKEY": o["turnstile_sitekey"],
        "NEXT_PUBLIC_STRIPE_PRICE_EUR": o["stripe_price_eur"],
        "NEXT_PUBLIC_STRIPE_PRICE_USD": o["stripe_price_usd"],
        "NEXT_PUBLIC_GA4_ID": c["ga4_id"],
    }
    public.update(
        {
            "GCP_BILLING_ACCOUNT": billing_id,
            "CF_ZONE_ID": c["cf_zone"],
            "CF_ACCOUNT_ID": c["cf_account"],
        }
    )
    for k, v in public.items():
        sh(["gh", "variable", "set", k, "--body", v, "--repo", repo])
    sync_ci(c, repo)


def sync_ci(c: dict, repo: str) -> None:
    """GitOps needs CI to hold what Terraform needs. Variables are public config; secrets go over
    stdin to `gh secret set` (never on a command line). Idempotent: re-setting is an overwrite."""
    say("6b/9 CI variables + secrets so GitHub Actions can apply Terraform and self-heal")
    billing = sh(
        [
            "gcloud",
            "billing",
            "projects",
            "describe",
            c["project"],
            "--format=value(billingAccountName)",
        ],
        capture=True,
        check=False,
    ).split("/")[-1]
    for k, v in {
        "GCP_BILLING_ACCOUNT": billing or "dry",
        "CLOUDFLARE_ZONE_ID": c["cf_zone"],
        "CLOUDFLARE_ACCOUNT_ID": c["cf_account"],
    }.items():
        sh(["gh", "variable", "set", k, "--body", v, "--repo", repo])
    for name, value in {
        "STRIPE_API_KEY": c["stripe_key"],
        "CLOUDFLARE_API_TOKEN": c["cf_token"],
        "TF_GITHUB_TOKEN": sh(["gh", "auth", "token"], capture=True) or "dry",
    }.items():
        sh(["gh", "secret", "set", name, "--repo", repo], input_text=value)
    if DRY:
        print("   ? CLAUDE_CODE_OAUTH_TOKEN from `claude setup-token` (paste once)")
        return
    kr = keyring_or_none()
    tok = kr.get_password(KEYRING_SERVICE, "claude_oauth") if kr else None
    if not tok:
        print("   Run `claude setup-token` in another terminal, then paste the token here.")
        tok = getpass.getpass("   CLAUDE_CODE_OAUTH_TOKEN: ")
        if kr and tok:
            kr.set_password(KEYRING_SERVICE, "claude_oauth", tok)
    if tok:
        sh(["gh", "secret", "set", "CLAUDE_CODE_OAUTH_TOKEN", "--repo", repo], input_text=tok)
    else:
        print("   skipped; self-heal.yml stays inactive until CLAUDE_CODE_OAUTH_TOKEN exists")
    # CI applies Terraform, so it needs the two vendor tokens as repository secrets (never printed).
    sh(["gh", "secret", "set", "CLOUDFLARE_API_TOKEN", "--repo", repo], input_text=c["cf_token"])
    sh(["gh", "secret", "set", "STRIPE_API_KEY", "--repo", repo], input_text=c["stripe_key"])


# ---------------------------------------------------------------- 7. git
def git_push(o: dict) -> None:
    say("7/9 repository: init, commit, push (CI deploys the placeholder)")
    if not DRY:
        write(os.path.join(ROOT, ".gitignore"), "\n".join(GITIGNORE) + "\n")
    if not os.path.isdir(os.path.join(ROOT, ".git")):
        sh(["git", "init", "-q", "-b", "main"])
    # Attach the versioned pre-push gate. A hook under .git/hooks lives on exactly one
    # machine and appears in no diff; core.hooksPath points git at .githooks/, which is
    # reviewed like any other file and arrives with the clone. Without this line the
    # gate is attached wherever somebody remembered to type it, which is nowhere.
    sh(["git", "config", "core.hooksPath", ".githooks"])
    # A previous run may have committed a now-ignored file (firebase-debug.log): untrack it.
    sh(["git", "rm", "-r", "-q", "--cached", "--ignore-unmatch", "firebase-debug.log"], check=False)
    sh(["git", "add", "-A"])
    sh(["git", "commit", "-qm", "chore: bootstrap StudioFace v2"], check=False)
    # HTTPS remote + gh as git credential helper: no SSH key to generate or upload.
    sh(["gh", "auth", "setup-git"])
    if ok(["git", "remote", "get-url", "origin"]):
        sh(["git", "remote", "set-url", "origin", o["github_repo_https"]])
    else:
        sh(["git", "remote", "add", "origin", o["github_repo_https"]])
    sh(["git", "push", "-u", "origin", "main"])


# ---------------------------------------------------------------- 8 + 9
def ci_gate() -> None:
    say("8/9 CI Mirror Gate inside .venv")
    sh([sys.executable, os.path.join(ROOT, "scripts", "ci.py")])


def trust_and_launch() -> None:
    say("9/9 trust this folder for Claude Code, then launch the build")
    # -p never shows the trust dialog; project allow rules are held until trusted. Documented route:
    # projects["<root>"].hasTrustDialogAccepted = true in ~/.claude.json (docs/en/permissions)
    cfg = os.path.expanduser("~/.claude.json")
    if not DRY:
        data = json.loads(read(cfg)) if os.path.exists(cfg) else {}
        data.setdefault("projects", {}).setdefault(ROOT, {})["hasTrustDialogAccepted"] = True
        write(cfg, json.dumps(data, indent=2))
    print(f"   trusted: {ROOT}")
    if DRY:
        print("   $ .venv python scripts/overnight.py")
        return
    rc = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "overnight.py")]).returncode
    sys.exit(rc)


def ensure_venv() -> None:
    """ONE interpreter for the repo: .venv. Create, install, re-run inside it (no exec)."""
    if os.path.abspath(sys.prefix) == os.path.abspath(VENV):
        return
    if not os.path.exists(VENV_PY):
        print(f"creating {VENV}")
        subprocess.run([sys.executable, "-m", "venv", VENV], check=True)
        subprocess.run([VENV_PY, "-m", "pip", "install", "-q", "--upgrade", "pip"], check=True)
    subprocess.run([VENV_PY, "-m", "pip", "install", "-q", "-e", ".[dev]"], cwd=ROOT, check=True)
    rc = subprocess.run([VENV_PY, os.path.abspath(__file__), *sys.argv[1:]], cwd=ROOT).returncode
    sys.exit(rc)


def main() -> None:
    global DRY
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print commands, execute nothing")
    ap.add_argument("--reset-inputs", action="store_true", help="forget saved answers and secrets")
    ap.add_argument(
        "--no-build", action="store_true", help="stop after the CI gate; do not launch Claude Code"
    )
    ns = ap.parse_args()
    DRY = ns.dry_run
    ensure_venv()
    os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
    print(f"StudioFace v2 bootstrap  {datetime.now():%Y-%m-%d %H:%M}  root={ROOT}  dry_run={DRY}")
    print(f"interpreter: {sys.executable}")
    print(f"pack version: {read(os.path.join(ROOT, 'PACK-VERSION.txt')).strip()}")
    preflight()
    c = inputs(reset=ns.reset_inputs)
    logins(c)
    validate(c)
    billing_id = gcp_project(c)
    o = terraform(c, billing_id)
    secrets_and_config(c, o, billing_id)
    git_push(o)
    ci_gate()
    if ns.no_build:
        say("9/9 skipped (--no-build): infra applied, code pushed, CI deploys")
        return
    trust_and_launch()


if __name__ == "__main__":
    main()
