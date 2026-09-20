"""Every violation the Python-scanning half of the suite claims to catch.

Same contract as offenders.tsx: each comment names the violation on the line below it, in
the words the scanner hunts for, so a scanner that has not been taught to strip comments
matches the prose and passes for the wrong reason.
"""

import subprocess


def mutating_commands() -> None:
    # A go-live preflight that can change state is not a preflight. Each of these is an
    # argv the tests assert scripts/go_live.py can never build.
    subprocess.run(["terraform", "apply", "-auto-approve"], check=False)
    subprocess.run(["gcloud", "run", "deploy", "api"], check=False)
    subprocess.run(["gh", "secret", "set", "STRIPE_API_KEY"], check=False)
    subprocess.run(["gh", "variable", "set", "NEXT_PUBLIC_STRIPE_PRICE_EUR"], check=False)
    subprocess.run(["git", "push", "origin", "main"], check=False)


def reads_a_secret_value() -> None:
    # Never ours to read, not even to print a prefix of it.
    subprocess.run(
        ["gcloud", "secrets", "versions", "access", "latest", "--secret=stripe-secret-key"],
        check=False,
    )


def logging_offences(logger, order_id: str) -> None:
    # An f-string inside a log call, which formats even when the line is never emitted.
    logger.info(f"order {order_id} delivered")
    # print() instead of a module-level named logger.
    print("delivered")


def swallowed(order_id: str) -> None:
    try:
        deliver(order_id)
    except Exception:  # a bare swallow: the exception goes nowhere
        pass


def deliver(order_id: str) -> None:
    raise NotImplementedError(order_id)
