from datetime import datetime

import pytest

from dnd_combat_simulator.reporting import (
    ReportSection,
    _rows,
    _to_float,
    generate_csv_report,
    generate_pdf_report,
)


def test_rows_accepts_read_only_mappings_without_copying() -> None:
    row: dict[str, str] = {"Metric": "Damage", "Value": "12.5"}

    assert _rows([row]) == (row,)
    assert _rows([row])[0] is row


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, 0.0), ("", 0.0), ("  ", 0.0), (" 12.5 ", 12.5), (3, 3.0)],
)
def test_to_float_handles_supported_report_values(
    value: object, expected: float
) -> None:
    assert _to_float(value) == expected


def test_reports_preserve_csv_values_and_pdf_share_link() -> None:
    section = ReportSection(
        "Damage Per Round Chart Data",
        _rows([{"Round": 1, "Average damage": "12.5"}]),
    )
    generated_at = datetime(2026, 7, 27, 12, 0, 0)
    share_url = "https://example.com/share?id=abc"

    csv_report = generate_csv_report(
        [section],
        simulation_count=100,
        seed=42,
        share_url=share_url,
        generated_at=generated_at,
    ).decode("utf-8-sig")
    pdf_report = generate_pdf_report(
        [section],
        simulation_count=100,
        seed=42,
        share_url=share_url,
        generated_at=generated_at,
    )

    assert "Round,Average damage\n1,12.5" in csv_report
    assert pdf_report.startswith(b"%PDF-1.7")
    assert b"/Subtype /Link" in pdf_report
    assert b"/URI (https://example.com/share?id=abc)" in pdf_report
