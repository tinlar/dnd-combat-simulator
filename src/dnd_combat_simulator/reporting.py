"""Deterministic exports of completed, in-memory simulation results."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from dnd_combat_simulator.simulation import (
    BuildComparisonResult,
    BuildConfig,
    SimulationResult,
)
from dnd_combat_simulator.ui.results import (
    _comparison_round_chart_data,
    _profile_breakdown_rows,
    _profile_combat_contribution_chart_data,
    _profile_contribution_chart_data,
    _resource_usage_rows,
    _result_rows,
    _round_breakdown_rows,
    _round_chart_data,
    _single_result_rows,
    _single_round_breakdown_rows,
)


@dataclass(frozen=True)
class ReportSection:
    """One named tabular section shared by CSV and PDF output."""

    title: str
    rows: tuple[dict[str, object], ...]


def _rows(rows: Iterable[dict[str, object]]) -> tuple[dict[str, object], ...]:
    return tuple(rows)


def build_report_sections(
    build: BuildConfig | None = None,
    result: SimulationResult | None = None,
    comparison: BuildComparisonResult | None = None,
) -> tuple[ReportSection, ...]:
    """Prepare the exact chart and detail-table data already used by the UI."""
    if comparison is not None:
        a, b = comparison.first_build, comparison.second_build
        ar, br = comparison.first_result, comparison.second_result
        return (
            ReportSection("Summary Metrics", _rows(_result_rows(comparison))),
            ReportSection(
                "Damage Per Round Chart Data",
                _rows(_comparison_round_chart_data(comparison)),
            ),
            ReportSection(
                f"{a.name} Attack Contribution to Damage Per Round Chart Data",
                _rows(_profile_contribution_chart_data(ar, a.name)),
            ),
            ReportSection(
                f"{b.name} Attack Contribution to Damage Per Round Chart Data",
                _rows(_profile_contribution_chart_data(br, b.name)),
            ),
            ReportSection(
                f"{a.name} Attack Contribution to Damage Per Combat Chart Data",
                _rows(_profile_combat_contribution_chart_data(ar, a.name)),
            ),
            ReportSection(
                f"{b.name} Attack Contribution to Damage Per Combat Chart Data",
                _rows(_profile_combat_contribution_chart_data(br, b.name)),
            ),
            ReportSection("Per-Round Damage", _rows(_round_breakdown_rows(comparison))),
            ReportSection(
                f"{a.name} Attack Breakdown", _rows(_profile_breakdown_rows(ar))
            ),
            ReportSection(f"{a.name} Resource Usage", _rows(_resource_usage_rows(ar))),
            ReportSection(
                f"{b.name} Attack Breakdown", _rows(_profile_breakdown_rows(br))
            ),
            ReportSection(f"{b.name} Resource Usage", _rows(_resource_usage_rows(br))),
        )
    if build is None or result is None:
        raise ValueError("A build and completed result are required")
    return (
        ReportSection("Summary Metrics", _rows(_single_result_rows(result))),
        ReportSection(
            "Damage Per Round Chart Data", _rows(_round_chart_data(result, build.name))
        ),
        ReportSection(
            "Attack Contribution to Damage Per Round Chart Data",
            _rows(_profile_contribution_chart_data(result, build.name)),
        ),
        ReportSection(
            "Attack Contribution to Damage Per Combat Chart Data",
            _rows(_profile_combat_contribution_chart_data(result, build.name)),
        ),
        ReportSection("Per-Round Damage", _rows(_single_round_breakdown_rows(result))),
        ReportSection("Attack Breakdown", _rows(_profile_breakdown_rows(result))),
        ReportSection("Resource Usage", _rows(_resource_usage_rows(result))),
    )


def _metadata(
    simulation_count: int, seed: int | None, share_url: str, generated_at: datetime
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = [
        {
            "Field": "Generated",
            "Value": generated_at.isoformat(sep=" ", timespec="seconds"),
        },
        {"Field": "Simulation count", "Value": simulation_count},
    ]
    if seed is not None:
        rows.append({"Field": "Simulation seed", "Value": seed})
    rows.append({"Field": "Share Configuration", "Value": share_url})
    return rows


def generate_csv_report(
    sections: Iterable[ReportSection],
    *,
    simulation_count: int,
    seed: int | None,
    share_url: str,
    generated_at: datetime,
) -> bytes:
    """Return one UTF-8 CSV containing clearly separated report sections."""
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    all_sections = (
        ReportSection(
            "Report Metadata",
            _rows(_metadata(simulation_count, seed, share_url, generated_at)),
        ),
        *sections,
    )
    for index, section in enumerate(all_sections):
        if index:
            writer.writerow([])
        writer.writerow([f"[{section.title}]"])
        if not section.rows:
            writer.writerow(["No data available"])
            continue
        columns = list(dict.fromkeys(key for row in section.rows for key in row))
        writer.writerow(columns)
        for row in section.rows:
            writer.writerow([row.get(column, "") for column in columns])
    return output.getvalue().encode("utf-8-sig")


def generate_pdf_report(
    sections: Iterable[ReportSection],
    *,
    simulation_count: int,
    seed: int | None,
    share_url: str,
    generated_at: datetime,
) -> bytes:
    """Return a dependency-free, paginated PDF with a clickable share URL.

    Tables are deliberately rendered from the same prepared rows as the CSV and UI.
    Chart sections additionally receive a compact bar visualization before their
    source table, without deriving or changing any result value.
    """

    def safe(value: object) -> str:
        return str(value).encode("latin-1", "replace").decode("latin-1")

    lines = [
        ("D&D COMBAT SIMULATOR REPORT", 18),
        (f"Generated: {generated_at.isoformat(sep=' ', timespec='seconds')}", 10),
        (f"Simulation count: {simulation_count}", 10),
    ]
    if seed is not None:
        lines.append((f"Simulation seed: {seed}", 10))
    lines.extend((("Share Configuration:", 10), (share_url, 9), ("", 8)))
    for section in sections:
        lines.extend(((section.title, 14), ("-" * min(100, len(section.title)), 8)))
        if not section.rows:
            lines.extend((("No data available.", 9), ("", 8)))
            continue
        columns = list(dict.fromkeys(key for row in section.rows for key in row))
        # A visual accompanies each chart while retaining the untouched source rows.
        if "Chart Data" in section.title:
            numeric = next(
                (
                    c
                    for c in reversed(columns)
                    if any(isinstance(r.get(c), (int, float)) for r in section.rows)
                ),
                None,
            )
            values = (
                [float(r.get(numeric, 0) or 0) for r in section.rows] if numeric else []
            )
            maximum = max(values, default=0)
            for row, value in zip(section.rows, values, strict=True):
                label = row.get("Round", row.get("Profile", row.get("Build", "")))
                bar = "#" * (int(28 * value / maximum) if maximum > 0 else 0)
                lines.append((f"{label!s:18.18} | {bar} {value:.2f}", 8))
        lines.append((" | ".join(columns), 7))
        for row in section.rows:
            text = " | ".join(safe(row.get(column, "")) for column in columns)
            while text:
                lines.append((text[:145], 7))
                text = text[145:]
        lines.append(("", 8))

    pages = [lines[index : index + 55] for index in range(0, len(lines), 55)] or [[]]
    objects: list[bytes] = []

    def add(data: str | bytes) -> int:
        objects.append(data.encode("latin-1") if isinstance(data, str) else data)
        return len(objects)

    catalog_id = add("")
    pages_id = add("")
    font_id = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids = []
    link_objects: list[tuple[int, int]] = []
    for page_lines in pages:
        commands = ["BT", "/F1 10 Tf", "36 570 Td"]
        share_y = None
        for text, size in page_lines:
            escaped = (
                safe(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            )
            commands.extend((f"/F1 {size} Tf", f"({escaped}) Tj", "0 -10 Td"))
            if text == share_url:
                share_y = 570 - (len(commands) // 3 - 1) * 10
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1")
        content_id = add(
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
        )
        annotation_id = None
        if share_y is not None:
            url = (
                safe(share_url)
                .replace("\\", "\\\\")
                .replace("(", "\\(")
                .replace(")", "\\)")
            )
            annotation_id = add(
                f"<< /Type /Annot /Subtype /Link /Rect [36 {share_y - 2} "
                f"750 {share_y + 9}] /Border [0 0 0] /A << /S /URI "
                f"/URI ({url}) >> >>"
            )
        page_id = add("")
        page_ids.append(page_id)
        link_objects.append((page_id, annotation_id or 0))
        annots = f" /Annots [{annotation_id} 0 R]" if annotation_id else ""
        objects[page_id - 1] = (
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 792 612] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
            f"/Contents {content_id} 0 R{annots} >>"
        )
        objects[page_id - 1] = objects[page_id - 1].encode()
    objects[pages_id - 1] = (
        f"<< /Type /Pages /Count {len(page_ids)} "
        f"/Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] >>"
    )
    objects[pages_id - 1] = objects[pages_id - 1].encode()
    objects[catalog_id - 1] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode()
    output = io.BytesIO()
    output.write(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(output.tell())
        output.write(f"{number} 0 obj\n".encode())
        output.write(obj)
        output.write(b"\nendobj\n")
    xref = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode())
    output.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode()
    )
    return output.getvalue()
