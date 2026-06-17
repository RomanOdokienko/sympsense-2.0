# Temporary lab duplicate audit note for Claude review

This is a temporary review note with the Codex verification result for the lab duplicate handling PR.

## Audit command

```bash
.venv/bin/python scripts/quality/audit_lab_duplicates_v1.py
```

## Generated report

`data/derived/reports/lab_duplicate_audit_v1_20260617T115756Z.json`

## Totals on current real data

```text
lab_results_count: 656
normalized_lab_results_count: 356

Intra-document:
primary: 8
duplicate: 8
related: 14
intra_document_duplicate_groups_count: 8
related_method_groups_count: 7

Cross-document:
primary: 10
duplicate: 10
cross_document_duplicate_groups_count: 10

flagged_duplicate_rows_count: 30
flagged_cross_document_duplicate_rows_count: 20
```

## CBC alias coverage currently implemented

The `CBC_ANALYTE_RULES` table in `scripts/facts/build_fact_layer_v1.py` covers:

- `wbc` / `лейкоцит` -> `wbc`, `Лейкоциты`
- `hgb` / `гемоглобин` -> `hemoglobin`, `Гемоглобин`
- `hct` / `гематокрит` -> `hematocrit`, `Гематокрит`
- `mcv` / Russian MCV variants -> `mcv`, `Средний объем эритроцита`
- `mchc` / Russian MCHC variants -> `mchc`, `Средняя концентрация Hb в эритроците`
- `mch` / Russian MCH variants -> `mch`, `Среднее содержание Hb в эритроците`
- `rdw-sd` -> `rdw_sd`, `RDW-SD`
- `rdw-cv` / `rdw` -> `rdw_cv`, `RDW-CV`
- `rbc` / `эритроцит` -> `rbc`, `Эритроциты`
- `mpv` / `средний объем тромбоцита` -> `mpv`, `Средний объем тромбоцита`
- `тромбокрит` / `pct` -> `plateletcrit`, `Тромбокрит`
- `pdw` / Russian PDW variants -> `pdw`, `PDW`
- `plt` / `тромбоцит` -> `platelets`, `Тромбоциты`
- `neu` / `нейтрофил` -> `neutrophils`, `Нейтрофилы`
- `lym` / `лимфоцит` -> `lymphocytes`, `Лимфоциты`
- `mono` / `моноцит` -> `monocytes`, `Моноциты`
- `eos` / `эозинофил` -> `eosinophils`, `Эозинофилы`
- `bas` / `базофил` -> `basophils`, `Базофилы`
- `незрелые гранулоциты` -> `immature_granulocytes`, `Незрелые гранулоциты`
- `нормобласт` -> `normoblasts`, `Нормобласты`
- `соэ` -> `esr`, `СОЭ`

## Example intra-document duplicates found

```text
MONO#) Моноциты = Моноциты
value: ↓ 0.35 10*9/л
role: MONO# primary, Моноциты duplicate
reason: same_doc_same_method_exact_text

MONO%) Моноциты = Моноциты, %
value: 8.8% / 9%
role: MONO% primary, Моноциты,% duplicate
reason: same_doc_same_method_near_numeric

LYM#) Лимфоциты = Лимфоциты
value: 1.42 / 1.46 10*9/л
reason: same_doc_same_method_near_numeric

LYM%) Лимфоциты = Лимфоциты, %
value: 36.1% / 37%
reason: same_doc_same_method_near_numeric
```

## Example cross-document duplicates found

In `docbundle_5dd80b551613` for `2025-09-21`, duplicates are detected across separate biochemistry files, including:

- `Аланинаминотрансфераза (АЛТ)`, value `10.6 Ед/л`
- `Аспартатаминотрансфераза (АСТ)`, value `15.9 Ед/л`
- `Билирубин общий`, value `5.4 мкмоль/л`
- `Билирубин прямой (конъюгированный)`, value `1.3 мкмоль/л`
- `Глюкоза (венозной крови) (натощак)`, value `4.93 ммоль/л`

## Known remaining review notes

- `_lab_result_is_display_primary()` is currently duplicated in three files. This is technical debt, not a blocker for this PR, and should be moved to shared utilities in a later PR.
- Regression tests were not added in this iteration.
- Existing `selfcheck` failure remains unrelated to duplicate handling: `body_snapshot_quality_gates_pass=false`, caused by `investigations_without_links_share = 0.5178571428571429`.
