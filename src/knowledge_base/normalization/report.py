"""Report writer for normalization runs.

Produces a JSON report and a human-readable Markdown summary under
``data/processed/normalized/``.
"""

from __future__ import annotations

import json
from pathlib import Path

from knowledge_base.normalization.models import NormalizationReport


def _report_dir(base: Path) -> Path:
    base = Path(base)
    d = base / "processed" / "normalized"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_report(report: NormalizationReport, base_dir: Path) -> tuple[Path, Path]:
    """Write ``{source}.json`` and ``{source}.md``; returns both paths."""
    out_dir = _report_dir(base_dir)
    stem = f"{report.source_file_id}"

    json_path = out_dir / f"{stem}.json"
    json_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    md_path = out_dir / f"{stem}.md"
    md_path.write_text(_to_markdown(report), encoding="utf-8")
    return json_path, md_path


def _to_markdown(report: NormalizationReport) -> str:
    header = [
        "# Normalization Report",
        "",
        f"- Source file: `{report.source_file_id}`",
        f"- Generated: {report.created_at.isoformat()}",
        f"- Pages: {len(report.items)}",
        f"- Pages changed: {report.changed_items}",
        f"- Pages flagged protected (religious): {report.protected_items}",
        "",
    ]

    rows: list[str] = []
    for item in report.items:
        stats = item.result.stats
        flagged = (
            "PROTECTED"
            if stats.protected
            else ("UNCHANGED" if item.result.unchanged else "CHANGED")
        )
        rows.append(
            f"- **p{item.page_number}** [{flagged}] chars {stats.chars_before}->{stats.chars_after}"
        )

    return "\n".join(header + rows) + "\n"
