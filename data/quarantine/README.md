# quarantine/

Files that failed validation or processing, moved here for review instead of
being silently discarded or kept in the main tree.

## Rules

- Anything in here is **suspicious or broken** — do not trust it.
- Review, then either fix and re-ingest, or delete.
- **Never committed** to git (may contain corrupt/partial source material).
- Quarantine is a deliberate act: pipeline stages move files here only when
  they fail and record the reason alongside.