"""Regression coverage for the simulation-row report control."""

from __future__ import annotations

import inspect

from dnd_combat_simulator.ui import page, results


def test_report_control_is_always_rendered_and_disabled_without_results(
    monkeypatch,
) -> None:
    calls = []

    monkeypatch.setattr(page, "_render_run_simulation_button", lambda disabled: False)
    monkeypatch.setattr(
        page,
        "_render_download_report_control",
        lambda **kwargs: calls.append(kwargs),
    )

    page._render_simulation_control_row(disabled=False, seed=17)

    assert len(calls) == 1
    assert calls[0]["disabled"] is True
    assert calls[0]["result"] is None


def test_report_control_enables_only_for_current_successful_result(monkeypatch) -> None:
    calls = []
    completed_result = object()
    monkeypatch.setattr(page, "_render_run_simulation_button", lambda disabled: False)
    monkeypatch.setattr(
        page,
        "_render_download_report_control",
        lambda **kwargs: calls.append(kwargs),
    )

    page._render_simulation_control_row(
        disabled=False, result=completed_result, seed=17
    )

    assert calls == [
        {
            "build": None,
            "result": completed_result,
            "comparison": None,
            "seed": 17,
            "disabled": False,
        }
    ]


def test_starting_run_disables_report_until_success(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(page, "_render_run_simulation_button", lambda disabled: True)
    monkeypatch.setattr(
        page,
        "_render_download_report_control",
        lambda **kwargs: calls.append(kwargs),
    )

    assert page._render_simulation_control_row(result=object(), disabled=False, seed=1)
    assert calls[0]["disabled"] is True


def test_configuration_change_and_failure_clear_downloadable_result() -> None:
    state = {
        page.COMPLETED_SIMULATION_REQUEST_KEY: "old request",
        page.COMPLETED_SIMULATION_RESULT_KEY: "old result",
        "completed-result-report": b"stale report",
    }

    assert page._current_completed_result(state, "new request") is None
    assert page.COMPLETED_SIMULATION_RESULT_KEY not in state
    assert "completed-result-report" not in state

    state[page.COMPLETED_SIMULATION_REQUEST_KEY] = "failed request"
    state[page.COMPLETED_SIMULATION_RESULT_KEY] = "old result"
    page._clear_completed_simulation(state)
    assert page._current_completed_result(state, "failed request") is None


def test_results_sections_do_not_duplicate_download_report_control() -> None:
    assert "_render_download_report_control" not in inspect.getsource(
        results._render_single_build_results
    )
    assert "_render_download_report_control" not in inspect.getsource(
        results._render_comparison_results
    )
