from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FACT_LAYER_PATH = ROOT / "scripts/facts/build_fact_layer_v1.py"


def load_fact_layer_module():
    spec = importlib.util.spec_from_file_location("build_fact_layer_v1", FACT_LAYER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


facts = load_fact_layer_module()


def lab_row(
    fact_id: str,
    name: str,
    value_text: str,
    unit: str,
    *,
    method: str = "analyzer",
    value_num: float | None = None,
    measurement_kind: str = "absolute",
) -> dict[str, object]:
    return {
        "fact_id": fact_id,
        "doc_id": "doc_test",
        "analyte_name": name,
        "analyte_id": "monocytes",
        "measurement_kind": measurement_kind,
        "method": method,
        "specimen": "blood",
        "value_text": value_text,
        "value_num": value_num,
        "unit": unit,
        "qa_status": "ok",
    }


def test_cbc_normalization_handles_mixed_cyrillic_latin_mchc() -> None:
    row = facts.infer_cbc_lab_normalization("МСHС (ср. конц. Hb в эр.)", "Клинический анализ крови", "г/дл")

    assert row["analyte_id"] == "mchc"
    assert row["normalized_label"] == "Средняя концентрация Hb в эритроците"


def test_cbc_normalization_marks_manual_microscopy_context_rows() -> None:
    analyzer = facts.infer_cbc_lab_normalization(
        "(LYM#) Лимфоциты",
        "Клинический анализ крови",
        "10*9/л",
        manual_microscopy_context=True,
    )
    manual = facts.infer_cbc_lab_normalization(
        "Лимфоциты",
        "Клинический анализ крови",
        "10*9/л",
        manual_microscopy_context=True,
    )

    assert analyzer["method"] == "analyzer"
    assert manual["method"] == "manual_microscopy"
    assert manual["measurement_kind"] == "absolute"


def test_same_method_cbc_rows_are_duplicates() -> None:
    rows = [
        lab_row("f1", "MONO#) Моноциты", "↓ 0.35", "10*9/л", value_num=0.35),
        lab_row("f2", "Моноциты", "↓ 0.35", "10*9/л", value_num=0.35),
    ]

    facts.annotate_intra_doc_lab_duplicates(rows)

    assert {row["duplicate_role"] for row in rows} == {"primary", "duplicate"}


def test_different_method_cbc_rows_are_related_not_duplicates() -> None:
    rows = [
        lab_row("f1", "LYM#) Лимфоциты", "1.42", "10*9/л", value_num=1.42),
        lab_row("f2", "Лимфоциты", "1.46", "10*9/л", method="manual_microscopy", value_num=1.46),
    ]
    for row in rows:
        row["analyte_id"] = "lymphocytes"

    facts.annotate_intra_doc_lab_duplicates(rows)

    assert [row["duplicate_role"] for row in rows] == ["related", "related"]
    assert all(str(row["duplicate_reason"]).startswith("same_doc_different_method") for row in rows)


def test_unit_family_groups_equivalent_absolute_count_units() -> None:
    assert facts.lab_unit_family("x10^9/л") == "10*9/л"
    assert facts.lab_unit_family("тыс/мкл") == "10*9/л"
    assert facts.lab_unit_family("10*9/л") == "10*9/л"
