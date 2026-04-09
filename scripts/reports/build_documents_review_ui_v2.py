from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(".")
REGISTRY = ROOT / "data/canonical/documents/batch_01_registry_active.json"
REPORTS_DIR = ROOT / "data/derived/reports"
QUALITY_CFG = ROOT / "configs/quality_gates_v1.json"
OUT = ROOT / "data/derived/reports/ui_documents_registry.html"
OUT_DATA = ROOT / "data/derived/reports/ui_documents_registry_data.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_json_files(directory: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not directory.exists():
        return out
    for p in sorted(directory.glob("*.json")):
        try:
            out.append(load_json(p))
        except Exception:
            continue
    return out


def expected_entities(doc_type: str, cfg: dict[str, Any]) -> list[str]:
    exact = cfg.get("doc_type_requirements", {})
    if doc_type in exact:
        return list(exact[doc_type])
    for prefix, entities in cfg.get("doc_type_prefix_requirements", {}).items():
        if doc_type.startswith(prefix):
            return list(entities)
    return []


def compute_review_flags(
    doctor_records: list[dict[str, Any]],
    recommendation_records: list[dict[str, Any]],
    labs_records: list[dict[str, Any]],
    full_extraction: dict[str, Any] | None,
) -> dict[str, Any]:
    doctor_needs_review = any(str(x.get("status") or "").strip() == "needs_review" for x in doctor_records)
    recommendations_needs_review = any(str(x.get("status") or "").strip() == "needs_review" for x in recommendation_records)
    labs_review_required = any(bool((x.get("quality") or {}).get("review_required")) for x in labs_records)
    full_extraction_review_required = bool(((full_extraction or {}).get("quality") or {}).get("review_required"))

    reasons: list[str] = []
    if doctor_needs_review:
        reasons.append("doctor_conclusions")
    if recommendations_needs_review:
        reasons.append("recommendations")
    if labs_review_required:
        reasons.append("labs")
    if full_extraction_review_required:
        reasons.append("full_extraction")

    return {
        "doctor_needs_review": doctor_needs_review,
        "recommendations_needs_review": recommendations_needs_review,
        "labs_review_required": labs_review_required,
        "full_extraction_review_required": full_extraction_review_required,
        "any_review_required": bool(reasons),
        "reasons": reasons,
    }


def quality_state(row: dict[str, Any], has_full: bool, has_expected: bool, review_required: bool) -> str:
    if row.get("status") == "needs_review" or review_required:
        return "review"
    if has_full and has_expected:
        return "complete"
    return "incomplete"


def esc(s: Any) -> str:
    return html.escape(str(s) if s is not None else "")


def build_file_link(rel_path: str | None) -> dict[str, str] | None:
    if not rel_path:
        return None
    candidate = ROOT / rel_path
    try:
        abs_path = candidate.resolve()
    except Exception:
        return None
    return {
        "href": abs_path.as_uri(),
        "abs_path": str(abs_path),
    }


