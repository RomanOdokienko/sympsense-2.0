# Lab Summary UI Plan v1

This file is a handoff note for continuing the lab summary UI work.

## Current status

Already implemented on `main`:

1. Duplicate-aware lab normalization and display-primary logic for CBC-style aliases.
2. Related-method handling for analyzer vs manual microscopy.
3. Grouped lab classification with documented rationale in `docs/lab_classification_v1.md`.
4. Clinical ordering inside groups instead of alphabetic ordering.
5. Lightweight usefulness levels for display rows: `high`, `medium`, `low`.
6. Low-utility rows are collapsed by default inside groups unless search is active or the `low` filter is selected.

Recent commits:

- `7a21666` `ui: sort lab rows clinically`
- `ff52efb` `ui: add lab usefulness levels`

Primary implementation file:

- `scripts/reports/build_documents_review_ui_v2.py`

## What is already true in UI

On `/ui` -> `Анализы`:

- rows are grouped by clinical category;
- rows inside groups are ordered clinically;
- duplicate hiding still works;
- manual microscopy remains expert-oriented behavior;
- usefulness filters exist in the dropdown:
  - `Высокая полезность`
  - `Средняя полезность`
  - `Низкая полезность`
- top stats show compact usefulness counts:
  - `выс.`
  - `низк.`

## Verified before handoff

These checks were run after the usefulness iteration:

- `.venv/bin/python scripts/reports/build_documents_review_ui_v2.py`
- `.venv/bin/python -m pytest tests/test_lab_duplicate_normalization.py`
- browser check on `http://127.0.0.1:8000/ui`

Result:

- UI built successfully
- tests passed: `5 passed`
- new usefulness filters work in browser
- browser was returned to `Все показатели`

## Remaining plan

### Iteration 3: Collapse low-utility rows by default

Status:
Implemented.

Goal:
Make the table easier to scan without deleting or hiding data irreversibly.

Recommended scope:

1. Keep `high` and most `medium` rows visible by default.
2. Move `low` rows into a compact collapsed block per group, for example:
   - `Еще 7 строк`
3. Keep explicit reveal controls inside the same group.
4. Do not physically remove rows from data or from the DOM model.
5. Keep search behavior predictable:
   - search match should reveal matching collapsed rows automatically, or
   - collapsed counts should become zero under a search query.

Important constraint:

- Do not overcomplicate with nested virtualization or separate data stores.
- Reuse existing `usefulness_level` on `labSummaryRows`.

Recommended implementation shape:

1. In `renderLabSummaryTable(items)`, split each group into:
   - visible rows
   - collapsed low-utility rows
2. Render visible rows normally.
3. Render one compact disclosure block below them when collapsed rows exist.
4. Keep `Качественные / без динамики` as a separate display bucket for now.

### Iteration 4: Better archive behavior

Goal:
Reduce noise from rows that are technically present but weakly useful in the default view.

Recommended scope:

1. Review whether some `medium` rows should remain visible only if:
   - they are recent, or
   - they are core markers.
2. Keep `low` rows more aggressively collapsed.
3. Consider a tiny summary line per group like:
   - `12 видно, 5 свернуто`

Important constraint:

- No new medical interpretation yet.
- This is still table ergonomics, not “what matters clinically”.

### Iteration 5: "Что важно" with medical logic

Goal:
Add a focused clinician-like overview that is not just ref-range coloring.

Recommended shape:

1. Build a separate block or tab, not a mutation of the archive table.
2. Include signals such as:
   - current abnormal values
   - important markers missing for a long time
   - patterns that matter in combination
   - important trend shifts even when still inside reference
3. Keep it advisory and heuristic, not diagnostic.

Important constraint:

- Do not mix this logic into `usefulness_level`.
- `usefulness_level` is a UI scanning heuristic.
- `"Что важно"` is a separate clinical-priority layer.

## Practical notes for Claude

If continuing from here, start with:

1. `git status -sb`
2. inspect `renderLabSummaryTable(...)`
3. inspect `labUsefulnessMeta(...)`
4. rebuild UI
5. verify in browser on `/ui`

Good next commit message for iteration 4:

- `ui: refine collapsed lab archive behavior`
