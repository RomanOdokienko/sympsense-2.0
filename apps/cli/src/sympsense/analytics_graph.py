from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_body_graph(
    project_root: Path,
    *,
    include_needs_review: bool,
    min_link_confidence: float,
    allowed_link_priorities: set[str],
    include_document_nodes: bool,
    include_orphans: bool,
) -> dict[str, Any]:
    root = project_root.resolve()
    snapshot_path = root / "data/canonical/facts/body_snapshot_v1.json"
    registry_path = root / "data/canonical/documents/batch_01_registry_active.json"

    if not snapshot_path.exists():
        raise FileNotFoundError("body_snapshot_v1.json not found")
    if not registry_path.exists():
        raise FileNotFoundError("batch_01_registry_active.json not found")

    snapshot = _load_json(snapshot_path)
    registry_rows: list[dict[str, Any]] = _load_json(registry_path)
    registry_by_doc = {str(x.get("id") or ""): x for x in registry_rows if str(x.get("id") or "")}

    conditions: list[dict[str, Any]] = list(snapshot.get("condition_mentions") or [])
    clusters: list[dict[str, Any]] = list(snapshot.get("condition_clusters") or [])
    investigations: list[dict[str, Any]] = list(snapshot.get("investigation_events") or [])
    links: list[dict[str, Any]] = list(snapshot.get("condition_investigation_links") or [])

    condition_by_id = {str(x.get("mention_id") or ""): x for x in conditions if str(x.get("mention_id") or "")}
    investigation_by_id = {
        str(x.get("event_id") or ""): x for x in investigations if str(x.get("event_id") or "")
    }
    cluster_by_id = {str(x.get("cluster_id") or ""): x for x in clusters if str(x.get("cluster_id") or "")}

    mention_to_cluster: dict[str, str] = {}
    for cluster in clusters:
        cluster_id = str(cluster.get("cluster_id") or "")
        for mention_id in cluster.get("mention_ids") or []:
            mention_to_cluster[str(mention_id)] = cluster_id

    def qa_ok(row: dict[str, Any]) -> bool:
        return str(row.get("qa_status") or "needs_review") == "ok"

    filtered_links: list[dict[str, Any]] = []
    for link in links:
        prio = str(link.get("link_priority") or "").lower()
        conf = float(link.get("confidence") or 0.0)
        if allowed_link_priorities and prio not in allowed_link_priorities:
            continue
        if conf < min_link_confidence:
            continue
        if not include_needs_review and not qa_ok(link):
            continue

        condition_id = str(link.get("condition_id") or "")
        investigation_id = str(link.get("investigation_id") or "")
        condition_row = condition_by_id.get(condition_id)
        investigation_row = investigation_by_id.get(investigation_id)
        if not condition_row or not investigation_row:
            continue
        if not include_needs_review and (not qa_ok(condition_row) or not qa_ok(investigation_row)):
            continue
        filtered_links.append(link)

    used_condition_ids = {str(x.get("condition_id") or "") for x in filtered_links}
    used_investigation_ids = {str(x.get("investigation_id") or "") for x in filtered_links}

    if include_orphans:
        for cond in conditions:
            cond_id = str(cond.get("mention_id") or "")
            if not cond_id:
                continue
            if not include_needs_review and not qa_ok(cond):
                continue
            used_condition_ids.add(cond_id)
        for inv in investigations:
            inv_id = str(inv.get("event_id") or "")
            if not inv_id:
                continue
            if not include_needs_review and not qa_ok(inv):
                continue
            used_investigation_ids.add(inv_id)

    used_cluster_ids = {mention_to_cluster.get(cid, "") for cid in used_condition_ids}
    used_cluster_ids = {x for x in used_cluster_ids if x}

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    # Cluster nodes (higher-level condition entities for graph analytics)
    for cluster_id in sorted(used_cluster_ids):
        cluster = cluster_by_id.get(cluster_id)
        if not cluster:
            continue
        if not include_needs_review and not qa_ok(cluster):
            continue
        label = (
            str((cluster.get("examples") or [""])[0] or "")
            or str(cluster.get("group_key") or cluster_id)
        )
        nodes.append(
            {
                "id": f"condition_cluster:{cluster_id}",
                "node_type": "condition_cluster",
                "label": label[:280],
                "cluster_id": cluster_id,
                "group_key": cluster.get("group_key"),
                "mention_count": cluster.get("mention_count"),
                "doc_count": cluster.get("doc_count"),
                "icd_codes": cluster.get("icd_codes") or [],
                "qa_status": cluster.get("qa_status"),
                "confidence": cluster.get("confidence"),
                "first_date": cluster.get("first_date"),
                "last_date": cluster.get("last_date"),
            }
        )

    # Investigation nodes
    for inv_id in sorted(used_investigation_ids):
        inv = investigation_by_id.get(inv_id)
        if not inv:
            continue
        if not include_needs_review and not qa_ok(inv):
            continue
        nodes.append(
            {
                "id": f"investigation:{inv_id}",
                "node_type": "investigation",
                "label": str(inv.get("title") or inv_id)[:280],
                "event_id": inv_id,
                "doc_id": inv.get("doc_id"),
                "doc_type": inv.get("doc_type"),
                "event_date": inv.get("event_date"),
                "qa_status": inv.get("qa_status"),
                "confidence": inv.get("confidence"),
                "highlights": inv.get("highlights") or [],
            }
        )

    # Main condition<->investigation edges based on ranked links
    for link in filtered_links:
        cond_id = str(link.get("condition_id") or "")
        inv_id = str(link.get("investigation_id") or "")
        cluster_id = mention_to_cluster.get(cond_id)
        if not cluster_id:
            continue
        if cluster_id not in used_cluster_ids or inv_id not in used_investigation_ids:
            continue
        edges.append(
            {
                "id": f"edge:{link.get('link_id')}",
                "edge_type": "condition_cluster_to_investigation",
                "source": f"condition_cluster:{cluster_id}",
                "target": f"investigation:{inv_id}",
                "relation_type": link.get("relation_type"),
                "confidence": link.get("confidence"),
                "link_priority": link.get("link_priority"),
                "qa_status": link.get("qa_status"),
                "days_apart": link.get("days_apart"),
                "score_reasons": link.get("score_reasons") or [],
            }
        )

    if include_document_nodes:
        used_doc_ids: set[str] = set()
        condition_mentions_by_cluster: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for cond_id in used_condition_ids:
            cluster_id = mention_to_cluster.get(cond_id)
            cond = condition_by_id.get(cond_id)
            if cluster_id and cond:
                condition_mentions_by_cluster[cluster_id].append(cond)

        for cluster_id, mentions in condition_mentions_by_cluster.items():
            for cond in mentions:
                doc_id = str(cond.get("doc_id") or "")
                if not doc_id or doc_id not in registry_by_doc:
                    continue
                used_doc_ids.add(doc_id)
                edges.append(
                    {
                        "id": f"edge:cluster_doc:{cluster_id}:{doc_id}:{cond.get('mention_id')}",
                        "edge_type": "condition_cluster_in_document",
                        "source": f"condition_cluster:{cluster_id}",
                        "target": f"document:{doc_id}",
                        "relation_type": "mentioned_in_document",
                        "confidence": cond.get("confidence"),
                        "qa_status": cond.get("qa_status"),
                        "event_date": cond.get("event_date"),
                    }
                )

        for inv_id in used_investigation_ids:
            inv = investigation_by_id.get(inv_id)
            if not inv:
                continue
            doc_id = str(inv.get("doc_id") or "")
            if not doc_id or doc_id not in registry_by_doc:
                continue
            used_doc_ids.add(doc_id)
            edges.append(
                {
                    "id": f"edge:inv_doc:{inv_id}:{doc_id}",
                    "edge_type": "investigation_in_document",
                    "source": f"investigation:{inv_id}",
                    "target": f"document:{doc_id}",
                    "relation_type": "from_document",
                    "confidence": inv.get("confidence"),
                    "qa_status": inv.get("qa_status"),
                    "event_date": inv.get("event_date"),
                }
            )

        for doc_id in sorted(used_doc_ids):
            row = registry_by_doc.get(doc_id) or {}
            nodes.append(
                {
                    "id": f"document:{doc_id}",
                    "node_type": "document",
                    "label": str(row.get("file_name") or doc_id)[:280],
                    "doc_id": doc_id,
                    "doc_type": row.get("doc_type"),
                    "event_date_raw": row.get("event_date_raw"),
                    "parse_mode": row.get("parse_mode"),
                    "text_len": row.get("text_len"),
                    "source_rel": (row.get("source") or {}).get("relative_path"),
                }
            )

    node_type_counts: dict[str, int] = defaultdict(int)
    for node in nodes:
        node_type_counts[str(node.get("node_type") or "unknown")] += 1

    edge_type_counts: dict[str, int] = defaultdict(int)
    for edge in edges:
        edge_type_counts[str(edge.get("edge_type") or "unknown")] += 1

    return {
        "generated_at": _now_utc(),
        "version": "analytics_body_graph_v1",
        "filters": {
            "include_needs_review": include_needs_review,
            "min_link_confidence": min_link_confidence,
            "allowed_link_priorities": sorted(allowed_link_priorities),
            "include_document_nodes": include_document_nodes,
            "include_orphans": include_orphans,
        },
        "counts": {
            "nodes_total": len(nodes),
            "edges_total": len(edges),
            "node_type_counts": dict(node_type_counts),
            "edge_type_counts": dict(edge_type_counts),
            "filtered_links_count": len(filtered_links),
            "used_condition_mentions_count": len(used_condition_ids),
            "used_investigations_count": len(used_investigation_ids),
            "used_condition_clusters_count": len(used_cluster_ids),
        },
        "graph": {
            "nodes": nodes,
            "edges": edges,
        },
    }

