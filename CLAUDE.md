# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Read [`STATUS.md`](STATUS.md) first.** This repository is no longer maintained and archived; the successor is [dktzde/max2mqtt](https://github.com/dktzde/max2mqtt).

## Git, commits and pull requests

These rules apply to every session, also to Claude Code on the web.

- **Author:** commits and PRs must look as if the maintainer made them alone. Before the first commit run `git config user.name "dktzde"` and `git config user.email "dktzde@users.noreply.github.com"`. No `Co-Authored-By`, no "Generated with Claude" in commits, PR texts, issues, changelog or README.
- **Branches:** no `claude/` prefix where the environment allows it (Claude Code on the web may force `claude/…`; that is accepted).
- **One topic = one branch = one PR.** One commit per sub-topic. Never force-push a pushed branch; fix mistakes with `git revert`.
- **This is a fork of `MassiPi/maxcube`.** Open PRs against our fork with `gh pr create --repo dktzde/maxcube --base main`, otherwise they land at the upstream.
- **Merge** only when the maintainer explicitly asks, always with a merge commit (no squash).
- **Language:** everything in the repository is English. Commit messages in the imperative, e.g. `fix: …`, `docs: …`, `chore: …`.
- **No secrets or private data** (tokens, passwords, IP addresses, radio addresses, serial numbers, entity IDs) in the repository; use placeholders.
- **Handover:** keep `STATUS.md` up to date after every step.
