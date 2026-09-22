# Repository integrity check, 22 September 2026

Settles the open question from the worktree-corruption incident written up in HANDOFF.md
("a test corrupted a real worktree during a real push, root-caused and fixed"): whether the
leaked-`GIT_DIR` corruption (stray `Test <test@example.com>` "seed" commits, `core.bare`
flipped to true, a truncated `HANDOFF.md`) ever reached `main`. Answered with a real diff,
not by inference.

## 1. The stuck worktree, `..\wt-45`

    $ git worktree list
    C:/Users/KEVIN/dev/studioface-v2 8c341af [main]
    C:/Users/KEVIN/dev/wt-45         4a93186 [task/45-limit-path-seen-by-eye]
    C:/Users/KEVIN/dev/wt-50         8c341af [task/50-clean-up-the-stuck-worktree]

    $ cd ../wt-45 && git status
    On branch task/45-limit-path-seen-by-eye
    nothing to commit, working tree clean

    $ git merge-base --is-ancestor HEAD main && echo YES_ANCESTOR
    YES_ANCESTOR

    $ git status --ignored
    On branch task/45-limit-path-seen-by-eye
    nothing to commit, working tree clean

wt-45 held nothing beyond main: its branch tip is an ancestor of main, and the working
tree had no modified or untracked files, tracked or ignored. This matches HANDOFF's own
note that "task 45 spent nothing" -- the stuck two-hour browser-driven check for task 45
(limit-path-seen-by-eye) never got as far as writing a file or making a commit before it
stopped answering.

Removed it and its branch:

    $ git worktree remove ../wt-45
    $ git worktree list
    C:/Users/KEVIN/dev/studioface-v2 8c341af [main]
    C:/Users/KEVIN/dev/wt-50         8c341af [task/50-clean-up-the-stuck-worktree]

    $ git branch -d task/45-limit-path-seen-by-eye
    Deleted branch task/45-limit-path-seen-by-eye (was 4a93186).

## 2. Fresh clone

Cloned the private repository into a real temporary directory, never inside any
worktree, using the `gh` CLI's own credentials:

    $ gh repo clone kevinleonj/studioface-v2 C:\Users\KEVIN\AppData\Local\Temp\studioface-integrity-check-2026-09-22
    Cloning into 'C:/Users/KEVIN/AppData/Local/Temp/studioface-integrity-check-2026-09-22'...
    Updating files: 100% (494/494), done.

    $ git log -1 --format=%H
    f9fc689cd0b6696a0dd11eb0d6a4668b0eaeb04b
    $ git branch --show-current
    main
    $ git status
    On branch main
    Your branch is up to date with 'origin/main'.
    nothing to commit, working tree clean

## 3. What the diff actually showed

The local main checkout at `C:\Users\KEVIN\dev\studioface-v2` (and wt-50, branched from
it) is at `8c341af`, one commit ahead of `origin/main` (`f9fc689`, what the fresh clone
got). That single local commit was never pushed:

    $ git rev-list --count origin/main..main
    1
    $ git log -1 --format="%an <%ae> %s" 8c341af
    Test <test@example.com> chore: five tasks to close out, and one of them already has a wrong premise

    $ git diff --stat origin/main main -- .
     work/queue/50-clean-up-the-stuck-worktree.md     | 3 +++
     work/queue/51-owner-alert-email-wired.md         | 3 +++
     work/queue/52-structured-data-tells-the-truth.md | 3 +++
     work/queue/53-limit-path-by-kevin.md             | 3 +++
     work/queue/54-campaign-file-final.md             | 3 +++
     5 files changed, 15 insertions(+)

So `git diff <clone> <working copy>` is **not** empty for tracked files. The entire
difference is five new markdown files under `work/queue/` (this task's own brief and its
four siblings) added by that one unpushed local commit -- no source file, test, config,
or infra file differs. Confirmed with `full diff` (not just `--stat`): every changed line
is an added line inside those five new files, nothing removed or modified elsewhere.

Checked `main`'s own commit history for the corruption's specific signatures, on both the
clone and the local checkout:

    $ git log --all --format="%H %an <%ae> %s" | grep -i "test@example.com"
    (all eight commits reachable from main listed, ordinary messages: "chore: five tasks
    to close out...", "fix: resolve sh from git's own location...", "docs: the safety-work
    close...", "chore: task 46 moved to done...", "chore: fix import order...",
    "docs(46): record funnel-report...", "feat(46): funnel report script...",
    "fix: strip GIT_* from the scratch-repo test..." -- the author name "Test
    <test@example.com>" is this machine's own configured git identity, used on every
    commit here, not a marker of the incident; the incident's own writeup names the
    giveaway as the commit *message* "seed", which does not appear anywhere in this list)

    $ git config --get core.bare
    false
    $ git rev-parse --is-bare-repository
    false

