# Privacy Policy

**coordinator-claude** — a Claude Code plugin by [Dónal O'Duffy](https://github.com/dbc-oduffy)

Last updated: 2026-04-02

## What this plugin does

This plugin provides an engineering management layer for Claude Code — session workflows, multi-persona code review, structured planning, delegation, and handoffs. It coordinates Claude agents (reviewers, executors, enrichers) entirely within your local Claude Code session.

## Data collection

This plugin does **not** collect, transmit, or store any user data. It has no analytics, telemetry, tracking, or external reporting of any kind.

## Where your data goes

All output (plans, reviews, handoffs, lessons) is written to local files in your project directory. Data flows only through services you already use:

- **All workflows** — use Claude Code's built-in tools (file read/write, git, shell). No additional services.

## Third-party services

| Service | When used | Your relationship |
|---------|-----------|-------------------|
| Anthropic (Claude) | All workflows | Your existing Claude Code subscription |

This plugin does not introduce any third-party service relationships beyond what you already have with Anthropic.

## Source code

This plugin is fully open source. You can audit every agent prompt, skill, command, and hook at [github.com/dbc-oduffy/coordinator-claude](https://github.com/dbc-oduffy/coordinator-claude).

## Contact

Questions about this policy: open an issue on the [GitHub repository](https://github.com/dbc-oduffy/coordinator-claude/issues).
