# READ THIS FIRST

**Before doing anything else in this repo, check git for the current state.** Past sessions have wasted time operating on outdated assumptions about the architecture (e.g. assuming a LaunchAgent 5-min poll when the trigger is now IMAP-driven). Prior-session memory and the README may lag behind the actual code.

## First steps every session

1. `git log --oneline -20` — see what's changed recently.
2. `git status` and `git branch -a` — see uncommitted work and open branches.
3. `git diff main...HEAD` if on a feature branch.
4. Read the actual entry-point files before making claims about how the bot runs:
   - `idealista_bot.py` — main scrape/contact logic
   - `email_listener.py` — current trigger source
   - `scheduler.sh`, `run_bot.sh`, `docker_entrypoint.sh` — how runs are kicked off
   - `.env.example` — required environment variables (compare to `.env` to spot missing keys)

If a prior memory or doc contradicts what's in the code, **trust the code** and update the memory/doc.

## Workflow

All changes go through pull requests against `main`. Do not commit directly to `main`. Workflow:

1. `git checkout -b <branch-name>`
2. Make changes, commit.
3. `git push -u origin <branch-name>`
4. `gh pr create` with a short title and a summary of what changed and why.

Confirm with the user before pushing or opening the PR unless they've already authorized it for this turn.
