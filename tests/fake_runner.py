"""A stand-in local runner for tests/test_workflow_lint.py. Never executed.

workflow_lint decides whether a workflow step has a local mirror by looking for the
step's key command inside the runner's SOURCE. The tests therefore need a runner whose
text contains those keys but whose behaviour is irrelevant, so they can assert on the
linter rather than on whatever scripts/ci.py happens to run this week.

Keeping it separate from scripts/ci.py is the point: a test that pointed at the real
runner would pass or fail for reasons that have nothing to do with the linter.
"""

STEPS_THIS_RUNNER_MIRRORS = (
    "ruff check .",
    "pytest -q",
    "pip install -e .[dev]",
    "python scripts/ci.py",
    "python scripts/design_audit.py frontend/out",
    "docker build -t studioface-api .",
)

if __name__ == "__main__":
    raise SystemExit("fixture only; not a runnable gate")
