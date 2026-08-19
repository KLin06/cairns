# Contract: Backfill CLI

This feature has no HTTP/API surface — its interface is a command-line script,
`server/db/backfill.py`. This is the contract other tooling (a Makefile target, a CI step, a
human operator) can rely on.

## Invocation

```
python -m db.backfill [trail_id ...]
```

Run from `server/`, with `DATABASE_URL` set (same `.env` convention as the rest of `server/`).

- No arguments → process every eligible trail (every `enriched_descriptions/*.json` file).
- One or more `trail_id` arguments → process only those trails (still subject to the same
  eligibility check per trail — an explicitly-named trail with no enriched description is
  reported as skipped, not an error, consistent with FR-001 applying uniformly).

## Behavior guarantees (traced to spec.md FRs)

- Idempotent: running the same invocation twice with unchanged source files leaves storage
  identical after both runs, including `updated_at` values — the second run's upserts still
  execute but no row's data actually changes, so `updated_at` is the only thing that could move,
  and per FR-005 that must not update the timestamp when nothing else changed. *(Planning note:
  either compare before writing and skip the upsert set when unchanged, or accept the
  `updated_at` still refreshing — the spec text doesn't clearly pick one. Recommend comparing
  first and skipping unchanged writes, so `updated_at` stays meaningful. Confirm during
  implementation review.)*
- Never partially writes a table's `NOT NULL` columns — each entity's upsert either has every
  value it needs or is not attempted at all (no entity is ever half-written).
- Continues past a single trail's failure (FR-008); that trail's error is recorded, not raised
  out of the run.

## Output (stdout, end of run)

One line per processed trail, plus a summary line. Exact format is an implementation detail, but
the content must include, per trail: `trail_id`, which of the three tables were written, and
error text if it failed — and, in the summary, total attempted / succeeded / failed counts. This
is what "report which trails succeeded and which failed" (FR-009) means operationally.

## Exit code

- `0` if every eligible trail (or every explicitly-named trail that was actually eligible)
  processed without error.
- Non-zero if at least one trail's processing raised an error — lets this be wired into CI/a
  Makefile target without swallowing failures silently, without that failure having stopped the
  rest of the run (FR-008 still holds; the non-zero exit is just the run-level signal).

## Non-goals

- Not a long-running service, not scheduled by this feature (a cron/CI wrapper calling it
  periodically is a separate, later concern, out of scope here per spec.md's Assumptions).
- Does not modify anything under `data/datasets/` — read-only against the pipeline output.
- Does not remove storage rows for trails whose source files have since disappeared (spec.md
  Edge Cases — explicitly out of scope).