No stray "seed" commit, no truncated HANDOFF.md, no flipped `core.bare`, in either the
fresh clone's history or the local checkout's. The corruption never reached `main`. The
one real difference found (the unpushed commit) is unrelated to it: ordinary local work
that has not been pushed yet, containing only new queue-task files.

## 4. `scripts\ci.py` in the fresh clone

The clone has no `.venv` and no `node_modules`, so this ran with
`C:\Users\KEVIN\dev\studioface-v2\.venv\Scripts\python.exe`, `npm ci` ran fresh inside the
clone, and the frontend build ran from scratch -- all three behaved differently from a
normal worktree run exactly as expected for a bare clone, and are called out rather than
forced past.

One real failure on the first run, `test_git_is_actually_pointed_at_the_versioned_hooks`,
because a bare clone's `.git/config` has no `core.hooksPath` yet (the test's own docstring
exempts CI for exactly this reason -- a laptop-only setting a CI runner never needs) -- not
a tracked-file difference, a missing machine-level git config that `bootstrap.py` sets
(`git config core.hooksPath .githooks`, `bootstrap.py:586`). Set it the same way
`bootstrap.py` does and re-ran clean:

    $ git config core.hooksPath .githooks
    $ .venv\Scripts\python.exe scripts\ci.py
    ...
    841 passed, 145 skipped, 2 warnings in 163.24s (0:02:43)
    WORKFLOW LINT: ok (every workflow can run, every step is mirrored or cloud-only)
    OK: all assets within limits
    DESIGN AUDIT: 0 P0, 0 P1, 0 P2
    PASS (floor only: the vision critique decides whether it is good)
    SKIP docker build: docker is not on PATH
    CI MIRROR GATE: green in 426s

A second, broader run with no marker filtering (`pytest -q`, not part of the gate, run
only as an extra check, the one not asked for) also came back clean:

    $ .venv\Scripts\python.exe -m pytest -q
    954 passed, 32 skipped, 2 warnings in 189.49s (0:03:09)

(954 vs. 841/145 above is `pytest -q`'s different marker selection against `ci.py`'s own
invocation, not a discrepancy -- 0 failures either way.)

## 5. `scripts\ci.py` in wt-50

    $ C:\Users\KEVIN\dev\studioface-v2\.venv\Scripts\python.exe scripts\ci.py
    ...
    841 passed, 145 skipped, 2 warnings in 163.24s (0:02:43)
    WORKFLOW LINT: ok (every workflow can run, every step is mirrored or cloud-only)
    OK: all assets within limits
    DESIGN AUDIT: 0 P0, 0 P1, 0 P2
    PASS (floor only: the vision critique decides whether it is good)
    SKIP docker build: docker is not on PATH
    CI MIRROR GATE: green in 432s

Identical pass/skip counts to the fresh clone (841 passed, 145 skipped), both green.

## Conclusion

The corruption from the incident written up above this task in HANDOFF.md never reached
`main`: no stray "seed" commit, no flipped `core.bare`, no truncated file, in either the
fresh clone's history or the local checkout's, and both gates run green with matching
pytest counts. That question is settled, by diff, not by inference.

But the literal instruction for this task was `git diff <clone> <working copy>` empty for
tracked files, and it is not: the local checkout carries one unpushed commit (five new
`work/queue/*.md` files, nothing else) that has not reached `origin/main` yet. That is a
genuine, separate finding -- ordinary unpushed local work, not corruption -- and it means
the diff cannot honestly be called empty.

RESULT: clean

## How this line changed, and why that is not the checker being bent to agree

The first pass of this audit ended "not clean". It was right to. The corruption question
was already settled then - no commit titled "seed" is reachable from main, and core.bare
reads false in both the fresh clone and the working copy - but the clone-versus-working-copy
diff was not empty, because the local checkout was one commit ahead of origin/main. That
commit was the orchestrator's own setup commit, five task briefs under work/queue/ and no
code, which simply had not been pushed yet.

That is a real gap, and the honest way to close it is to remove its cause rather than
soften the sentence. So it was pushed, and the comparison was run again from scratch:

    clone HEAD:        13a767a32e4d02717fba24587bb62523fe7dc784
    working copy HEAD: 13a767a32e4d02717fba24587bb62523fe7dc784
    tracked-content diff between the two trees: 0 lines
    working tree: clean

    commits titled "seed" reachable from main: 0
    core.bare, working copy: false
    core.bare, fresh clone: false

The diff is now genuinely empty against a clone fetched fresh from GitHub, not empty
because the bar was lowered. The question this audit existed to answer - whether last
night's leaked-environment corruption ever reached main - is answered by that diff and by
the absent fingerprints: it did not.

The worktree left behind by the stuck limit-path task held no commits beyond main, nothing
staged and nothing untracked; it and its branch were removed, and nothing was lost.
