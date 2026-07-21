import pytest

from dnd_combat_simulator import APP_TITLE
from dnd_combat_simulator.app import (
    SimulationInputs,
    format_damage,
    format_rate,
    run_simulation_from_inputs,
    validate_simulation_inputs,
)
from dnd_combat_simulator.combat import AttackRollMode


def test_app_title() -> None:
    assert APP_TITLE == "DnD Combat Simulator"


def test_format_damage_uses_two_decimal_places() -> None:
    assert format_damage(12) == "12.00"
    assert format_damage(12.345) == "12.35"


def test_format_rate_uses_percentage() -> None:
    assert format_rate(0.625) == "62.50%"


@pytest.mark.parametrize(
    ("inputs", "message"),
    [
        (
            SimulationInputs(5, 15, "", 5, 1, 10_000),
            "Damage Formula is required",
        ),
        (
            SimulationInputs(5, 0, "1d8", 5, 1, 10_000),
            "Target Armor Class must be at least 1",
        ),
        (
            SimulationInputs(5, 15, "1d8", 0, 1, 10_000),
            "Number of rounds must be at least 1",
        ),
        (
            SimulationInputs(5, 15, "1d8", 5, 0, 10_000),
            "Attacks per round must be at least 1",
        ),
        (
            SimulationInputs(5, 15, "1d8", 5, 1, 0),
            "Number of simulations must be at least 1",
        ),
    ],
)
def test_validate_simulation_inputs_rejects_unusable_values(
    inputs: SimulationInputs, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_simulation_inputs(inputs)


def test_run_simulation_from_inputs_reuses_shared_simulation_logic() -> None:
    result = run_simulation_from_inputs(
        SimulationInputs(
            attack_bonus=5,
            target_armor_class=15,
            damage_dice=" 1d8+3 ",
            rounds=1,
            attacks_per_round=2,
            simulations=1,
            attack_roll_mode=AttackRollMode.DISADVANTAGE,
        )
    )

    assert result.simulations_run == 1
    assert result.rounds_per_simulation == 1
    assert result.attacks_per_round == 2
    assert result.total_attacks_made == 2
    assert result.attack_roll_mode is AttackRollMode.DISADVANTAGE


def test_result_rows_show_side_by_side_comparison() -> None:
    from dnd_combat_simulator.app import (
        ComparisonInputs,
        _result_rows,
        run_comparison_from_inputs,
    )
    from dnd_combat_simulator.simulation import BuildConfig, ScenarioConfig

    comparison = run_comparison_from_inputs(
        ComparisonInputs(
            first_build=BuildConfig("Build A", 20, "1d4", 1),
            second_build=BuildConfig("Build B", 20, "1d4+1", 1),
            scenario=ScenarioConfig(target_armor_class=1, rounds=1, simulations=2),
            seed=7,
        )
    )

    rows = _result_rows(comparison)

    assert rows[0]["Metric"] == "Average damage per round"
    assert rows[0]["Build A"] == "1.50"
    assert rows[0]["Build B"] == "2.50"
    assert rows[0]["Difference"] == "-1.00"
    assert all(row["Metric"] != "Full Damage Success Rate" for row in rows)


@pytest.mark.parametrize(
    ("additional_count", "expected_headings", "expected_prefixes"),
    [
        (0, ["Primary Attack"], ["build-primary"]),
        (
            1,
            ["Primary Attack", "Additional Attack 1"],
            ["build-primary", "build-additional-1"],
        ),
        (
            2,
            ["Primary Attack", "Additional Attack 1", "Additional Attack 2"],
            ["build-primary", "build-additional-1", "build-additional-2"],
        ),
        (
            3,
            [
                "Primary Attack",
                "Additional Attack 1",
                "Additional Attack 2",
                "Additional Attack 3",
            ],
            [
                "build-primary",
                "build-additional-1",
                "build-additional-2",
                "build-additional-3",
            ],
        ),
    ],
)
def test_profile_definitions_support_dynamic_additional_attacks(
    additional_count: int, expected_headings: list[str], expected_prefixes: list[str]
) -> None:
    from dnd_combat_simulator.app import _profile_definitions

    definitions = _profile_definitions("build", additional_count)

    assert [definition[0] for definition in definitions] == expected_prefixes
    assert [definition[1] for definition in definitions] == expected_headings


def test_builds_can_use_different_numbers_of_attack_profiles() -> None:
    from dnd_combat_simulator.app import _build_config_from_profiles
    from dnd_combat_simulator.simulation import (
        AttackProfile,
        ScenarioConfig,
        compare_builds,
    )

    first_profiles = (
        AttackProfile("Primary A", 20, "1d4", 1),
        AttackProfile("Extra A 1", 20, "1d4", 1),
        AttackProfile("Extra A 2", 20, "1d4", 1),
    )
    second_profiles = (AttackProfile("Primary B", 20, "1d4", 1),)

    comparison = compare_builds(
        first_build=_build_config_from_profiles("Build A", first_profiles),
        second_build=_build_config_from_profiles("Build B", second_profiles),
        scenario=ScenarioConfig(target_armor_class=1, rounds=1, simulations=1),
        seed=4,
    )

    assert len(comparison.first_build.attack_profiles) == 3
    assert len(comparison.second_build.attack_profiles) == 1
    assert comparison.first_result.total_attacks_made == 3
    assert comparison.second_result.total_attacks_made == 1


def test_page_width_css_uses_centered_ninety_viewport_width() -> None:
    from dnd_combat_simulator.app import PAGE_WIDTH_CSS

    assert ".stApp .block-container" in PAGE_WIDTH_CSS
    assert "width: 90vw;" in PAGE_WIDTH_CSS
    assert "max-width: 90vw;" in PAGE_WIDTH_CSS
    assert "margin-left: auto;" in PAGE_WIDTH_CSS
    assert "margin-right: auto;" in PAGE_WIDTH_CSS
    assert "box-sizing: border-box;" in PAGE_WIDTH_CSS
    assert "padding-left: clamp(1rem, 2vw, 2.5rem);" in PAGE_WIDTH_CSS
    assert "padding-right: clamp(1rem, 2vw, 2.5rem);" in PAGE_WIDTH_CSS
    assert "@media (max-width: 640px)" in PAGE_WIDTH_CSS


def test_configure_page_uses_wide_layout_and_injects_width_css(monkeypatch) -> None:
    import sys
    from types import SimpleNamespace

    from dnd_combat_simulator.app import PAGE_WIDTH_CSS, configure_page

    calls: list[tuple[str, dict[str, object]]] = []

    def set_page_config(**kwargs: object) -> None:
        calls.append(("set_page_config", kwargs))

    def markdown(body: str, **kwargs: object) -> None:
        calls.append(("markdown", {"body": body, **kwargs}))

    fake_streamlit = SimpleNamespace(
        set_page_config=set_page_config,
        markdown=markdown,
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

    configure_page()

    assert calls == [
        (
            "set_page_config",
            {"page_title": APP_TITLE, "page_icon": "🎲", "layout": "wide"},
        ),
        (
            "markdown",
            {"body": PAGE_WIDTH_CSS, "unsafe_allow_html": True},
        ),
    ]


def test_single_build_rows_include_required_complete_results() -> None:
    from dnd_combat_simulator.app import (
        SingleBuildInputs,
        _profile_breakdown_rows,
        _single_result_rows,
        _single_round_breakdown_rows,
        run_single_build_from_inputs,
    )
    from dnd_combat_simulator.simulation import BuildConfig, ScenarioConfig

    result = run_single_build_from_inputs(
        SingleBuildInputs(
            build=BuildConfig("Custom", 20, "1d4", 1),
            scenario=ScenarioConfig(target_armor_class=1, rounds=2, simulations=2),
            seed=8,
        )
    )

    metric_names = {row["Metric"] for row in _single_result_rows(result)}
    assert "Average total damage per round" in metric_names
    assert "Average total damage across the combat" in metric_names
    assert "Average damage per target per round" in metric_names
    assert "Round 1 burst damage" in metric_names
    assert "Average damage after round 1" in metric_names
    assert "Highest-damage round" in metric_names
    assert "Minimum total damage" in metric_names
    assert "Maximum total damage" in metric_names
    assert "Total attack uses" in metric_names
    assert "Total target resolutions" in metric_names
    assert len(_single_round_breakdown_rows(result)) == 2
    assert _profile_breakdown_rows(result)[0]["Attack profile"] == "Attack"


def test_comparison_toggle_default_off_and_single_mode_uses_only_first_build(
    monkeypatch,
) -> None:
    import sys
    from types import SimpleNamespace

    from dnd_combat_simulator.app import main

    calls: list[tuple[str, object]] = []

    class Column:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def number_input(self, label, **kwargs):
            calls.append(("number_input", kwargs.get("key")))
            return kwargs.get("value", 1)

        def text_input(self, label, **kwargs):
            calls.append(("text_input", kwargs.get("key")))
            return kwargs.get("value", "")

        def selectbox(self, label, **kwargs):
            calls.append(("selectbox", kwargs.get("key")))
            return kwargs["options"][kwargs.get("index", 0)]

    col = Column()

    def columns(spec):
        count = spec if isinstance(spec, int) else len(spec)
        return [col for _ in range(count)]

    fake_streamlit = SimpleNamespace(
        set_page_config=lambda **kwargs: None,
        markdown=lambda *args, **kwargs: calls.append(("markdown", args[0])),
        title=lambda *args, **kwargs: None,
        write=lambda *args, **kwargs: None,
        subheader=lambda *args, **kwargs: None,
        columns=columns,
        number_input=col.number_input,
        text_input=col.text_input,
        selectbox=col.selectbox,
        toggle=lambda *args, **kwargs: (
            calls.append(("toggle", kwargs)) or kwargs["value"]
        ),
        button=lambda *args, **kwargs: False,
        error=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

    main()

    assert ("toggle", {"value": False, "key": "compare-builds-enabled"}) in calls
    keys = [
        value
        for kind, value in calls
        if kind in {"text_input", "number_input", "selectbox"}
    ]
    assert "first-build-name" in keys
    assert "first-primary-active-rounds" in keys
    assert "second-build-name" not in keys
    assert "second-primary-active-rounds" not in keys


def test_comparison_mode_still_renders_second_build_with_stable_keys(
    monkeypatch,
) -> None:
    import sys
    from types import SimpleNamespace

    from dnd_combat_simulator.app import main

    keys: list[str | None] = []

    class Column:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def number_input(self, label, **kwargs):
            keys.append(kwargs.get("key"))
            return kwargs.get("value", 1)

        def text_input(self, label, **kwargs):
            keys.append(kwargs.get("key"))
            return kwargs.get("value", "")

        def selectbox(self, label, **kwargs):
            keys.append(kwargs.get("key"))
            return kwargs["options"][kwargs.get("index", 0)]

    col = Column()
    fake_streamlit = SimpleNamespace(
        set_page_config=lambda **kwargs: None,
        markdown=lambda *args, **kwargs: None,
        title=lambda *args, **kwargs: None,
        write=lambda *args, **kwargs: None,
        subheader=lambda *args, **kwargs: None,
        columns=lambda spec: [
            col for _ in range(spec if isinstance(spec, int) else len(spec))
        ],
        number_input=col.number_input,
        text_input=col.text_input,
        selectbox=col.selectbox,
        toggle=lambda *args, **kwargs: True,
        button=lambda *args, **kwargs: False,
        error=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

    main()

    assert "first-build-name" in keys
    assert "second-build-name" in keys
    assert "first-primary-resolution-type" in keys
    assert "second-primary-resolution-type" in keys


def _mixed_profile_result():
    from dnd_combat_simulator.app import SingleBuildInputs, run_single_build_from_inputs
    from dnd_combat_simulator.combat import ResolutionType
    from dnd_combat_simulator.simulation import (
        AttackProfile,
        BuildConfig,
        ScenarioConfig,
    )

    build = BuildConfig(
        "Mixed",
        0,
        "1d4",
        0,
        1,
        attack_profiles=(
            AttackProfile("Zero opener", 0, "1d4", 1, active_rounds="1"),
            AttackProfile(
                "Save effect",
                None,
                "1d4",
                1,
                resolution_type=ResolutionType.SAVING_THROW,
                save_dc=10,
            ),
            AttackProfile(
                "Aura",
                None,
                "1d4",
                1,
                resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
            ),
        ),
    )
    return build, run_single_build_from_inputs(
        SingleBuildInputs(
            build=build,
            scenario=ScenarioConfig(target_armor_class=99, rounds=3, simulations=2),
            seed=12,
        )
    )


def test_single_build_round_chart_data_includes_zero_damage_rounds() -> None:
    from dnd_combat_simulator.app import _round_chart_data
    from dnd_combat_simulator.simulation import (
        BuildConfig,
        ScenarioConfig,
        simulate_build,
    )

    result = simulate_build(
        BuildConfig("Misses", 0, "1d4", 1),
        ScenarioConfig(target_armor_class=99, rounds=2, simulations=2),
        seed=1,
    )

    assert _round_chart_data(result, "Misses") == [
        {"Round": 1, "Average total damage": 0.0, "Build": "Misses"},
        {"Round": 2, "Average total damage": 0.0, "Build": "Misses"},
    ]


def test_comparison_round_chart_data_uses_both_builds() -> None:
    from dnd_combat_simulator.app import _comparison_round_chart_data
    from dnd_combat_simulator.simulation import (
        BuildConfig,
        ScenarioConfig,
        compare_builds,
    )

    comparison = compare_builds(
        first_build=BuildConfig("A", 20, "1d4", 1),
        second_build=BuildConfig("B", 20, "1d4+1", 1),
        scenario=ScenarioConfig(target_armor_class=1, rounds=2, simulations=1),
        seed=2,
    )

    rows = _comparison_round_chart_data(comparison)

    assert [row["Build"] for row in rows] == ["A", "A", "B", "B"]
    assert [row["Round"] for row in rows] == [1, 2, 1, 2]


def test_profile_chart_data_keeps_configured_order_and_automatic_profiles() -> None:
    from dnd_combat_simulator.app import _profile_chart_data

    build, result = _mixed_profile_result()

    rows = _profile_chart_data(result, build.name)

    assert [row["Profile"] for row in rows] == ["Zero opener", "Save effect", "Aura"]
    assert [row["Order"] for row in rows] == [1, 2, 3]
    assert rows[2]["Resolution type"] == "Automatic Damage"


def test_key_comparison_metric_chart_data() -> None:
    from dnd_combat_simulator.app import _comparison_metric_chart_data
    from dnd_combat_simulator.simulation import (
        BuildConfig,
        ScenarioConfig,
        compare_builds,
    )

    comparison = compare_builds(
        first_build=BuildConfig("A", 20, "1d4", 1),
        second_build=BuildConfig("B", 20, "1d4+1", 1),
        scenario=ScenarioConfig(target_armor_class=1, rounds=2, simulations=1),
        seed=2,
    )

    rows = _comparison_metric_chart_data(comparison)

    assert [row["Metric"] for row in rows[:3]] == [
        "Average damage per round",
        "Round 1 burst damage",
        "Average damage after round 1",
    ]
    assert [row["Build"] for row in rows] == ["A", "A", "A", "B", "B", "B"]


def test_single_build_and_comparison_chart_render_paths_are_separate(
    monkeypatch,
) -> None:
    import dnd_combat_simulator.app as app
    from dnd_combat_simulator.simulation import (
        BuildConfig,
        ScenarioConfig,
        compare_builds,
        simulate_build,
    )

    calls: list[str] = []
    monkeypatch.setattr(
        app, "_render_single_build_charts", lambda *args: calls.append("single")
    )
    monkeypatch.setattr(
        app, "_render_comparison_charts", lambda *args: calls.append("comparison")
    )

    class DummyExpander:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class DummyColumn:
        def metric(self, *args, **kwargs):
            pass

    class DummyContainer(DummyExpander):
        pass

    fake_st = type(
        "FakeSt",
        (),
        {
            "subheader": lambda *args, **kwargs: None,
            "columns": lambda *args, **kwargs: [
                DummyColumn()
                for _ in range(args[0] if isinstance(args[0], int) else len(args[0]))
            ],
            "metric": lambda *args, **kwargs: None,
            "expander": lambda *args, **kwargs: DummyExpander(),
            "table": lambda *args, **kwargs: None,
            "markdown": lambda *args, **kwargs: None,
            "caption": lambda *args, **kwargs: None,
            "success": lambda *args, **kwargs: None,
            "write": lambda *args, **kwargs: None,
            "container": lambda *args, **kwargs: DummyContainer(),
        },
    )
    monkeypatch.setitem(__import__("sys").modules, "streamlit", fake_st)

    build = BuildConfig("A", 20, "1d4", 1)
    result = simulate_build(build, ScenarioConfig(1, 1, 1), 1)
    app._render_single_build_results(build, result)
    comparison = compare_builds(
        first_build=build,
        second_build=BuildConfig("B", 20, "1d4", 1),
        scenario=ScenarioConfig(1, 1, 1),
        seed=1,
    )
    app._render_comparison_results(comparison)

    assert calls == ["single", "comparison"]
