# AGENTS.md — Operating Rules for Coding Agents

TeachMeMusic is a research/software project developed in numbered
development increments (DEV-xxx) under a lightweight, repository-centered
governance system. If you are a coding agent (or human) modifying this
repository, follow these rules.

## Before modifying anything

1. Read `PROJECT_STATUS.md` — where the project is, what is active.
2. Read `README.md` — what the project is and is not.
3. Read `docs/governance.md` — lifecycle, Definitions of Ready/Done, commit rules.
4. Read `docs/architecture.md` — conceptual layers and modularity rules.
5. Read the current increment's record in `docs/development/`.
6. Read the relevant requirements in `docs/requirements/`.
7. Read the relevant ADRs in `docs/decisions/`.
8. Inspect the relevant source and tests, and run `git status`.

## You must

- Work **only within the active increment** shown in `PROJECT_STATUS.md`.
- Respect architectural boundaries (ADR-0001: external parsing-library
  objects terminate at the score-ingestion boundary; layers communicate
  through contracts, not implementation details).
- Keep changes modular; no speculative functionality, no unrelated
  refactoring, no premature abstractions.
- Justify any new dependency in the increment record (or an ADR when
  architectural).
- Preserve stable identifiers: requirement IDs, test IDs, experiment IDs,
  ADR numbers. Never reuse or silently repurpose an ID.
- Never delete or rewrite historical ADRs; supersede by linking.
- Add or update tests for the behavior you change; never fabricate results.
- Update affected documentation, the traceability matrix,
  `PROJECT_STATUS.md`, and `CHANGELOG.md` as part of the change.
- Treat `PROJECT_STATUS.md` as an append-only chronological handoff log. Add a
  dated entry after meaningful work or a status change; never rewrite earlier
  entries, and always leave the exact next action for the next developer or
  LLM.
- Run the full verification suite and report **actual** results:
  `pytest`, `ruff check .`, `ruff format --check .`, `mypy src/teachmemusic`.
- Review the Git diff before finishing and report it honestly.

## You must not

- Begin future increments or invent requirements.
- Mark any requirement, acceptance criterion, or test *Verified* without
  real evidence in the repository.
- Bypass architectural boundaries for convenience.
- Rewrite unrelated working code.
- Commit or push without explicit human approval; **never push** without
  explicit approval.
- Introduce major dependencies casually.
- Expose secrets or machine-specific absolute paths in tracked content.
- Modify files outside this repository.

## When blocked or ambiguous

Stop. Record the blocker in the increment record and `PROJECT_STATUS.md`
(status: BLOCKED with reason), and ask the human. Do not fill major
ambiguity with assumptions.
