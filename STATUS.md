# Status and next steps

Handover file for the maintainer and for Claude Code sessions working on this repository. **Read this first, and update it after every step**, so the next session can continue without the chat history.

Last updated: 2026-10-31 (no longer maintained, repository archived)

## Current state

- **No longer maintained since 2026-10-31.** The maintainer replaced the MAX! Cube by a Cube flashed with a-culfw (used as a network CUL) and the add-on [dktzde/max2mqtt](https://github.com/dktzde/max2mqtt). The README starts with a notice and a short migration guide.
- The repository is **archived** (read-only). Unarchive it in the GitHub settings if something must change.
- Last functional change: 2026-03-23 (`set_programme` service, duty cycle sensors, reconnect fix, `_programming` folder).

## Next steps

- None. Questions and fixes go to [dktzde/max2mqtt](https://github.com/dktzde/max2mqtt).

## Known issues and backlog

- No `LICENSE` file in this fork (the upstream [MassiPi/maxcube](https://github.com/MassiPi/maxcube) has none either at the time of writing – check before reusing code).

## Decisions and conventions

- Fork of [MassiPi/maxcube](https://github.com/MassiPi/maxcube). No pull requests to the upstream are planned.
- Documentation-only changes, no versions.

## Key files

- `maxcube/` – the custom integration (Home Assistant `custom_components/maxcube`).
- `_programming/` – Home Assistant scripts, helpers and a dashboard for syncing a scheduler to the Cube week programmes.