def flatten_lab_items(lab_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rec in lab_records:
        for section in rec.get("sections") or []:
            if not isinstance(section, dict):
                continue
            section_name = str(section.get("name") or "section")
            for item in section.get("items") or []:
                if not isinstance(item, dict):
                    continue
                out.append(
                    {
                        "section": section_name,
                        "parameter": item.get("parameter"),
                        "result": item.get("result"),
                        "reference": item.get("reference"),
                        "unit": item.get("unit"),
                    }
                )
    return out


def build() -> None:
    registry = load_json(REGISTRY)
    qcfg = load_json(QUALITY_CFG)

    fe_by_doc: dict[str, dict[str, Any]] = {}
    for p in REPORTS_DIR.glob("full_extraction_*.json"):
        try:
            j = load_json(p)
        except Exception:
            continue
        doc_id = str(j.get("doc_id") or "").strip()
        if doc_id:
            j["_path"] = str(p).replace("\\", "/")
            fe_by_doc[doc_id] = j

    doctor_by_doc: dict[str, list[dict[str, Any]]] = {}
    for j in read_json_files(ROOT / "data/canonical/doctor_conclusions"):
        doc_id = str((j.get("source") or {}).get("document_id") or j.get("doc_id") or "").strip()
        if doc_id:
            doctor_by_doc.setdefault(doc_id, []).append(j)

    rec_by_doc: dict[str, list[dict[str, Any]]] = {}
    for j in read_json_files(ROOT / "data/canonical/recommendations"):
        doc_id = str((j.get("source") or {}).get("document_id") or j.get("doc_id") or "").strip()
        if doc_id:
            rec_by_doc.setdefault(doc_id, []).append(j)

    labs_by_doc: dict[str, list[dict[str, Any]]] = {}
    for j in read_json_files(ROOT / "data/canonical/labs"):
        doc_id = str(j.get("doc_id") or (j.get("source") or {}).get("document_id") or "").strip()
        if doc_id:
            labs_by_doc.setdefault(doc_id, []).append(j)

    rows: list[dict[str, Any]] = []
    for idx, row in enumerate(registry, start=1):
        doc_id = str(row.get("id") or "")
        doc_type = str(row.get("doc_type") or "")
        expected = expected_entities(doc_type, qcfg)
        labs_records = labs_by_doc.get(doc_id, [])
        lab_items = flatten_lab_items(labs_records)
        doctor_records = doctor_by_doc.get(doc_id, [])
        recommendation_records = rec_by_doc.get(doc_id, [])
        full_record = fe_by_doc.get(doc_id)

        has_full = doc_id in fe_by_doc
        has_expected = True
        for entity in expected:
            if entity == "doctor_conclusions" and not doctor_records:
                has_expected = False
            elif entity == "recommendations" and not recommendation_records:
                has_expected = False
            elif entity == "labs" and (not labs_records or len(lab_items) == 0):
                has_expected = False
        review_flags = compute_review_flags(
            doctor_records=doctor_records,
            recommendation_records=recommendation_records,
            labs_records=labs_records,
            full_extraction=full_record,
        )

        rows.append(
            {
                "idx": idx,
                "doc_id": doc_id,
                "file_name": row.get("file_name"),
                "doc_type": doc_type,
                "event_date_raw": row.get("event_date_raw"),
                "status": row.get("status"),
                "parse_mode": row.get("parse_mode"),
                "text_len": row.get("text_len"),
                "source_rel": ((row.get("source") or {}).get("relative_path")),
                "pdf_link": build_file_link(((row.get("source") or {}).get("relative_path"))),
                "has_full_extraction": has_full,
                "has_expected_facts": has_expected,
                "expected_entities": expected,
                "quality_status": quality_state(row, has_full, has_expected, review_flags["any_review_required"]),
                "review_required": review_flags["any_review_required"],
                "review_flags": review_flags,
                "doctor_conclusions": doctor_records,
                "recommendations": recommendation_records,
                "labs": labs_records,
                "lab_item_count": len(lab_items),
                "lab_items_preview": lab_items[:40],
                "full_extraction": full_record,
                "full_extraction_link": build_file_link((full_record or {}).get("_path") if full_record else None),
            }
        )

    generated_at = datetime.now(timezone.utc).isoformat()
    rows_json = json.dumps(rows, ensure_ascii=False)
    doc_types = sorted({str(r.get("doc_type") or "") for r in rows})
    data_payload = {
        "generated_at": generated_at,
        "source_registry": str(REGISTRY).replace("\\", "/"),
        "total": len(rows),
        "rows": rows,
    }
    OUT_DATA.parent.mkdir(parents=True, exist_ok=True)
    OUT_DATA.write_text(json.dumps(data_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    options = "".join(f'<option value="{esc(t)}">{esc(t)}</option>' for t in doc_types)
    html_out = f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Documents Review UI</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f7f8fb;color:#111827}}
.wrap{{padding:22px;max-width:1800px;margin:0 auto}}
.h1{{font-size:46px;font-weight:800;margin:0 0 4px}}
.muted{{color:#6b7280}}
.layout{{display:grid;grid-template-columns:56% 44%;gap:16px;margin-top:14px;align-items:start}}
.panel{{background:#fff;border:1px solid #e5e7eb;border-radius:14px}}
.detail-panel{{position:sticky;top:12px;max-height:calc(100vh - 24px);overflow:auto}}
.body{{padding:12px}}
.controls{{display:grid;grid-template-columns:1.6fr 1fr 1fr 1fr 1fr;gap:8px}}
input,select{{padding:9px;border:1px solid #d1d5db;border-radius:10px;font-size:14px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{border-bottom:1px solid #f0f1f3;padding:8px;text-align:left;vertical-align:top}}
tr:hover{{background:#f8fafc;cursor:pointer}}
.badge{{display:inline-block;padding:2px 8px;border-radius:999px;border:1px solid #d1d5db;font-size:12px}}
.complete{{background:#ecfdf5;color:#166534;border-color:#86efac}}
.incomplete{{background:#fffbeb;color:#92400e;border-color:#fde68a}}
.review{{background:#fef2f2;color:#991b1b;border-color:#fca5a5}}
.k{{font-size:12px;color:#6b7280}}
.v{{font-size:14px;white-space:pre-wrap;word-break:break-word}}
.sec{{border-top:1px dashed #e5e7eb;padding-top:10px;margin-top:10px}}
.btn{{display:inline-block;padding:6px 10px;border:1px solid #93c5fd;border-radius:10px;text-decoration:none;color:#1d4ed8;background:#eff6ff}}
.btn-danger{{padding:6px 10px;border:1px solid #ef4444;border-radius:10px;background:#fef2f2;color:#991b1b;cursor:pointer}}
.btn-danger-sm{{padding:4px 8px;font-size:12px;border:1px solid #ef4444;border-radius:10px;background:#fef2f2;color:#991b1b;cursor:pointer}}
.notice{{margin-top:8px;padding:8px 10px;border-radius:10px;font-size:13px;display:none}}
.notice.ok{{display:block;background:#ecfdf5;border:1px solid #86efac;color:#166534}}
.notice.err{{display:block;background:#fef2f2;border:1px solid #fca5a5;color:#991b1b}}
.btn-danger-sm:disabled,.btn-danger:disabled{{opacity:.45;cursor:not-allowed}}
@media (max-width: 1180px){{
  .layout{{grid-template-columns:1fr}}
  .detail-panel{{position:static;max-height:none;overflow:visible}}
}}
</style>
</head>
<body>
<div class="wrap">
  <div class="h1">Documents Review UI</div>
  <div class="muted">Generated at {esc(generated_at)}</div>
  <div id="notice" class="notice"></div>
  <div class="layout">
    <div class="panel">
      <div class="body">
        <div class="controls">
          <input id="q" placeholder="Search file/doc_id/path"/>
          <select id="typeFilter"><option value="">All doc types</option>{options}</select>
          <select id="stateFilter">
            <option value="">All quality states</option>
            <option value="complete">complete</option>
            <option value="incomplete">incomplete</option>
            <option value="review">review</option>
          </select>
          <select id="reviewFilter">
            <option value="">All review flags</option>
            <option value="needs_review">needs_review</option>
            <option value="ok">ok</option>
          </select>
          <select id="sortBy">
            <option value="idx">Original order</option>
            <option value="event_date_raw">Date</option>
            <option value="doc_type">Doc type</option>
            <option value="text_len">Text len</option>
          </select>
        </div>
        <div id="stats" class="muted" style="margin:10px 0"></div>
        <table>
          <thead><tr><th>#</th><th>File</th><th>Type</th><th>Date</th><th>Parse</th><th>Text</th><th>Quality</th><th>Review</th><th>Action</th></tr></thead>
          <tbody id="rows"></tbody>
        </table>
      </div>
    </div>
    <div class="panel detail-panel"><div class="body" id="detail">Выбери документ слева.</div></div>
  </div>
</div>
<script>
let rows = {rows_json};
const q=document.getElementById('q'), tF=document.getElementById('typeFilter'), sF=document.getElementById('stateFilter'), rF=document.getElementById('reviewFilter'), sB=document.getElementById('sortBy');
const tbody=document.getElementById('rows'), detail=document.getElementById('detail'), stats=document.getElementById('stats');
const notice=document.getElementById('notice');
const API_BASE=location.protocol==='file:'?'http://127.0.0.1:8765':'';
let apiReady=false;
function e(s){{ return (s??'').toString().replace(/[&<>\"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}}[m])); }}
function line(v){{ return e(v).replace(/\\n/g,'<br/>'); }}
function apiUrl(path){{ return `${{API_BASE}}${{path}}`; }}
function assetHref(relPath, fallbackHref){{
  if(!relPath) return fallbackHref||'';
  if(location.protocol==='file:') return fallbackHref||'';
  return apiUrl('/api/file?rel=' + encodeURIComponent(relPath));
}}
function setNotice(msg, isError){{
  notice.className = isError ? 'notice err' : 'notice ok';
  notice.textContent = msg;
}}
async function probeApi(){{
  try {{
    const res = await fetch(apiUrl('/api/health'), {{ method:'GET' }});
    if(!res.ok) throw new Error(`HTTP ${{res.status}}`);
    apiReady = true;
    setNotice('Delete API: available.', false);
  }} catch(err) {{
    apiReady = false;
    if(location.protocol==='file:'){{
      setNotice('Delete недоступен: запусти локальный API сервер и открой http://127.0.0.1:8765/ui', true);
    }} else {{
      setNotice(`Delete API недоступен: ${{err.message}}`, true);
    }}
  }}
  filt();
}}
async function deleteDoc(docId){{
  if(!apiReady){{
    setNotice('Delete недоступен: API сервер не отвечает.', true);
    return;
  }}
  const r=rows.find(x=>x.doc_id===docId);
  if(!r) return;
  const ask=confirm(`Delete document ${{r.file_name}} (${{docId}}) and all linked files?`);
  if(!ask) return;
  try {{
    const res=await fetch(apiUrl('/api/delete'), {{
      method:'POST',
      headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{doc_id: docId}})
    }});
    const payload = await res.json().catch(()=>({{}}));
    if(!res.ok) throw new Error(payload.error||`HTTP ${{res.status}}`);
    rows = rows.filter(x => x.doc_id !== docId);
    rows.forEach((x,i)=>x.idx=i+1);
    setNotice(`Deleted ${{docId}}. Removed files: ${{(payload.deleted_paths||[]).length}}.`, false);
    filt();
  }} catch(err) {{
    setNotice(`Delete failed for ${{docId}}: ${{err.message}}`, true);
  }}
}}
function filt(){{
  const qv=q.value.toLowerCase().trim(), tv=tF.value, sv=sF.value, rv=rF.value, sb=sB.value;
  let list=rows.filter(r=> {{
    const hay=[r.file_name,r.doc_id,r.source_rel,r.doc_type].join(' ').toLowerCase();
    const reviewOk = !rv || (rv==='needs_review' ? !!r.review_required : !r.review_required);
    return (!qv || hay.includes(qv)) && (!tv || r.doc_type===tv) && (!sv || r.quality_status===sv) && reviewOk;
  }});
  list.sort((a,b)=> {{
    if(sb==='idx') return a.idx-b.idx;
    const av=(a[sb]??'').toString(), bv=(b[sb]??'').toString();
    return av.localeCompare(bv,'ru');
  }});
  render(list);
}}
function render(list){{
  const c=rows.filter(r=>r.quality_status==='complete').length, i=rows.filter(r=>r.quality_status==='incomplete').length, rw=rows.filter(r=>r.quality_status==='review').length;
  const rr=rows.filter(r=>!!r.review_required).length;
  stats.innerHTML=`Total: <b>${{rows.length}}</b> | complete: <b>${{c}}</b> | incomplete: <b>${{i}}</b> | quality_review: <b>${{rw}}</b> | needs_review_flag: <b>${{rr}}</b> | filtered: <b>${{list.length}}</b>`;
  tbody.innerHTML=list.map(r=>`<tr data-id="${{r.doc_id}}">
    <td>${{r.idx}}</td>
    <td>${{e(r.file_name)}}<div class="muted">${{e(r.doc_id)}}</div></td>
    <td>${{e(r.doc_type)}}</td>
    <td>${{e(r.event_date_raw||'')}}</td>
    <td>${{e(r.parse_mode||'')}}</td>
    <td>${{e(r.text_len||'')}}</td>
    <td><span class="badge ${{r.quality_status}}">${{e(r.quality_status)}}</span></td>
    <td><span class="badge ${{r.review_required?'review':'complete'}}">${{e(r.review_required?'needs_review':'ok')}}</span></td>
    <td><button class="btn-danger-sm" data-del="${{r.doc_id}}" ${{apiReady?'':'disabled title="API unavailable"'}}>Delete</button></td>
  </tr>`).join('');
  [...tbody.querySelectorAll('tr')].forEach(tr=>tr.onclick=()=>show(tr.dataset.id));
  [...tbody.querySelectorAll('button[data-del]')].forEach(btn=>btn.onclick=(ev)=>{{ ev.stopPropagation(); deleteDoc(btn.dataset.del); }});
  if(list.length) show(list[0].doc_id); else detail.innerHTML='Нет документов по фильтрам';
}}
function show(id){{
  const r=rows.find(x=>x.doc_id===id); if(!r) return;
  const dc=(r.doctor_conclusions||[]), rec=(r.recommendations||[]), labs=(r.labs||[]), labItems=(r.lab_items_preview||[]);
  const rf=(r.review_flags||{{}});
  const fe=r.full_extraction||null;
  const conclusionLabel=(r.doc_type||'').startsWith('imaging_report_')
    ? 'imaging_conclusions'
    : 'doctor_conclusions';
  const pdfLink=assetHref(r.source_rel, r.pdf_link?.href||'');
  const feLink=assetHref(fe?._path||'', r.full_extraction_link?.href||'');
  const labText=labItems.length
    ? labItems.map(it=>`${{it.section}}: ${{it.parameter||''}} = ${{it.result||''}}${{it.reference?` (ref: ${{it.reference}})`:''}}`).join('\\n')
    : '';
  detail.innerHTML=`
    <h2 style="margin:0 0 6px">${{e(r.file_name)}}</h2>
    <div class="muted">${{e(r.doc_id)}} | <span class="badge ${{r.quality_status}}">${{e(r.quality_status)}}</span> | review: <span class="badge ${{r.review_required?'review':'complete'}}">${{e(r.review_required?'needs_review':'ok')}}</span> | type: <b>${{e(r.doc_type)}}</b></div>
    <div style="margin:10px 0;display:flex;gap:8px;flex-wrap:wrap">
      ${{pdfLink?`<a class="btn" href="${{pdfLink}}" target="_blank">Open PDF</a>`:''}}
      ${{feLink?`<a class="btn" href="${{feLink}}" target="_blank">Open full_extraction JSON</a>`:''}}
      <button class="btn-danger" onclick="deleteDoc('${{r.doc_id}}')" ${{apiReady?'':'disabled title="API unavailable"'}}>Delete Document</button>
    </div>
    <div class="sec"><div class="k">coverage</div><div class="v">full_extraction=${{r.has_full_extraction}} | expected_facts=${{r.has_expected_facts}} | expected_entities=${{e((r.expected_entities||[]).join(', ')||'none')}}</div></div>
    <div class="sec"><div class="k">review flags</div><div class="v">needs_review=${{e(!!r.review_required)}} | doctor_conclusions=${{e(!!rf.doctor_needs_review)}} | recommendations=${{e(!!rf.recommendations_needs_review)}} | labs=${{e(!!rf.labs_review_required)}} | full_extraction=${{e(!!rf.full_extraction_review_required)}} | reasons=${{e((rf.reasons||[]).join(', ')||'none')}}</div></div>
    <div class="sec"><div class="k">${{conclusionLabel}} (${{dc.length}})</div><div class="v">${{dc.length?line(dc.map(x=>[x.conclusion_text, x.findings_text?('findings: '+x.findings_text):''].filter(Boolean).join('\\n\\n')).join('\\n\\n----\\n\\n')):'none'}}</div></div>
    <div class="sec"><div class="k">recommendations (${{rec.length}})</div><div class="v">${{rec.length?line(rec.map(x=>x.recommendation_text).join('\\n\\n')):'none'}}</div></div>
    <div class="sec"><div class="k">labs (${{labs.length}} records, ${{r.lab_item_count||0}} items)</div><div class="v">${{labItems.length?line(labText):'none'}}</div></div>
    <div class="sec"><div class="k">full extraction summary</div>
      <div class="v">visit_type: ${{e(fe?.summary?.visit_type||'')}}</div>
      <div class="v">recommendation: ${{e(fe?.summary?.recommendation||'')}}</div>
      <div class="v">lab_items_parsed: ${{e(r.lab_item_count||0)}}</div>
    </div>
    <div class="sec"><details><summary>raw excerpt</summary><div class="v">${{line(fe?.raw_text_excerpt||'')}}</div></details></div>
  `;
}}
[q,tF,sF,rF,sB].forEach(x=>x.addEventListener('input',filt));
[tF,sF,rF,sB].forEach(x=>x.addEventListener('change',filt));
filt();
probeApi();
</script>
</body></html>"""

    OUT.write_text(html_out, encoding="utf-8")
    print(str(OUT).replace("\\", "/"))


if __name__ == "__main__":
    build()
