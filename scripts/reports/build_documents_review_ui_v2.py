from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(".")
OUT = ROOT / "data/derived/reports/ui_documents_registry.html"
OUT_DATA = ROOT / "data/derived/reports/ui_documents_registry_data.json"


def build() -> None:
    generated_at = datetime.now(timezone.utc).isoformat()

    # Kept for backward compatibility with tooling expecting this artifact.
    OUT_DATA.parent.mkdir(parents=True, exist_ok=True)
    OUT_DATA.write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "mode": "api_driven",
                "source": "http://127.0.0.1:8000/v1/review/documents",
                "rows": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    html_out = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Sympsense 2.0</title>
<style>
:root{
  --bg:#13161c;--panel:#1e2230;--panel2:#252a38;--line:#2d3348;
  --text:#e8eaf0;--muted:#7b82a0;
  --green:#4ade80;--amber:#f59e0b;--red:#f87171;--blue:#60a5fa;
}
body{font-family:Segoe UI,Arial,sans-serif;margin:0;background:var(--bg);color:var(--text)}
.wrap{padding:22px;max-width:1800px;margin:0 auto}
.h1{font-size:24px;font-weight:700;margin:0 0 3px;color:var(--text)}
.muted{color:var(--muted)}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;min-width:0}
.body{padding:14px}
.notice{margin-top:10px;padding:8px 12px;border-radius:8px;font-size:13px;display:none}
.notice.ok{display:block;background:#052e16;border:1px solid #166534;color:var(--green)}
.notice.err{display:block;background:#1a0808;border:1px solid #7f1d1d;color:var(--red)}
.quality-chip{display:inline-block;padding:2px 9px;border-radius:999px;border:1px solid var(--line);font-size:12px;color:var(--muted)}
.quality-pass{background:#052e16;color:var(--green);border-color:#166534}
.quality-fail{background:#1a0808;color:var(--red);border-color:#7f1d1d}
.quality-unknown{background:var(--panel2);color:var(--muted);border-color:var(--line)}
.tabbar{display:flex;gap:6px;flex-wrap:wrap}
.tab-btn{padding:6px 14px;border:1px solid var(--line);border-radius:8px;background:var(--panel);color:var(--muted);cursor:pointer;font-size:13px;text-decoration:none;transition:border-color .15s,color .15s;line-height:1.4}
.tab-btn:hover{color:var(--text);border-color:var(--blue)}
.tab-btn.active{background:var(--panel2);border-color:var(--blue);color:var(--text)}
.toolbar{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:12px;flex-wrap:wrap}
.switch{display:inline-flex;align-items:center;gap:8px;color:var(--muted);font-size:13px}
.switch input[type="checkbox"]{accent-color:var(--blue)}
.view{display:none;margin-top:14px}
.view.active{display:block}
.docs-layout{display:grid;grid-template-columns:minmax(0,58%) minmax(0,42%);gap:14px;align-items:start}
.detail-panel{position:sticky;top:12px;max-height:calc(100vh - 24px);overflow:auto}
.controls{display:grid;grid-template-columns:1.8fr 1fr 1.2fr;gap:8px}
input,select{padding:8px 10px;border:1px solid var(--line);border-radius:8px;font-size:13px;width:100%;box-sizing:border-box;background:var(--panel2);color:var(--text)}
input::placeholder{color:var(--muted)}
select option{background:var(--panel2)}
select{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.controls>*{min-width:0}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{border-bottom:1px solid var(--line);padding:8px;text-align:left;vertical-align:top;color:var(--text)}
th{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
tbody#rows tr:hover{background:var(--panel2);cursor:pointer}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;border:1px solid var(--line);font-size:12px;color:var(--muted)}
.complete{background:#052e16;color:var(--green);border-color:#166534}
.incomplete{background:#1a1000;color:var(--amber);border-color:#92400e}
.review{background:#1a0808;color:var(--red);border-color:#7f1d1d}
.type-chip{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;background:var(--panel2);border:1px solid var(--line);color:var(--muted)}
.type-labs{background:#0a1428;color:var(--blue);border-color:#1e3a6a}
.type-consult{background:#052e16;color:var(--green);border-color:#166534}
.type-imaging{background:#1a1000;color:var(--amber);border-color:#92400e}
.type-other{background:var(--panel2);color:var(--muted);border-color:var(--line)}
.k{font-size:12px;color:var(--muted)}
.v{font-size:13px;white-space:pre-wrap;word-break:break-word;color:var(--text)}
.sec{border-top:1px solid var(--line);padding-top:10px;margin-top:10px}
.btn{display:inline-block;padding:5px 10px;border:1px solid #1e3a6a;border-radius:8px;text-decoration:none;color:var(--blue);background:#0a1428;font-size:12px}
.btn-danger{padding:5px 10px;border:1px solid #7f1d1d;border-radius:8px;background:#1a0808;color:var(--red);cursor:pointer;font-size:12px}
.btn-danger-sm{padding:3px 8px;font-size:11px;border:1px solid #7f1d1d;border-radius:6px;background:transparent;color:var(--red);cursor:pointer}
.btn-danger-sm:disabled,.btn-danger:disabled{opacity:.35;cursor:not-allowed}
.card-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
.card{border:1px solid var(--line);border-radius:10px;padding:10px;background:var(--panel2)}
.card .k{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px}
.card .num{font-size:22px;font-weight:700;color:var(--text)}
.lab-table{width:100%;table-layout:fixed}
.lab-table th{font-size:11px;color:var(--muted);background:transparent;font-weight:600;text-transform:uppercase;letter-spacing:.06em}
.lab-table td{font-size:13px;color:var(--text)}
.lab-table th,.lab-table td{word-break:break-word}
.analytics-list{margin-top:8px}
.analytics-row{padding:6px 0;border-bottom:1px solid var(--line);color:var(--text)}
.analytics-row:last-child{border-bottom:none}
.queue-item{border:1px solid var(--line);border-radius:10px;padding:10px;margin:8px 0;background:var(--panel2)}
.queue-item .meta{font-size:12px;color:var(--muted);margin-bottom:6px}
.queue-item .txt{font-size:13px;line-height:1.4;color:var(--text)}
.link-btn{font-size:12px;padding:3px 8px;border:1px solid var(--line);border-radius:6px;background:var(--panel2);color:var(--muted);cursor:pointer}
.link-btn:hover{border-color:#1e3a6a;color:var(--blue)}
.queue-controls{display:grid;grid-template-columns:1.1fr 0.8fr 0.6fr 0.6fr;gap:6px;margin-bottom:8px}
.lab-summary-controls{display:grid;grid-template-columns:1.6fr 1fr 1fr;gap:8px;margin-bottom:8px}
.lab-trend-up{color:var(--red);font-weight:600}
.lab-trend-down{color:var(--blue);font-weight:600}
.lab-trend-flat{color:var(--muted);font-weight:600}
.lab-value-ok{color:var(--green);font-weight:600}
.lab-value-alert{color:var(--red);font-weight:600}
details.sec summary{cursor:pointer;user-select:none;color:var(--text)}
details.sec[open] summary{margin-bottom:6px}
.briefing-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:12px}
.briefing-section{border:1px solid var(--line);border-radius:12px;padding:14px;background:var(--panel2)}
.briefing-section h3{margin:0;font-size:14px;font-weight:600;color:var(--text)}
.briefing-sub{margin-top:3px;color:var(--muted);font-size:12px}
.briefing-list{display:flex;flex-direction:column;gap:6px;margin-top:10px}
.briefing-item{border:1px solid var(--line);border-radius:8px;padding:10px;background:var(--panel)}
.briefing-item .head{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}
.briefing-item .title{font-weight:600;font-size:13px;color:var(--text)}
.briefing-item .meta{font-size:11px;color:var(--muted);margin-top:3px}
.briefing-item .txt{font-size:13px;line-height:1.4;margin-top:5px;color:var(--muted)}
.briefing-bullets{margin:8px 0 0 0;padding-left:18px}
.briefing-bullets li{margin:4px 0;font-size:13px;color:var(--muted)}
.prio-chip{display:inline-flex;align-items:center;border-radius:999px;font-size:11px;padding:2px 8px;border:1px solid;white-space:nowrap}
.prio-high{background:#1a0808;color:var(--red);border-color:#7f1d1d}
.prio-medium{background:#1a1000;color:var(--amber);border-color:#92400e}
.prio-low{background:#0a1428;color:var(--blue);border-color:#1e3a6a}
.briefing-checklist{margin:8px 0 0 0;padding-left:18px}
.briefing-checklist li{margin:6px 0}
@media(max-width:1180px){
  .docs-layout{grid-template-columns:1fr}
  .detail-panel{position:static;max-height:none;overflow:visible}
  .card-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
  .queue-controls{grid-template-columns:1fr 1fr}
  .lab-summary-controls{grid-template-columns:1fr 1fr}
  .controls{grid-template-columns:1fr 1fr}
  .briefing-grid{grid-template-columns:1fr}
}
</style>
</head>
<body>
<div class="wrap">
  <div style="display:flex;justify-content:space-between;align-items:baseline">
    <div class="h1">Sympsense 2.0</div>
    <a href="/longevity" style="font-size:13px;color:var(--muted);text-decoration:none">Longevity ↗</a>
  </div>
  <div class="muted" id="qualityLine" style="font-size:12px;margin-top:2px"></div>
  <div id="notice" class="notice"></div>

  <div class="toolbar">
    <div class="tabbar">
      <button class="tab-btn active" data-view="briefing">Сводка</button>
      <button class="tab-btn" data-view="labs">Анализы</button>
      <button class="tab-btn" data-view="docs">Документы</button>
      <button class="tab-btn" data-view="review" data-advanced="true">Проверка фактов</button>
      <button class="tab-btn" data-view="analytics" data-advanced="true">Граф связей</button>
    </div>
    <label class="switch">
      <input id="advancedModeToggle" type="checkbox"/>
      Экспертный режим
    </label>
  </div>

  <div id="view-docs" class="view">
    <div class="docs-layout">
      <div class="panel">
        <div class="body">
          <div class="controls">
            <input id="q" placeholder="Поиск по названию, содержимому, doc_id"/>
            <select id="typeFilter"><option value="">Все типы документов</option></select>
            <label class="switch" style="padding:0 8px;border:1px solid var(--line);border-radius:8px;background:var(--panel2)">
              <input id="problemOnlyToggle" type="checkbox"/>
              Только проблемные
            </label>
          </div>
          <div id="stats" class="muted" style="margin:10px 0"></div>
          <table>
            <thead><tr><th>#</th><th>Файл</th><th>Тип</th><th>Дата</th><th>Качество</th><th>Действие</th></tr></thead>
            <tbody id="rows"></tbody>
          </table>
        </div>
      </div>
      <div class="panel detail-panel"><div class="body" id="detail">Выберите документ в таблице слева.</div></div>
    </div>
  </div>

  <div id="view-labs" class="view">
    <div class="panel"><div class="body">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <div>
          <div style="font-size:15px;font-weight:600;color:var(--text)">Анализы: динамика по годам</div>
          <div style="font-size:12px;color:var(--muted);margin-top:2px">по каждому показателю — значения по годам; пусто — не сдавался</div>
        </div>
        <button id="labSummaryRefreshBtn" class="link-btn" title="Обновить">↺</button>
      </div>
      <div class="lab-summary-controls">
        <input id="labSummarySearch" placeholder="Поиск по показателю"/>
        <select id="labSummaryFlagFilter">
          <option value="">Все показатели</option>
          <option value="abnormal">Есть отклонения</option>
          <option value="normal">Без отклонений</option>
        </select>
        <div id="labSummaryStats" class="muted"></div>
      </div>
      <div id="labSummaryPanel" class="muted">Загрузка...</div>
    </div></div>
  </div>
  <div id="view-review" class="view" data-advanced="true">
    <div class="panel"><div class="body">
      <div style="margin-bottom:12px">
        <div style="font-size:15px;font-weight:600;color:var(--text)">Очередь проверки фактов</div>
        <div style="font-size:12px;color:var(--muted);margin-top:2px">обрабатываются только спорные элементы базы</div>
      </div>
      <div class="queue-controls">
        <select id="factCollectionFilter">
          <option value="">Все коллекции</option>
          <option value="condition_mentions">condition_mentions</option>
          <option value="clinical_findings">clinical_findings</option>
          <option value="condition_investigation_links">condition_investigation_links</option>
          <option value="lab_results">lab_results</option>
          <option value="recommendation_items">recommendation_items</option>
          <option value="medication_items">medication_items</option>
        </select>
        <select id="factStateFilter">
          <option value="open">open (только открытые)</option>
          <option value="all">all (все)</option>
          <option value="resolved">resolved (подтвержденные)</option>
          <option value="skipped">skipped (пропущенные)</option>
        </select>
        <select id="factLimitFilter">
          <option value="12">12</option>
          <option value="30">30</option>
          <option value="60">60</option>
        </select>
        <button id="factQueueRefreshBtn" class="link-btn">Обновить</button>
      </div>
      <div id="factQueue" class="muted">Загрузка...</div>
    </div></div>
  </div>

  <div id="view-analytics" class="view" data-advanced="true">
    <div class="panel"><div class="body">
      <div style="margin-bottom:12px">
        <div style="font-size:15px;font-weight:600;color:var(--text)">Граф связей</div>
        <div style="font-size:12px;color:var(--muted);margin-top:2px">кластеры состояний и связанные исследования</div>
      </div>
      <div id="analyticsSnapshot" class="muted">Загрузка...</div>
      <div class="sec">
        <div class="k">Детализация по кластеру</div>
        <select id="analyticsClusterSelect" style="margin-top:6px">
          <option value="">Выберите кластер состояния...</option>
        </select>
        <div id="analyticsDrilldown" class="analytics-list muted">Выберите кластер</div>
      </div>
    </div></div>
  </div>

  <div id="view-briefing" class="view active">
    <div class="panel"><div class="body">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
        <div>
          <div style="font-size:15px;font-weight:600;color:var(--text)">Краткая медицинская сводка</div>
          <div style="font-size:12px;color:var(--muted);margin-top:2px">ключевые состояния и динамика по собранным документам</div>
        </div>
        <div style="display:flex;gap:6px">
          <button id="briefingRefreshBtn" class="link-btn" title="Обновить">↺</button>
          <button id="briefingBuildBtn" class="link-btn">Пересчитать</button>
        </div>
      </div>
      <div id="briefingPanel" class="muted">Загрузка...</div>
    </div></div>
  </div>
</div>
<script>
let rows = [];
let selectedDocId = '';
let deleteApiReady = false;
let analyticsGraphCache = { nodes: [], edges: [] };
let activeView = 'briefing';
let advancedModeEnabled = false;
let latestQualityPayload = null;
let labSummaryRows = [];
let labSummaryYears = [];

const FALLBACK_API_BASE = 'http://127.0.0.1:8000';
const API_BASE = location.protocol === 'file:' ? FALLBACK_API_BASE : window.location.origin;

const q=document.getElementById('q'), tF=document.getElementById('typeFilter');
const tbody=document.getElementById('rows'), detail=document.getElementById('detail'), stats=document.getElementById('stats');
const problemOnlyToggleEl=document.getElementById('problemOnlyToggle');
const notice=document.getElementById('notice');
const qualityLineEl=document.getElementById('qualityLine');
const analyticsSnapshotEl=document.getElementById('analyticsSnapshot');
const analyticsClusterSelectEl=document.getElementById('analyticsClusterSelect');
const analyticsDrilldownEl=document.getElementById('analyticsDrilldown');
const factQueueEl=document.getElementById('factQueue');
const factCollectionFilterEl=document.getElementById('factCollectionFilter');
const factStateFilterEl=document.getElementById('factStateFilter');
const factLimitFilterEl=document.getElementById('factLimitFilter');
const factQueueRefreshBtn=document.getElementById('factQueueRefreshBtn');
const briefingPanelEl=document.getElementById('briefingPanel');
const briefingRefreshBtn=document.getElementById('briefingRefreshBtn');
const briefingBuildBtn=document.getElementById('briefingBuildBtn');
const advancedModeToggleEl=document.getElementById('advancedModeToggle');
const labSummaryPanelEl=document.getElementById('labSummaryPanel');
const labSummaryStatsEl=document.getElementById('labSummaryStats');
const labSummarySearchEl=document.getElementById('labSummarySearch');
const labSummaryFlagFilterEl=document.getElementById('labSummaryFlagFilter');
const labSummaryRefreshBtn=document.getElementById('labSummaryRefreshBtn');

function e(s){
  return (s??'').toString()
    .replace(/&/g,'&amp;')
    .replace(/</g,'&lt;')
    .replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;')
    .replace(/'/g,'&#39;');
}
function line(v){ return e(v).replace(/\\n/g,'<br/>'); }
function readApiUrl(path){ return `${API_BASE}${path}`; }
function deleteApiUrl(path){ return `${API_BASE}${path}`; }
function parseNum(v){ const n=Number(v); return Number.isFinite(n)?n:0; }
function setNotice(msg, isError){ notice.className = isError ? 'notice err' : 'notice ok'; notice.textContent = msg; }
function toDateObject(isoDate){
  const s = (isoDate || '').toString().trim();
  if(!/^\\d{4}-\\d{2}-\\d{2}$/.test(s)) return null;
  const dt = new Date(`${s}T00:00:00Z`);
  return Number.isFinite(dt.getTime()) ? dt : null;
}
function daysBetweenInclusive(startDate, endDate){
  const a = toDateObject(startDate);
  const b = toDateObject(endDate);
  if(!a || !b) return 0;
  const diff = Math.round((b.getTime() - a.getTime()) / 86400000);
  return Math.max(0, diff) + 1;
}
function trendClassAndLabel(trend){
  if(trend === 'up') return { cls: 'lab-trend-up', label: 'рост' };
  if(trend === 'down') return { cls: 'lab-trend-down', label: 'снижение' };
  return { cls: 'lab-trend-flat', label: trend === 'flat' ? 'без явного тренда' : 'недостаточно данных' };
}

function setActiveView(view){
  activeView = view;
  document.querySelectorAll('.view').forEach(el=>el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el=>el.classList.remove('active'));
  const section = document.getElementById(`view-${view}`);
  if(section) section.classList.add('active');
  const btn = document.querySelector(`.tab-btn[data-view="${view}"]`);
  if(btn) btn.classList.add('active');
}

function setAdvancedMode(enabled){
  advancedModeEnabled = !!enabled;
  document.querySelectorAll('[data-advanced="true"]').forEach(el => {
    el.style.display = advancedModeEnabled ? '' : 'none';
  });
  renderQualityLine();
  if(!advancedModeEnabled && (activeView === 'review' || activeView === 'analytics')){
    setActiveView('briefing');
  }
  if(advancedModeEnabled){
    loadFactQueue().catch(err => setNotice(`Не удалось загрузить очередь фактов: ${err.message}`, true));
    loadAnalyticsSnapshot().catch(err => setNotice(`Не удалось загрузить граф связей: ${err.message}`, true));
  }
}

function openDoc(docId){
  setActiveView('docs');
  show(docId);
}

function toIsoDateKey(raw){
  const s=(raw||'').toString().trim();
  if(!s) return '';
  if(/^\\d{4}-\\d{2}-\\d{2}$/.test(s)) return s;
  const m=s.match(/^(\\d{2})\\.(\\d{2})\\.(\\d{4})$/);
  if(!m) return s;
  return `${m[3]}-${m[2]}-${m[1]}`;
}

function buildTypeOptions(){
  const types = [...new Set(rows.map(r => (r.doc_type||'').toString()).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'ru'));
  tF.innerHTML = '<option value="">Все типы документов</option>' + types.map(t => `<option value="${e(t)}">${e(docTypeLabel(t))}</option>`).join('');
}

function qualityChip(status){
  const s=(status||'unknown').toString().toLowerCase();
  const cls=s==='pass'?'quality-pass':(s==='fail'?'quality-fail':'quality-unknown');
  return `<span class="quality-chip ${cls}">${e(s)}</span>`;
}

function qualityLabel(status){
  const s=(status||'').toString().toLowerCase();
  if(s==='complete') return 'готово';
  if(s==='incomplete') return 'частично';
  if(s==='review') return 'на проверке';
  return s || 'неизвестно';
}

function docFamily(docType){
  const dt = (docType || '').toString().toLowerCase();
  if(dt === 'lab_report' || dt.includes('lab')) return 'labs';
  if(dt === 'doctor_consultation' || dt.includes('consult')) return 'consult';
  if(dt.startsWith('imaging_report_') || dt.includes('mri') || dt.includes('xray') || dt.includes('ct')) return 'imaging';
  return 'other';
}

function docTypeLabel(docType){
  const dt = (docType || '').toString().toLowerCase();
  const map = {
    lab_report: 'Анализы',
    doctor_consultation: 'Консультация врача',
    imaging_report_mri: 'Снимок (МРТ)',
    imaging_report_xray: 'Снимок (Рентген)',
    imaging_report_ct: 'Снимок (КТ)',
    imaging_report_ultrasound: 'Снимок (УЗИ)',
  };
  if(map[dt]) return map[dt];
  if(dt.startsWith('imaging_report_')) return 'Снимок';
  if(!dt) return 'Не указан';
  return dt.replace(/_/g, ' ');
}

function docFamilyLabel(family){
  const map = {
    labs: 'Анализы',
    consult: 'Консультации',
    imaging: 'Снимки',
    other: 'Прочее',
  };
  return map[family] || 'Прочее';
}

function prettifyFileName(name){
  const src = (name || '').toString().trim();
  if(!src) return '';
  let base = src.replace(/\\.pdf$/i, '');
  base = base.replace(/[_]+/g, ' ').replace(/\\s+/g, ' ').trim();
  base = base.replace(/Rezul'?tatyanalizovot/gi, 'Результат анализов от ');
  base = base.replace(/report-\\d+-\\d+/gi, 'Медицинский отчет');
  base = base.replace(/\\(\\s*(\\d+)\\s*\\)/g, '#$1');
  base = base.replace(/\\s{2,}/g, ' ').trim();
  if(base.length > 95) base = `${base.slice(0, 95)}...`;
  return base || src;
}

function isProblematicRow(r){
  return !!r.review_required || (r.quality_status||'') !== 'complete' || r.has_expected_facts === false || r.has_full_extraction === false;
}

function renderQualityLine(){
  if(!qualityLineEl || !latestQualityPayload) return;
  const payload = latestQualityPayload;
  const q = payload.reports?.quality_gates_v1;
  const b = payload.reports?.body_snapshot_quality_gates_v1;
  const totals = payload.totals || {};
  if(!advancedModeEnabled){
    qualityLineEl.innerHTML = `Качество базы: ${qualityChip(payload.overall_status)} | проблемных проверок: <b>${e(totals.failed_gates_count||0)}</b>`;
    return;
  }
  qualityLineEl.innerHTML = `Качество базы: ${qualityChip(payload.overall_status)} | quality_gates_v1: ${qualityChip(q?.status)} | body_snapshot_quality_gates_v1: ${qualityChip(b?.status)} | проблемных проверок: <b>${e(totals.failed_gates_count||0)}</b> | регрессионных провалов: <b>${e(totals.failed_regression_checks_count||0)}</b>`;
}

function entityLabel(entity){
  const map = {
    doctor_conclusions: 'заключения врача',
    recommendations: 'рекомендации',
    labs: 'лабораторные показатели',
    medications: 'медикаменты',
    symptoms_events: 'симптомы/события',
  };
  return map[entity] || entity || 'сущность';
}

function extractEvidenceSnippets(rawText, hints, maxItems){
  const src = (rawText || '').toString().replace(/\\s+/g, ' ').trim();
  if(!src) return [];

  const MEDICAL_CUES = [
    'диагноз','заключение','рекомендац','жалоб','объектив','анамнез','исследован','анализ',
    'невролог','терапевт','мрт','рентген','консультац','лечение','синдром','остеохондроз',
    'грыжа','протруз','боль','теносиновит','вегетатив'
  ];
  const NOISE_CUES = [
    'акционерное общество','огрн','инн','адрес','г.москва','ул.','д.','стр.',
    'id пациента','пациент:','медицинская документация','утверждено приказом',
    'российской федерации','клиника к+31'
  ];

  function norm(s){
    return (s || '').toString().replace(/\\s+/g, ' ').trim();
  }
  function hasCue(text, cues){
    const low = text.toLowerCase();
    return cues.some(c => low.includes(c));
  }
  function isMostlyNoise(text){
    const low = text.toLowerCase();
    const noiseHits = NOISE_CUES.filter(c => low.includes(c)).length;
    const medHits = MEDICAL_CUES.filter(c => low.includes(c)).length;
    return noiseHits >= 2 && medHits === 0;
  }
  function getWindow(text, idx, spanLeft=90, spanRight=180){
    const from = Math.max(0, idx - spanLeft);
    const to = Math.min(text.length, idx + spanRight);
    let cut = text.slice(from, to);
    const leftPunct = Math.max(cut.lastIndexOf('. '), cut.lastIndexOf('; '), cut.lastIndexOf(': '), cut.lastIndexOf('! '), cut.lastIndexOf('? '));
    if(leftPunct >= 0 && leftPunct < Math.floor(cut.length * 0.6)) cut = cut.slice(leftPunct + 2);
    const rightCandidates = [cut.indexOf('. '), cut.indexOf('; '), cut.indexOf('! '), cut.indexOf('? ')].filter(x => x >= 40);
    if(rightCandidates.length){
      const right = Math.min(...rightCandidates);
      cut = cut.slice(0, right + 1);
    }
    cut = norm(cut);
    if(from > 0) cut = `... ${cut}`;
    if(to < text.length) cut = `${cut} ...`;
    return cut;
  }

  const out = [];
  const seen = new Set();
  const candidates = [];
  const lowerSrc = src.toLowerCase();

  const hintTokens = [];
  for(const h of (hints || [])){
    const t = norm(h).toLowerCase();
    if(!t) continue;
    const tokens = t.split(/[^a-zа-яё0-9]+/i)
      .map(x => x.trim())
      .filter(x => x.length >= 5 && !NOISE_CUES.some(n => x.includes(n)));
    hintTokens.push(...tokens.slice(0, 8));
  }

  for(const token of [...new Set(hintTokens)]){
    const idx = lowerSrc.indexOf(token);
    if(idx < 0) continue;
    const snippet = getWindow(src, idx, 80, 210);
    if(!snippet || snippet.length < 40) continue;
    const score = (hasCue(snippet, MEDICAL_CUES) ? 4 : 0) + (isMostlyNoise(snippet) ? -6 : 0);
    candidates.push({ snippet, score });
  }

  if(candidates.length < maxItems){
    const cueRegex = /(диагноз|заключение|рекомендац|жалоб|объектив|исследован|консультац)/gi;
    let m;
    while((m = cueRegex.exec(src)) !== null){
      const snippet = getWindow(src, m.index, 70, 220);
      if(!snippet || snippet.length < 40) continue;
      const score = 3 + (hasCue(snippet, MEDICAL_CUES) ? 2 : 0) + (isMostlyNoise(snippet) ? -6 : 0);
      candidates.push({ snippet, score });
      if(candidates.length > 24) break;
    }
  }

  candidates.sort((a,b) => b.score - a.score || b.snippet.length - a.snippet.length);
  for(const c of candidates){
    if(out.length >= maxItems) break;
    const key = norm(c.snippet.toLowerCase()).slice(0, 180);
    if(!key || seen.has(key)) continue;
    if(isMostlyNoise(c.snippet)) continue;
    seen.add(key);
    out.push(c.snippet.length > 260 ? `${c.snippet.slice(0, 260)}...` : c.snippet);
  }

  if(out.length < maxItems){
    const parts = src
      .split(/(?:\\.\\s+|;\\s+|\\|\\s+)/)
      .map(x => norm(x))
      .filter(x => x.length >= 45 && !isMostlyNoise(x));
    for(const p of parts){
      if(out.length >= maxItems) break;
      const key = p.toLowerCase().slice(0, 180);
      if(seen.has(key)) continue;
      const score = hasCue(p, MEDICAL_CUES) ? 2 : 0;
      if(score <= 0) continue;
      seen.add(key);
      out.push(p.length > 260 ? `${p.slice(0, 260)}...` : p);
    }
  }

  return out.slice(0, maxItems);
}

function assetHref(relPath, fallbackHref){
  if(relPath) return deleteApiUrl('/api/file?rel=' + encodeURIComponent(relPath));
  return fallbackHref || '';
}

async function probeDeleteApi(){
  try {
    const res = await fetch(deleteApiUrl('/api/health'), { method:'GET' });
    if(!res.ok) throw new Error(`HTTP ${res.status}`);
    deleteApiReady = true;
    setNotice('API чтения и удаления доступны.', false);
  } catch(err) {
    deleteApiReady = false;
    setNotice(`API чтения доступен, удаление недоступно: ${err.message}`, true);
  }
}

async function loadRows(){
  const res = await fetch(readApiUrl('/v1/review/documents?limit=5000'));
  if(!res.ok) throw new Error(`Ошибка API документов: HTTP ${res.status}`);
  const payload = await res.json();
  rows = payload.items || [];
  buildTypeOptions();
  return payload;
}

async function loadQualitySummary(){
  const res = await fetch(readApiUrl('/v1/quality/latest'));
  if(!res.ok) throw new Error(`Ошибка API качества: HTTP ${res.status}`);
  latestQualityPayload = await res.json();
  renderQualityLine();
}

async function loadAllLabFacts(){
  const all = [];
  let offset = 0;
  const limit = 1000;
  while(true){
    const url = readApiUrl(`/v1/facts/lab_results?limit=${limit}&offset=${offset}`);
    const res = await fetch(url);
    if(!res.ok) throw new Error(`Ошибка API анализов: HTTP ${res.status}`);
    const payload = await res.json();
    const items = payload.items || [];
    all.push(...items);
    offset += items.length;
    if(offset >= Number(payload.total || 0) || items.length === 0) break;
  }
  return all;
}

function buildLabSummaryRows(labFacts){
  const groups = new Map();
  const yearsSet = new Set();
  for(const row of (labFacts || [])){
    const rawName = (row.analyte_name || '').toString().trim();
    if(!rawName) continue;
    const dateRaw = (row.event_date || '').toString().trim();
    const year = /^\\d{4}-\\d{2}-\\d{2}$/.test(dateRaw) ? dateRaw.slice(0, 4) : '';
    if(year) yearsSet.add(year);
    const key = rawName.toLowerCase();
    if(!groups.has(key)){
      groups.set(key, { analyte_name: rawName, rows: [] });
    }
    groups.get(key).rows.push(row);
  }
  const years = [...yearsSet].sort((a,b)=>a.localeCompare(b));
  const out = [];
  for(const g of groups.values()){
    const points = g.rows
      .map(x => ({
        date: (x.event_date || '').toString().trim(),
        value_num: Number.isFinite(Number(x.value_num)) ? Number(x.value_num) : null,
        value_text: (x.value_text || '').toString(),
        abnormal: !!x.abnormal_flag,
        doc_id: (x.doc_id || '').toString(),
        reference: (x.reference_range_text || '').toString(),
      }))
      .filter(x => x.date)
      .sort((a,b) => a.date.localeCompare(b.date));
    if(!points.length) continue;
    const byYear = {};
    for(const p of points){
      const y = /^\\d{4}-\\d{2}-\\d{2}$/.test(p.date) ? p.date.slice(0,4) : '';
      if(!y) continue;
      const prev = byYear[y];
      if(!prev || p.date > prev.date){
        byYear[y] = p;
      }
    }
    const abnormalCount = points.filter(x => x.abnormal).length;
    const latestPoint = points[points.length - 1];
    const latestReference = (latestPoint?.reference || '').toString().trim();
    const latestDocId = (latestPoint?.doc_id || '').toString().trim();
    out.push({
      analyte_name: g.analyte_name,
      abnormal_count: abnormalCount,
      by_year: byYear,
      latest_reference: latestReference,
      latest_doc_id: latestDocId,
    });
  }
  out.sort((a,b) => {
    const abnormalCmp = Number(b.abnormal_count || 0) - Number(a.abnormal_count || 0);
    if(abnormalCmp !== 0) return abnormalCmp;
    return (a.analyte_name || '').localeCompare((b.analyte_name || ''), 'ru');
  });
  return { rows: out, years: years };
}

function isUninformativeLabValue(v){
  const s = (v || '').toString().trim().toLowerCase();
  if(!s) return true;
  const normalized = s.replace(/\\s+/g, ' ');
  return normalized.includes('не обнаруж') || normalized.includes('отсутств') || normalized === '—' || normalized === '-';
}

function cleanReferenceText(ref){
  let s = (ref || '').toString().trim();
  if(!s) return '';
  s = s.replace(/\\s+/g, ' ');
  // Common OCR splits/joins in references.
  s = s.replace(/\\bо\\s*трицател[а-яё]*/gi, 'отрицательно');
  s = s.replace(/\\bотрицател[а-яё]*/gi, 'отрицательно');
  s = s.replace(/\\bн\\s*орма\\b/gi, 'норма');
  s = s.replace(/\\b(отрицательно|положительно|не обнаружено|не выявлено|норма)\\s*(мкмоль\\/л|ммоль\\/л|мг\\/дл|мг\\/л|г\\/л|нг\\/мл|пг\\/мл|ед\\/л|мме\\/мл|мме\\/л|%)\\b/gi, '$1 $2');
  s = s.replace(/^(<=?\\s*\\d+[.,]?\\d*\\s*-\\s*)норма\\s*(мкмоль\\/л|ммоль\\/л|мг\\/дл|мг\\/л|г\\/л|нг\\/мл|пг\\/мл|ед\\/л|мме\\/мл|мме\\/л|%)$/i, '$1норма');
  s = s.replace(/(\\d)([A-Za-zА-Яа-яЁёµμ%])/g, '$1 $2');
  s = s.replace(/([А-Яа-яЁё])([A-Za-zА-Яа-яЁёµμ]+\\/[A-Za-zА-Яа-яЁё]+)/g, '$1 $2');
  s = s.replace(/\\s+/g, ' ').trim();
  return s;
}

function usefulnessScore(row, years){
  const sortedYears = [...(years || [])].sort((a,b)=>a.localeCompare(b));
  const recentYears = sortedYears.slice(-3);
  const points = Object.values(row.by_year || {});
  const recentPresent = recentYears.filter(y => !!(row.by_year || {})[y]).length;
  const informativeCount = points.filter(p => !isUninformativeLabValue((p || {}).value_text || '')).length;
  const hasOnlyUninformative = points.length > 0 && informativeCount === 0;
  let score = 0;
  score += recentPresent * 30;
  score += informativeCount * 6;
  score += Number(row.abnormal_count || 0) * 3;
  if(recentPresent === 0) score -= 220;
  if(hasOnlyUninformative) score -= 140;
  return score;
}

function detectLabGroup(name){
  const n = (name || '').toLowerCase();
  if(!n) return 'Прочее';
  if(
    n.includes('ттг') || n.includes('тестостерон') || n.includes('пролактин') || n.includes('фсг') ||
    n.includes('лютеиниз') || n.includes('дгэа') || n.includes('андроген') || n.includes('гормон')
  ) return 'Гормоны';
  if(
    n.includes('днк ') || n.includes('пцр') || n.includes('papilloma') || n.includes('candida') ||
    n.includes('mycoplasma') || n.includes('ureaplasma') || n.includes('chlamydia') || n.includes('gonorrhoeae') ||
    n.includes('treponema') || n.includes('trichomonas') || n.includes('gardnerella') || n.includes('cmv') ||
    n.includes('герпес')
  ) return 'ПЦР / инфекции';
  if(
    n.includes('лейкоц') || n.includes('эритроц') || n.includes('гемоглоб') || n.includes('тромбоц') ||
    n.includes('нейтроф') || n.includes('лимфоц') || n.includes('моноц') || n.includes('эозиноф') ||
    n.includes('базоф') || n.includes('соэ') || n.includes('wbc') || n.includes('rbc') || n.includes('plt') ||
    n.includes('mcv') || n.includes('mch') || n.includes('mchc') || n.includes('rdw')
  ) return 'Общий анализ крови';
  if(
    n.includes('мочев') || n.includes('креатинин') || n.includes('холестерин') || n.includes('лпнп') ||
    n.includes('лпвп') || n.includes('триглицерид') || n.includes('глюкоз') || n.includes('билирубин')
  ) return 'Биохимия';
  if(
    n.includes('удельная плотность') || n.includes('белок') || n.includes('кетон') || n.includes('нитрит') ||
    n.includes('прозрачн') || n.includes('цвет мочи')
  ) return 'Анализ мочи';
  return 'Прочее';
}

function rowIsNonDetectedOrMissing(row){
  const points = Object.values(row.by_year || {});
  if(!points.length) return true;
  return points.every(p => isUninformativeLabValue((p || {}).value_text || ''));
}

function renderLabSummaryTableMarkup(items){
  const yearCount = Math.max((labSummaryYears || []).length, 1);
  const yearWidth = (36 / yearCount).toFixed(3);
  const yearHeaders = (labSummaryYears || []).map(y => `<th>${e(y)}</th>`).join('');
  const yearCols = (labSummaryYears || []).map(() => `<col style="width:${yearWidth}%">`).join('');
  const rowsHtml = items.map(x => {
    const yearCells = (labSummaryYears || []).map(y => {
      const point = (x.by_year || {})[y];
      if(!point) return '<td>—</td>';
      const cls = point.abnormal ? 'lab-value-alert' : 'lab-value-ok';
      return `<td><span class="${cls}">${e(point.value_text || '—')}</span></td>`;
    }).join('');
    return `
      <tr>
        <td>${e(x.analyte_name)}</td>
        ${yearCells}
        <td>${e(cleanReferenceText(x.latest_reference || '') || '—')}</td>
        <td>${x.latest_doc_id ? `<button class="link-btn" onclick="openDoc('${e(x.latest_doc_id)}')">к документу</button>` : '—'}</td>
      </tr>
    `;
  }).join('');
  return `
    <table class="lab-table">
      <colgroup>
        <col style="width:32%">
        ${yearCols}
        <col style="width:22%">
        <col style="width:10%">
      </colgroup>
      <thead>
        <tr>
          <th>Показатель</th>
          ${yearHeaders}
          <th>Референс</th>
          <th>Документ</th>
        </tr>
      </thead>
      <tbody>${rowsHtml}</tbody>
    </table>
  `;
}

function renderLabSummaryTable(items){
  if(!labSummaryPanelEl) return;
  if(!items.length){
    labSummaryPanelEl.innerHTML = '<div class="muted">Нет показателей под текущие фильтры.</div>';
    return;
  }

  const nonDetected = [];
  const grouped = new Map();
  for(const row of items){
    if(rowIsNonDetectedOrMissing(row)){
      nonDetected.push(row);
      continue;
    }
    const g = detectLabGroup(row.analyte_name);
    if(!grouped.has(g)) grouped.set(g, []);
    grouped.get(g).push(row);
  }

  const order = ['Гормоны','Общий анализ крови','Биохимия','Анализ мочи','ПЦР / инфекции','Прочее'];
  const parts = [];
  for(const g of order){
    const rows = grouped.get(g) || [];
    if(!rows.length) continue;
    parts.push(`
      <details class="sec" open>
        <summary><b>${e(g)}</b> (${rows.length})</summary>
        <div style="margin-top:8px">${renderLabSummaryTableMarkup(rows)}</div>
      </details>
    `);
  }
  parts.push(`
    <details class="sec">
      <summary><b>Не обнаружено / без информативной динамики</b> (${nonDetected.length})</summary>
      <div style="margin-top:8px">${nonDetected.length ? renderLabSummaryTableMarkup(nonDetected) : '<div class="muted">Нет строк в этой группе.</div>'}</div>
    </details>
  `);
  labSummaryPanelEl.innerHTML = parts.join('');
}

function renderLabSummary(){
  if(!labSummaryPanelEl || !labSummaryStatsEl) return;
  const query = (labSummarySearchEl?.value || '').toLowerCase().trim();
  const flag = (labSummaryFlagFilterEl?.value || '').trim();
  const filtered = labSummaryRows.filter(x => {
    if(query && !(x.analyte_name || '').toLowerCase().includes(query)) return false;
    if(flag === 'abnormal' && Number(x.abnormal_count || 0) <= 0) return false;
    if(flag === 'normal' && Number(x.abnormal_count || 0) > 0) return false;
    return true;
  });
  filtered.sort((a,b) => {
    const aAbn = Number(a.abnormal_count || 0) > 0 ? 1 : 0;
    const bAbn = Number(b.abnormal_count || 0) > 0 ? 1 : 0;
    if(bAbn !== aAbn) return bAbn - aAbn;
    const sa = usefulnessScore(a, labSummaryYears);
    const sb = usefulnessScore(b, labSummaryYears);
    if(sb !== sa) return sb - sa;
    const aAbnCount = Number(a.abnormal_count || 0);
    const bAbnCount = Number(b.abnormal_count || 0);
    if(bAbnCount !== aAbnCount) return bAbnCount - aAbnCount;
    return (a.analyte_name || '').localeCompare((b.analyte_name || ''), 'ru');
  });
  const abnormalSeries = filtered.filter(x => Number(x.abnormal_count || 0) > 0).length;
  labSummaryStatsEl.innerHTML = `Показателей: <b>${filtered.length}</b> из <b>${labSummaryRows.length}</b> | с отклонениями: <b>${abnormalSeries}</b>`;
  renderLabSummaryTable(filtered);
}

async function loadLabSummary(){
  if(!labSummaryPanelEl) return;
  labSummaryPanelEl.innerHTML = 'Загрузка...';
  const labFacts = await loadAllLabFacts();
  const built = buildLabSummaryRows(labFacts);
  labSummaryRows = built.rows || [];
  labSummaryYears = built.years || [];
  renderLabSummary();
}

async function loadAnalyticsSnapshot(){
  const res = await fetch(readApiUrl('/v1/analytics/body-graph?include_needs_review=false&min_link_confidence=0.62&link_priorities=high,medium&include_document_nodes=true&include_orphans=false'));
  if(!res.ok) throw new Error(`Ошибка API графа: HTTP ${res.status}`);
  const payload = await res.json();
  const counts = payload.counts || {};
  const graph = payload.graph || { nodes: [], edges: [] };
  analyticsGraphCache = graph;
  const clusterNodes = (graph.nodes || []).filter(n => n.node_type === 'condition_cluster').sort((a,b) => Number(b.mention_count||0) - Number(a.mention_count||0));
  const topClusters = clusterNodes.slice(0,5);
  analyticsSnapshotEl.innerHTML = `
    <div class="card-grid">
      <div class="card"><div class="k">узлов</div><div class="num">${e(counts.nodes_total||0)}</div></div>
      <div class="card"><div class="k">связей</div><div class="num">${e(counts.edges_total||0)}</div></div>
      <div class="card"><div class="k">кластеров</div><div class="num">${e(counts.used_condition_clusters_count||0)}</div></div>
      <div class="card"><div class="k">исследований</div><div class="num">${e(counts.used_investigations_count||0)}</div></div>
    </div>
    <div class="sec">
      <div class="k">Крупнейшие кластеры состояний</div>
      <div class="v">${topClusters.length ? topClusters.map(c=>`${e(c.label||c.cluster_id)} (${e(c.mention_count||0)})`).join('<br/>') : 'нет'}</div>
    </div>
  `;
  if(analyticsClusterSelectEl){
    analyticsClusterSelectEl.innerHTML = '<option value="">Выберите кластер состояния...</option>' + clusterNodes.map(c=>`<option value="${e(c.cluster_id || '')}">${e(c.label || c.cluster_id || '')} (${e(c.mention_count || 0)})</option>`).join('');
    if(clusterNodes.length){
      analyticsClusterSelectEl.value = clusterNodes[0].cluster_id || '';
      renderAnalyticsDrilldown(analyticsClusterSelectEl.value);
    } else if(analyticsDrilldownEl){
      analyticsDrilldownEl.innerHTML = 'Кластеры не найдены';
    }
  }
}

function briefingLine(items, mapFn){
  if(!items || !items.length) return 'нет';
  return items.map(mapFn).join('<br/>');
}

function renderLabAttentionTable(items){
  const rows = (items || []).slice(0, 12);
  if(!rows.length){
    return '<div class="muted">Значимых отклонений в лабораториях не выявлено.</div>';
  }
  return `
    <table class="lab-table">
      <thead>
        <tr>
          <th>Показатель</th>
          <th>Эпизодов</th>
          <th>Последнее</th>
          <th>Референс</th>
          <th>Интерпретация</th>
        </tr>
      </thead>
      <tbody>
        ${rows.map(x=>{
          const latest = (x.latest_value || '').toString();
          const interpretation = latest.includes('↑')
            ? 'выше референса'
            : (latest.includes('↓') ? 'ниже референса' : 'без явной метки');
          return `
            <tr>
              <td>${e(x.theme || '')}</td>
              <td>${e(x.episodes || 0)}</td>
              <td>${e(latest || '—')}</td>
              <td>${e(x.latest_reference || '—')}</td>
              <td>${e(interpretation)}</td>
            </tr>
          `;
        }).join('')}
      </tbody>
    </table>
  `;
}

function renderBriefingRows(items, renderFn, emptyText){
  if(!items || !items.length) return `<div class="muted">${e(emptyText || 'нет данных')}</div>`;
  return items.map(renderFn).join('');
}

function truncateText(v, maxLen){
  const src = (v || '').toString().replace(/\\s+/g, ' ').trim();
  const lim = Number(maxLen) > 0 ? Number(maxLen) : 220;
  if(!src) return '';
  if(src.length <= lim) return src;
  return `${src.slice(0, lim).trim()}...`;
}

function priorityVisual(priority){
  const p = (priority || '').toString().toLowerCase();
  if(p === 'high') return { cls:'prio-high', label:'высокий' };
  if(p === 'medium') return { cls:'prio-medium', label:'средний' };
  return { cls:'prio-low', label:'низкий' };
}

function cleanBoilerplateText(text){
  let s = (text || '').toString().replace(/\\s+/g, ' ').trim();
  if(!s) return '';
  s = s
    .replace(/^Последнее подтверждение:[^.]*\\.?\\s*/i, '')
    .replace(/Состояние актуально для текущего визита\\.?/gi, '')
    .replace(/^Уточнить текущую активность состояния\\s+«[^»]+»\\s+и критерии контроля динамики\\.?/i, '')
    .replace(/^Проверить долгосрочный план наблюдения по состоянию\\s+«[^»]+»\\.?/i, '')
    .replace(/^Обсудить, нужен ли контроль показателя\\s+«[^»]+»\\s+и в какие сроки его пересдать\\.?/i, '')
    .replace(/\\s{2,}/g, ' ')
    .trim();
  return s;
}

function conciseActiveText(item){
  const limits = Array.isArray(item?.functional_limits) ? item.functional_limits : [];
  if(limits.length){
    return truncateText(cleanBoilerplateText(limits[0]) || limits[0], 170);
  }
  const prompt = cleanBoilerplateText(item?.discussion_prompt || '');
  if(prompt) return truncateText(prompt, 170);
  return 'Сверить текущие симптомы, допустимую нагрузку и понятный план контроля.';
}

async function loadPatientBriefing(){
  if(!briefingPanelEl) return;
  const briefingRes = await fetch(readApiUrl('/v1/reports/patient-briefing/v1'));
  if(!briefingRes.ok) throw new Error(`Ошибка API сводки: HTTP ${briefingRes.status}`);
  const payload = await briefingRes.json();
  const quality = payload.quality || {};
  const labs = payload.lab_attention_items || [];
  const findings = payload.clinical_findings || {};
  const currentState = payload.current_state || {};
  const active = currentState.active_conditions || [];
  const longTerm = currentState.long_term_conditions || [];
  const monitor = currentState.monitoring_items || [];
  const limits = currentState.functional_limits || [];
  const history = currentState.history_items || [];
  const uncertainItems = currentState.uncertain_items || [];
  const priorities = findings.prioritized_findings || [];
  const diagnosisPriorities = priorities.filter(x => {
    const k = (x?.kind || '').toString();
    return k === 'condition_active' || k === 'condition_monitor';
  });
  const qualityNote = findings.quality_note || '';
  const highCount = priorities.filter(x => (x.priority||'') === 'high').length;
  const mediumCount = priorities.filter(x => (x.priority||'') === 'medium').length;
  const lowCount = priorities.filter(x => (x.priority||'') === 'low').length;
  const prioritiesCount = priorities.length;

  briefingPanelEl.innerHTML = `
    <div class="briefing-grid">
      <div class="briefing-section">
        <h3>Что важно сейчас</h3>
        <div class="briefing-sub">Ключевые состояния, на которые стоит ориентироваться в ближайшее время.</div>
        <div class="briefing-list">
          ${renderBriefingRows(
            active.slice(0,6),
            x=>`<div class="briefing-item">
              <div class="head"><div class="title">${e(x.title||'')}</div></div>
              <div class="meta">фокус текущего наблюдения</div>
              <div class="txt">${e(conciseActiveText(x))}</div>
            </div>`,
            'Нет активных состояний в текущем окне данных.'
          )}
        </div>
      </div>

      <div class="briefing-section">
        <h3>Ключевые диагнозы и состояния</h3>
        <div class="briefing-sub">Короткий список ориентиров по текущей базе, без рекомендаций.</div>
        <div class="briefing-list">
          ${renderBriefingRows(
            diagnosisPriorities.slice(0,10),
            x=>{
              const pv = priorityVisual(x.priority);
              return `<div class="briefing-item">
                <div class="head">
                  <div class="title">${e(x.title||'')}</div>
                  <span class="prio-chip ${pv.cls}">${e(pv.label)}</span>
                </div>
              </div>`;
            },
            'Ключевые диагнозы в приоритетах не выделены.'
          )}
        </div>
      </div>
    </div>

    <div class="briefing-grid">
      <div class="briefing-section">
        <h3>Устойчивые состояния</h3>
        <div class="briefing-sub">Долгосрочный фон, который полезно держать в памяти.</div>
        <div class="briefing-list">
          ${renderBriefingRows(
            longTerm.slice(0,10),
            x=>`<div class="briefing-item">
              <div class="title">${e(x.title||'')}</div>
              <div class="meta">долгосрочный клинический фон</div>
            </div>`,
            'Устойчивые состояния пока не выделены.'
          )}
        </div>
      </div>

      <div class="briefing-section">
        <h3>Что мониторить</h3>
        <div class="briefing-sub">Плановый контроль без автоматического признака срочности.</div>
        <div class="briefing-list">
          ${renderBriefingRows(
            monitor.slice(0,10),
            x=>{
              const kind = (x.kind||'');
              if(kind === 'lab_monitor'){
                const docBtn = x.latest_doc_id ? ` <button class="link-btn" onclick="openDoc('${e(x.latest_doc_id)}')">к документу</button>` : '';
                return `<div class="briefing-item">
                  <div class="head"><div class="title">${e(x.title||'')}</div></div>
                  <div class="meta">лабораторный контроль${docBtn}</div>
                  <div class="txt">значение: ${e(x.latest_value||'н/д')} | референс: ${e(x.latest_reference||'н/д')}</div>
                </div>`;
              }
              return `<div class="briefing-item">
                <div class="title">${e(x.title||'')}</div>
                <div class="meta">плановое наблюдение</div>
                <div class="txt">${e(truncateText(cleanBoilerplateText(x.monitoring_reason||'') || x.monitoring_reason || '', 140))}</div>
              </div>`;
            },
            'На текущем срезе отдельные пункты мониторинга не выделены.'
          )}
        </div>
      </div>
    </div>

    <div class="briefing-section" style="margin-top:10px">
      <h3>Лабораторные сигналы</h3>
      <div class="briefing-sub">Ключевые отклонения и последние значения.</div>
      <div style="margin-top:8px">${renderLabAttentionTable(labs)}</div>
    </div>

    <div class="briefing-section" style="margin-top:10px">
      <h3>Ограничения и осторожность</h3>
      <div class="briefing-sub">Практические ограничения нагрузки и режима.</div>
      ${limits.length
        ? `<ul class="briefing-bullets">${limits.slice(0,10).map(x=>`<li>${e(x)}</li>`).join('')}</ul>`
        : `<div class="muted" style="margin-top:8px">Специальных ограничений не выделено.</div>`
      }
    </div>

    <details class="sec">
      <summary><b>История значимых эпизодов</b> (${e(history.length)})</summary>
      <div style="margin-top:8px" class="briefing-list">
        ${renderBriefingRows(
          history.slice(0,14),
          x=>`<div class="briefing-item"><div class="title">${e(x.title||'')}</div><div class="meta">период: ${e(x.first_seen||'н/д')} -> ${e(x.last_seen||'н/д')}</div></div>`,
          'Исторические эпизоды не выделены.'
        )}
      </div>
    </details>
    <details class="sec">
      <summary><b>Требуют уточнения</b> (${e(uncertainItems.length)})</summary>
      <div style="margin-top:8px" class="briefing-list">
        ${renderBriefingRows(
          uncertainItems.slice(0,10),
          x=>`<div class="briefing-item"><div class="title">${e(x.title||'')}</div><div class="meta">статус: требует уточнения</div><div class="txt">${e(truncateText(x.why_in_state||'', 180))}</div></div>`,
          'Неопределенных формулировок нет.'
        )}
      </div>
    </details>
    ${qualityNote ? `<div class="sec"><div class="k">Комментарий по качеству данных</div><div class="v">${e(qualityNote)}</div></div>` : ''}
    <div class="sec"><div class="k">Сводное качество</div><div class="v">${qualityChip(quality.overall_status||'unknown')} | высокий приоритет: ${e(highCount)} | средний: ${e(mediumCount)} | низкий: ${e(lowCount)} | всего приоритетов: ${e(prioritiesCount)}</div></div>
  `;
}

async function rebuildPatientBriefing(){
  if(!briefingBuildBtn) return;
  briefingBuildBtn.disabled = true;
  try {
    const [briefingRes, problemRes] = await Promise.all([
      fetch(readApiUrl('/v1/reports/patient-briefing/v1/build'), { method:'POST' }),
      fetch(readApiUrl('/v1/facts/problem-list/v1/build'), { method:'POST' }),
    ]);
    const briefingPayload = await briefingRes.json().catch(()=>({}));
    const problemPayload = await problemRes.json().catch(()=>({}));
    if(!briefingRes.ok) throw new Error(briefingPayload.detail || briefingPayload.error || `HTTP ${briefingRes.status}`);
    if(!problemRes.ok) throw new Error(problemPayload.detail || problemPayload.error || `HTTP ${problemRes.status}`);
    setNotice('Сводка и список состояний успешно пересчитаны.', false);
    await loadPatientBriefing();
  } catch(err){
    setNotice(`Не удалось пересчитать сводку: ${err.message}`, true);
  } finally {
    briefingBuildBtn.disabled = false;
  }
}

function renderAnalyticsDrilldown(clusterId){
  if(!analyticsDrilldownEl) return;
  const cid = (clusterId || '').toString().trim();
  if(!cid){ analyticsDrilldownEl.innerHTML = 'Выберите кластер'; return; }
  const nodes = analyticsGraphCache?.nodes || [];
  const edges = analyticsGraphCache?.edges || [];
  const clusterNodeId = `condition_cluster:${cid}`;
  const cluster = nodes.find(n => n.id === clusterNodeId);
  if(!cluster){ analyticsDrilldownEl.innerHTML = 'Кластер не найден в графе'; return; }

  const invNodeById = Object.fromEntries(nodes.filter(n => n.node_type === 'investigation').map(n => [n.id, n]));
  const docNodeById = Object.fromEntries(nodes.filter(n => n.node_type === 'document').map(n => [n.id, n]));
  const clusterToInv = edges.filter(x => x.edge_type === 'condition_cluster_to_investigation' && x.source === clusterNodeId);
  const clusterToDocs = edges.filter(x => x.edge_type === 'condition_cluster_in_document' && x.source === clusterNodeId);

  const investigations = [...new Map(clusterToInv.map(x => [x.target, invNodeById[x.target]]).filter(([,n]) => !!n)).values()];
  const documents = [...new Map(clusterToDocs.map(x => [x.target, docNodeById[x.target]]).filter(([,n]) => !!n)).values()];

  analyticsDrilldownEl.innerHTML = `
    <div class="analytics-row"><b>${e(cluster.label || cid)}</b></div>
    <div class="analytics-row">cluster_id: ${e(cid)} | упоминаний: ${e(cluster.mention_count||0)} | документов: ${e(cluster.doc_count||0)} | МКБ: ${e((cluster.icd_codes||[]).join(', ') || 'нет')}</div>
    <div class="analytics-row">Связанных исследований: <b>${e(investigations.length)}</b></div>
    <div class="analytics-row">${investigations.length ? investigations.slice(0,5).map(i=>`${e(i.label || i.event_id)} (${e(i.event_date||'')})`).join('<br/>') : 'нет'}</div>
    <div class="analytics-row">Связанных документов: <b>${e(documents.length)}</b></div>
    <div class="analytics-row">${documents.length ? documents.slice(0,7).map(d=>`${e(d.label || d.doc_id)} ${d.doc_id ? `<button class="link-btn" onclick="openDoc('${e(d.doc_id)}')">к документу</button>` : ''}`).join('<br/>') : 'нет'}</div>
  `;
}

async function loadFactQueue(){
  const state = (factStateFilterEl?.value || 'open').toLowerCase();
  const collection = (factCollectionFilterEl?.value || '').trim();
  const limit = (factLimitFilterEl?.value || '12').trim();
  const includeResolved = state !== 'open';
  const includeMedications = collection === 'medication_items';
  const qs = new URLSearchParams({
    limit: limit,
    include_ok: 'false',
    include_resolved: includeResolved ? 'true' : 'false',
    include_medications: includeMedications ? 'true' : 'false',
    review_state: state,
  });
  if(collection) qs.set('collections', collection);
  const res = await fetch(readApiUrl('/v1/review/fact-queue?' + qs.toString()));
  if(!res.ok) throw new Error(`Ошибка API очереди фактов: HTTP ${res.status}`);
  const payload = await res.json();
  const items = payload.items || [];
  const counts = payload.counts_by_collection || {};
  const states = payload.counts_by_review_state || {};
  factQueueEl.innerHTML = `
    <div class="k">Элементов в очереди: <b>${e(payload.total||0)}</b></div>
    <div class="k">По статусам: ${e(Object.entries(states).map(([k,v])=>`${k}:${v}`).join(' | ') || 'нет')}</div>
    <div class="k">По коллекциям: ${e(Object.entries(counts).map(([k,v])=>`${k}:${v}`).join(' | ') || 'нет')}</div>
    ${items.map(it => `
      <div class="queue-item">
        <div class="meta">
          ${e(it.fact_collection)} | score=${e(it.priority_score)} | conf=${e(it.confidence)} | state=${e(it.review_state||'open')} | doc=${e(it.doc_id||'')}
          ${it.doc_id ? `<button class="link-btn" onclick="openDoc('${it.doc_id}')">к документу</button>` : ''}
          ${it.review_state==='open'
            ? `<button class="link-btn" onclick="applyFactDecision('${e(it.queue_id)}','resolved')">подтвердить</button>
               <button class="link-btn" onclick="applyFactDecision('${e(it.queue_id)}','skipped')">пропустить</button>`
            : `<button class="link-btn" onclick="applyFactDecision('${e(it.queue_id)}','reopened')">вернуть</button>`
          }
        </div>
        <div class="txt">${line(it.preview||'')}</div>
        <div class="k">Причины: ${e((it.reasons||[]).join(', ') || 'нет')}</div>
      </div>
    `).join('')}
  `;
}

async function applyFactDecision(queueId, action){
  try {
    const res = await fetch(readApiUrl('/v1/review/fact-queue/decision'), {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ queue_id: queueId, action: action, actor: 'ui' })
    });
    const payload = await res.json().catch(()=>({}));
    if(!res.ok) throw new Error(payload.detail || payload.error || `HTTP ${res.status}`);
    setNotice(`Решение сохранено: ${queueId} -> ${action}`, false);
    await loadFactQueue();
  } catch(err){
    setNotice(`Не удалось сохранить решение: ${err.message}`, true);
  }
}

async function loadAndRenderDetail(docId){
  const res = await fetch(readApiUrl('/v1/review/documents/' + encodeURIComponent(docId)));
  if(!res.ok) throw new Error(`Ошибка API деталей: HTTP ${res.status}`);
  const r = await res.json();
  const dc=(r.doctor_conclusions||[]), rec=(r.recommendations||[]), labs=(r.labs||[]), labItems=(r.lab_items_preview||[]);
  const rf=(r.review_flags||{});
  const fe=r.full_extraction||null;
  const prettyFileName = prettifyFileName(r.file_name || '');
  const showOriginalName = prettyFileName && prettyFileName !== (r.file_name || '');
  const typeHuman = docTypeLabel(r.doc_type || '');
  const conclusionLabel=(r.doc_type||'').startsWith('imaging_report_') ? 'Заключения по исследованию' : 'Заключения врача';
  const pdfLink=assetHref(r.source_rel, r.pdf_link?.href||'');
  const feLink=assetHref(r.full_extraction_rel||'', r.full_extraction_link?.href||'');
  const expectedEntities = Array.isArray(r.expected_entities) ? r.expected_entities : [];
  const expectedHuman = expectedEntities.map(entityLabel);
  const expectedCoverage = expectedEntities.map(name => {
    let found = false;
    if(name === 'doctor_conclusions') found = dc.length > 0;
    else if(name === 'recommendations') found = rec.length > 0;
    else if(name === 'labs') found = (labItems.length > 0) || (labs.length > 0);
    else found = false;
    return { name, found };
  });
  const foundExpected = expectedCoverage.filter(x => x.found).map(x => entityLabel(x.name));
  const missingExpected = expectedCoverage.filter(x => !x.found).map(x => entityLabel(x.name));
  const coverageByEntity = expectedCoverage.length
    ? expectedCoverage.map(x => `${entityLabel(x.name)}: ${x.found ? 'да' : 'нет'}`).join('\\n')
    : 'нет ожидаемых сущностей для этого типа';
  const reviewReasons = Array.isArray(rf.reasons) ? rf.reasons : [];
  const statusWhy = [];
  if(!r.has_full_extraction) statusWhy.push('нет full_extraction');
  if(missingExpected.length) statusWhy.push(`не заполнены ожидаемые сущности: ${missingExpected.join(', ')}`);
  if(reviewReasons.length) statusWhy.push(`есть причины needs_review: ${reviewReasons.join(', ')}`);
  if(!statusWhy.length) statusWhy.push('критичных пробелов по требованиям не обнаружено');
  const evidenceHints = [
    ...(dc || []).map(x => x?.conclusion_text || ''),
    ...(dc || []).map(x => x?.findings_text || ''),
    ...(rec || []).map(x => x?.recommendation_text || ''),
    ...(labItems || []).map(x => `${x?.parameter || ''} ${x?.result || ''}`),
  ].filter(Boolean);
  const evidenceSnippets = extractEvidenceSnippets(fe?.raw_text_excerpt || '', evidenceHints, 3);
  const labText=labItems.length ? labItems.map(it=>`${it.section}: ${it.parameter||''} = ${it.result||''}${it.reference?` (референс: ${it.reference})`:''}`).join('\\n') : '';
  const foundParts = [];
  if(dc.length) foundParts.push(`<div class="sec"><div class="k">${conclusionLabel} (${dc.length})</div><div class="v">${line(dc.map(x=>[x.conclusion_text, x.findings_text?('описание: '+x.findings_text):''].filter(Boolean).join('\\n\\n')).join('\\n\\n----\\n\\n'))}</div></div>`);
  if(labItems.length) foundParts.push(`<div class="sec"><div class="k">Лабораторные показатели (${r.lab_item_count||0})</div><div class="v">${line(labText)}</div></div>`);
  if(rec.length) foundParts.push(`<div class="sec"><div class="k">Рекомендации (${rec.length})</div><div class="v">${line(rec.map(x=>x.recommendation_text).join('\\n\\n'))}</div></div>`);
  if(!foundParts.length) foundParts.push('<div class="sec"><div class="k">Что найдено</div><div class="v">Явных клинически полезных блоков не выделено.</div></div>');

  detail.innerHTML=`
    <h2 style="margin:0 0 6px">${e(prettyFileName || r.file_name || '')}</h2>
    ${showOriginalName ? `<div class="muted">${e(r.file_name || '')}</div>` : ''}
    <div class="muted">${e(r.doc_id)}</div>
    <div style="margin:10px 0;display:flex;gap:8px;flex-wrap:wrap">
      ${pdfLink?`<a class="btn" href="${pdfLink}" target="_blank">Открыть PDF</a>`:''}
      ${feLink?`<a class="btn" href="${feLink}" target="_blank">Открыть full_extraction JSON</a>`:''}
      <button class="btn-danger" onclick="deleteDoc('${r.doc_id}')" ${deleteApiReady?'':'disabled title="API удаления недоступен"'}>Удалить документ</button>
    </div>

    <div class="sec"><div class="k">Главное</div><div class="v">Тип: ${e(typeHuman)} (${e(r.doc_type||'')})\nДата: ${e(r.event_date_raw||'')}\nСтатус качества: ${e(qualityLabel(r.quality_status||''))}\nНужна ручная проверка: ${e(r.review_required ? 'да' : 'нет')}</div></div>
    <div class="sec"><div class="k">Почему такой статус</div><div class="v">Ожидалось сущностей: ${e(expectedEntities.length)}\nНайдено ожидаемых: ${e(foundExpected.length)}${foundExpected.length ? ` (${e(foundExpected.join(', '))})` : ''}\nПропущено ожидаемых: ${e(missingExpected.length)}${missingExpected.length ? ` (${e(missingExpected.join(', '))})` : ''}\nfull_extraction: ${e(r.has_full_extraction ? 'да' : 'нет')}\nexpected_facts: ${e(r.has_expected_facts ? 'да' : 'нет')}\nПричины статуса: ${e(statusWhy.join(' | '))}</div></div>
    <div class="sec"><div class="k">Покрытие по ожидаемым сущностям</div><div class="v">${line(coverageByEntity)}</div></div>
    ${foundParts.join('')}
    <div class="sec"><div class="k">Доказательства из текста документа</div><div class="v">${evidenceSnippets.length ? line(evidenceSnippets.map((x,i)=>`${i+1}. ${x}`).join('\\n')) : 'Фрагменты не найдены автоматически. Проверьте PDF вручную.'}</div></div>
    <div class="sec"><div class="k">Источник</div><div class="v">Путь: ${e(r.source_rel||'')}\nОжидаемые сущности: ${e(expectedHuman.join(', ')||'нет')}</div></div>

    <div class="sec">
      <details>
        <summary>Технические детали извлечения</summary>
        <div class="v">Покрытие: full_extraction=${r.has_full_extraction} | expected_facts=${r.has_expected_facts}</div>
        <div class="v">Причины review: ${e((rf.reasons||[]).join(', ')||'нет')}</div>
        <div class="v">Тип визита: ${e(fe?.summary?.visit_type||'')}</div>
        <div class="v">Итоговая рекомендация: ${e(fe?.summary?.recommendation||'нет')}</div>
        <div class="v">Распознано lab_items: ${e(r.lab_item_count||0)}</div>
        <div class="v" style="margin-top:8px">${line(fe?.raw_text_excerpt||'')}</div>
      </details>
    </div>
  `;
}

async function deleteDoc(docId){
  if(!deleteApiReady){ setNotice('Удаление недоступно: API не отвечает.', true); return; }
  const r=rows.find(x=>x.doc_id===docId);
  if(!r) return;
  const ask=confirm(`Удалить документ ${r.file_name} (${docId}) и все связанные файлы?`);
  if(!ask) return;
  try {
    const res=await fetch(deleteApiUrl('/api/delete'), {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({doc_id: docId})
    });
    const payload = await res.json().catch(()=>({}));
    if(!res.ok) throw new Error(payload.error||payload.detail||`HTTP ${res.status}`);
    const rebuild = payload.rebuild || {};
    const rebuildMsg = rebuild.ok===false ? ' Пересчет после удаления завершился ошибкой, см. логи API.' : '';
    setNotice(`Документ ${docId} удален. Удалено файлов: ${(payload.deleted_paths||[]).length}.${rebuildMsg}`, rebuild.ok===false);
    await reloadAll();
  } catch(err) {
    setNotice(`Ошибка удаления ${docId}: ${err.message}`, true);
  }
}

function compareRowsByDateDesc(a,b){
  const ad = toIsoDateKey(a.event_date_raw);
  const bd = toIsoDateKey(b.event_date_raw);
  const cmp = bd.localeCompare(ad, 'ru');
  if(cmp !== 0) return cmp;
  return parseNum(a.idx)-parseNum(b.idx);
}

function filt(){
  const qv=q.value.toLowerCase().trim(), tv=tF.value;
  const onlyProblems = !!problemOnlyToggleEl?.checked;
  let list=rows.filter(r=> {
    const hay=[r.file_name,r.doc_id,r.source_rel,r.doc_type,r.search_blob||''].join(' ').toLowerCase();
    const problemOk = !onlyProblems || isProblematicRow(r);
    return (!qv || hay.includes(qv)) && (!tv || r.doc_type===tv) && problemOk;
  });
  list.sort(compareRowsByDateDesc);
  render(list);
}

function render(list){
  const problemsTotal = rows.filter(isProblematicRow).length;
  const familyCounts = rows.reduce((acc, r) => {
    const k = docFamily(r.doc_type);
    acc[k] = (acc[k] || 0) + 1;
    return acc;
  }, {});
  stats.innerHTML=`Показано: <b>${list.length}</b> из <b>${rows.length}</b> | проблемных: <b>${problemsTotal}</b> | анализы: <b>${familyCounts.labs||0}</b>, консультации: <b>${familyCounts.consult||0}</b>, снимки: <b>${familyCounts.imaging||0}</b>`;
  tbody.innerHTML=list.map(r=>{
    const pretty = prettifyFileName(r.file_name||'');
    const raw = (r.file_name||'').toString();
    const hint = `${raw}\\n${(r.doc_id||'').toString()}`;
    const family = docFamily(r.doc_type);
    return `<tr data-id="${r.doc_id}">
    <td>${r.idx}</td>
    <td title="${e(hint)}">${e(pretty)}</td>
    <td><span class="type-chip type-${family}">${e(docTypeLabel(r.doc_type))}</span></td>
    <td>${e(r.event_date_raw||'')}</td>
    <td><span class="badge ${r.quality_status}">${e(qualityLabel(r.quality_status))}</span></td>
    <td><button class="btn-danger-sm" data-del="${r.doc_id}" ${deleteApiReady?'':'disabled title="API удаления недоступен"'}>Удалить</button></td>
  </tr>`;
  }).join('');

  [...tbody.querySelectorAll('tr')].forEach(tr=>tr.onclick=()=>show(tr.dataset.id));
  [...tbody.querySelectorAll('button[data-del]')].forEach(btn=>btn.onclick=(ev)=>{ ev.stopPropagation(); deleteDoc(btn.dataset.del); });

  const keepId = selectedDocId && list.some(x=>x.doc_id===selectedDocId) ? selectedDocId : (list[0]?.doc_id || '');
  if(keepId){
    show(keepId);
  } else {
    selectedDocId = '';
    detail.innerHTML='Нет документов по текущим фильтрам';
  }
}

async function show(id){
  selectedDocId = id;
  detail.innerHTML = 'Загрузка...';
  try {
    await loadAndRenderDetail(id);
  } catch(err) {
    detail.innerHTML = `<div class="k">Не удалось загрузить детали</div><div class="v">${e(err.message)}</div>`;
  }
}

async function reloadAll(){
  try {
    await loadRows();
    await loadQualitySummary();
    await loadPatientBriefing();
    await loadLabSummary();
    if(advancedModeEnabled){
      await loadFactQueue();
      await loadAnalyticsSnapshot();
    }
    await probeDeleteApi();
    filt();
  } catch(err) {
    setNotice(`API чтения недоступен: ${err.message}`, true);
    rows = [];
    buildTypeOptions();
    filt();
  }
}

[q,tF].forEach(x=>x.addEventListener('input',filt));
[tF].forEach(x=>x.addEventListener('change',filt));
if(problemOnlyToggleEl) problemOnlyToggleEl.addEventListener('change',filt);
if(factCollectionFilterEl) factCollectionFilterEl.addEventListener('change', ()=>loadFactQueue());
if(factStateFilterEl) factStateFilterEl.addEventListener('change', ()=>loadFactQueue());
if(factLimitFilterEl) factLimitFilterEl.addEventListener('change', ()=>loadFactQueue());
if(factQueueRefreshBtn) factQueueRefreshBtn.addEventListener('click', ()=>loadFactQueue());
if(briefingRefreshBtn) briefingRefreshBtn.addEventListener('click', ()=>loadPatientBriefing());
if(briefingBuildBtn) briefingBuildBtn.addEventListener('click', ()=>rebuildPatientBriefing());
if(labSummarySearchEl) labSummarySearchEl.addEventListener('input', ()=>renderLabSummary());
if(labSummaryFlagFilterEl) labSummaryFlagFilterEl.addEventListener('change', ()=>renderLabSummary());
if(labSummaryRefreshBtn) labSummaryRefreshBtn.addEventListener('click', ()=>loadLabSummary());
if(analyticsClusterSelectEl) analyticsClusterSelectEl.addEventListener('change', ()=>renderAnalyticsDrilldown(analyticsClusterSelectEl.value));
if(advancedModeToggleEl) advancedModeToggleEl.addEventListener('change', ()=>setAdvancedMode(advancedModeToggleEl.checked));
document.querySelectorAll('.tab-btn').forEach(btn => btn.addEventListener('click', ()=>setActiveView(btn.dataset.view)));

setAdvancedMode(false);
reloadAll();
</script>
</body></html>"""

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html_out, encoding="utf-8")
    print(str(OUT).replace("\\", "/"))


if __name__ == "__main__":
    build()



