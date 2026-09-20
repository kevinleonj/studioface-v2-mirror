#!/bin/sh
# Shell-side offender fixture. Same contract as offenders.tsx and offenders.py: each
# comment names, in the scanner's own words, the violation on the line below it. A
# scanner that has not been taught to strip shell comments will match the comment
# instead of the command and pass for entirely the wrong reason.
#
# scripts/ci.py mentioned here in a comment, deliberately.

set -e

# the gate invocation the pre-push hook must actually contain
"$PY" scripts/ci.py || exit 1

# an escape hatch that does not demand a reason and writes nothing down
if [ -n "$SF_SKIP_GATE" ]; then
  exit 0
fi

# a push that skips verification entirely
git push --no-verify origin main

echo "REFUSED"
