# Lab classification v1

This document explains the lab summary grouping used in the local UI.

## Goals

The classification should be:

- universal enough for new users and new labs;
- useful for scanning a personal medical timeline;
- stable when the raw lab names vary between providers;
- explicit enough to audit when a parameter lands in `Прочее`.

The UI grouping is intentionally not based only on visual section names from PDFs. A document may say `Клинический анализ крови и обмен железа`, but it can contain both CBC and iron metabolism markers. The grouping should follow the analyte meaning first, then specimen/method context.

## External anchors

The grouping follows the same broad mental model as laboratory interoperability standards:

- LOINC treats laboratory observations as reportable clinical measurements and separates them by component/analyte, system/specimen, property, method, and scale. This supports our local key idea: `analyte_id + specimen + method + measurement_kind`.
  Source: https://loinc.org/get-started/scope-of-loinc/
- HL7 FHIR Observation categories keep laboratory observations under a broad `laboratory` category while recognizing common lab areas such as chemistry, hematology, serology, microbiology, virology, cytology, and pathology.
  Source: https://terminology.hl7.org/5.5.0/CodeSystem-observation-category.html

The project does not implement full LOINC mapping yet. Instead, it uses a pragmatic local category catalog that can later be mapped to LOINC where useful.

## Current top-level UI groups

Rows inside each group are ordered clinically rather than alphabetically. Known high-value sequences are encoded in the UI catalog: for example CBC starts with hemoglobin/erythrocyte indices, then leukocytes and differential, then platelets and ESR; chemistry starts with glucose/lipids, then liver, kidney, proteins, electrolytes, and inflammation markers. Unknown rows stay inside their detected group and fall back to name sorting after the known clinical ranks.

The UI also assigns a lightweight usefulness level (`high`, `medium`, `low`) to each display row. This is not a diagnosis and not a clinical recommendation. It is a display heuristic based on recency, number of informative measurements, abnormal flags, and whether the marker belongs to a core screening/longevity set. The purpose is to support later UI steps such as focused filters and collapsing archive-like rows.

### ОАК / гематология

CBC and hematology morphology/count markers:

- leukocytes, erythrocytes, hemoglobin, hematocrit;
- MCV/MCH/MCHC/RDW;
- platelets, MPV, PDW, P-LCR, plateletcrit;
- leukocyte differential: neutrophils, lymphocytes, monocytes, eosinophils, basophils;
- normoblasts, reticulocytes, erythrocyte fragments, atypical mononuclear cells;
- ESR.

Analyzer and manual microscopy are not duplicates. They can be related values for the same analyte and are displayed separately in expert mode.

### Биохимия

General serum/plasma chemistry:

- ALT/AST/GGT and bilirubin;
- glucose, creatinine, urea;
- lipids;
- total protein/albumin;
- electrolytes and minerals: sodium, potassium, chloride, calcium, magnesium.

### Обмен железа / витамины

Grouped separately from general biochemistry because these markers are often reviewed together clinically:

- ferritin, iron, transferrin;
- total/latent iron-binding capacity;
- transferrin saturation;
- vitamin D, B12, folate.

### Гормоны

Endocrine markers:

- TSH, prolactin, FSH, LH;
- testosterone, SHBG, free androgen index;
- DHEA-S, androstenedione, cortisol;
- estradiol, progesterone, 17-OH progesterone.

### Коагулограмма

Coagulation/hemostasis markers:

- PT/prothrombin time;
- prothrombin by Quick;
- INR;
- APTT;
- thrombin time;
- fibrinogen.

### Анализ мочи

Urinalysis markers and urine microscopy:

- color, clarity, relative density, pH;
- protein, glucose, ketones, bilirubin, urobilinogen, nitrites;
- leukocyte esterase;
- erythrocytes/leukocytes/epithelium/bacteria/mucus when the section/specimen is urine.

### Инфекции / серология / ПЦР

Infectious disease and molecular/serology results:

- HIV, hepatitis B/C, syphilis;
- HPV, SARS-CoV-2, CMV, EBV, herpes;
- Chlamydia, Gonorrhoeae, Mycoplasma, Ureaplasma, Candida, Trichomonas, Gardnerella;
- Helicobacter pylori antibodies;
- helminth egg testing.

### Цитология / патология

Non-numeric cytology and pathology reports:

- PAP/Bethesda/Papanicolaou conclusions;
- cytogram and material adequacy;
- histology/pathology conclusions;
- macro/microscopic descriptions.

### Группа крови

Immunohematology identity markers:

- ABO blood group;
- Rh factor.

### Прочее

`Прочее` is an audit bucket, not a desired long-term group. A large `Прочее` count means the classification catalog should be expanded.

## Qualitative / no-dynamics rows

`Качественные / без динамики` is not a medical category. It is a display bucket for rows that do not have useful numeric trend dynamics, such as:

- `не обнаружено`;
- `отрицательно`;
- `отсутствует`.

When possible, these rows should still have an underlying medical category. For example, a negative HIV result is an infection/serology observation, even if the UI may collapse it into a qualitative/no-dynamics block for scanning.

## Implementation rule

Classification should prefer structured context in this order:

1. `analyte_id`, when available.
2. Section/specimen context, for example urine vs blood.
3. Known aliases and keywords.
4. Fallback to `Прочее`.

The UI currently implements this as a local catalog in `scripts/reports/build_documents_review_ui_v2.py`. If the catalog keeps growing, the next step should be moving it to a shared JSON/YAML file with tests.

## Future improvements

- Add canonical analyte ids for iron metabolism, coagulation, infection markers, urinalysis, and cytology/pathology.
- Add a quality gate for `Прочее` share, for example warning when more than 10 percent of display rows land there.
- Add optional LOINC codes for high-value analytes, starting with CBC, core chemistry, iron status, and coagulation.
- Keep raw source names in the fact layer; classification should annotate and group, not rewrite source data.
