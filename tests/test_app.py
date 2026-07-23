import sys

import pytest

from dnd_combat_simulator import APP_TITLE
from dnd_combat_simulator.combat import AttackRollMode
from dnd_combat_simulator.ui.results import format_damage, format_rate
from dnd_combat_simulator.ui.run_control import (
    SimulationInputs,
    run_simulation_from_inputs,
    validate_simulation_inputs,
)


def test_app_title() -> None:
    assert APP_TITLE == "DnD Combat Simulator"


def test_format_damage_uses_two_decimal_places() -> None:
    assert format_damage(12) == "12.00"
    assert format_damage(12.345) == "12.35"


def test_format_rate_uses_percentage() -> None:
    assert format_rate(0.625) == "62.50%"


def test_damage_formula_help_uses_markdown_lists() -> None:
    from dnd_combat_simulator.ui.constants import DAMAGE_FORMULA_HELP

    assert "•" not in DAMAGE_FORMULA_HELP
    examples = [
        "1d8",
        "2d6+4",
        "1d10-1",
        "2d8r<2",
        "2d8r8",
        "2d8r1r3r5r7",
        "3d6!",
        "3d6!>4",
        "3d6!3",
        "4d6kh3",
        "4d6kl3",
        "8d100dl3",
        "8d100dh3",
        "4d6r1!kh3+2",
        "1d6+1d4+4d4+3",
        "4d6kh3+2d8!+1d4-2",
    ]
    lines = DAMAGE_FORMULA_HELP.splitlines()

    for example in examples:
        matches = [line for line in lines if f"`{example}`" in line]
        assert len(matches) == 1
        assert matches[0].startswith(f"- `{example}`")


def test_damage_formula_input_keeps_streamlit_help_icon(monkeypatch) -> None:
    import sys
    from types import SimpleNamespace

    from dnd_combat_simulator.ui.constants import DAMAGE_FORMULA_HELP
    from dnd_combat_simulator.ui.inputs import _attack_profile_inputs

    text_input_calls: list[dict[str, object]] = []

    class Column:
        def number_input(self, label, **kwargs):
            return kwargs.get("value", 1)

        def text_input(self, label, **kwargs):
            text_input_calls.append({"label": label, **kwargs})
            return kwargs.get("value", "")

        def selectbox(self, label, **kwargs):
            return kwargs["options"][kwargs.get("index", 0)]

    col = Column()
    fake_streamlit = SimpleNamespace(
        selectbox=col.selectbox,
        text_input=col.text_input,
        columns=lambda spec, **kwargs: [
            col for _ in range(spec if isinstance(spec, int) else len(spec))
        ],
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

    _attack_profile_inputs("test", "Attack")

    damage_call = next(
        call for call in text_input_calls if call["label"] == "Damage Formula"
    )
    assert damage_call["help"] == DAMAGE_FORMULA_HELP


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
    from dnd_combat_simulator.simulation import BuildConfig, ScenarioConfig
    from dnd_combat_simulator.ui.results import _result_rows
    from dnd_combat_simulator.ui.run_control import (
        ComparisonInputs,
        run_comparison_from_inputs,
    )

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
    assert rows[0]["Difference (Build B − Build A)"] == "1.00"
    assert all(row["Metric"] != "Full Damage Success Rate" for row in rows)


@pytest.mark.parametrize(
    ("additional_count", "expected_headings", "expected_prefixes"),
    [
        (0, ["Attack 1"], ["build-primary"]),
        (
            1,
            ["Attack 1", "Attack 2"],
            ["build-primary", "build-additional-1"],
        ),
        (
            2,
            ["Attack 1", "Attack 2", "Attack 3"],
            ["build-primary", "build-additional-1", "build-additional-2"],
        ),
        (
            3,
            [
                "Attack 1",
                "Attack 2",
                "Attack 3",
                "Attack 4",
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
    from dnd_combat_simulator.ui.inputs import _profile_definitions

    definitions = _profile_definitions("build", additional_count)

    assert [definition[0] for definition in definitions] == expected_prefixes
    assert [definition[1] for definition in definitions] == expected_headings


def test_builds_can_use_different_numbers_of_attack_profiles() -> None:
    from dnd_combat_simulator.simulation import (
        AttackProfile,
        ScenarioConfig,
        compare_builds,
    )
    from dnd_combat_simulator.ui.inputs import _build_config_from_profiles

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
    from dnd_combat_simulator.ui.components import PAGE_WIDTH_CSS

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

    from dnd_combat_simulator.ui.components import (
        ATTACK_TOOLBAR_CSS,
        PAGE_WIDTH_CSS,
        configure_page,
    )

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
        (
            "markdown",
            {"body": ATTACK_TOOLBAR_CSS, "unsafe_allow_html": True},
        ),
    ]


def test_single_build_rows_include_required_complete_results() -> None:
    from dnd_combat_simulator.simulation import BuildConfig, ScenarioConfig
    from dnd_combat_simulator.ui.results import (
        _profile_breakdown_rows,
        _single_result_rows,
        _single_round_breakdown_rows,
    )
    from dnd_combat_simulator.ui.run_control import (
        SingleBuildInputs,
        run_single_build_from_inputs,
    )

    result = run_single_build_from_inputs(
        SingleBuildInputs(
            build=BuildConfig("Custom", 20, "1d4", 1),
            scenario=ScenarioConfig(target_armor_class=1, rounds=2, simulations=2),
            seed=8,
        )
    )

    metric_names = {row["Metric"] for row in _single_result_rows(result)}
    assert "Average total damage per combat" in metric_names
    assert "Average damage per round" in metric_names
    assert "Expected damage per target resolution" in metric_names
    assert "Average attack executions per combat" in metric_names
    assert "Average attack executions per round" in metric_names
    assert "Average damaging target resolutions per combat" in metric_names
    assert "Average damaging target resolutions per round" in metric_names
    assert "Round 1 burst damage" in metric_names
    assert "Average damage after round 1" in metric_names
    assert "Highest-damage round" in metric_names
    assert "Minimum total damage" not in metric_names
    assert "Maximum total damage" not in metric_names
    assert "Total attack uses" not in metric_names
    assert "Target instances damaged" not in metric_names
    assert len(_single_round_breakdown_rows(result)) == 2
    profile_row = _profile_breakdown_rows(result)[0]
    assert profile_row["Attack profile"] == "Attack"
    assert "Average executions per combat" in profile_row
    assert "Average executions per round" in profile_row
    assert "Configured uses" not in profile_row
    assert "Triggered executions" not in profile_row
    assert "Total actual executions" not in profile_row


def test_comparison_toggle_default_off_and_single_mode_uses_only_first_build(
    monkeypatch,
) -> None:
    import sys
    from types import SimpleNamespace

    from dnd_combat_simulator.ui.page import main

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

    def columns(spec, **kwargs):
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

    from dnd_combat_simulator.ui.page import main

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
        columns=lambda spec, **kwargs: [
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
    from dnd_combat_simulator.combat import ResolutionType
    from dnd_combat_simulator.simulation import (
        AttackProfile,
        BuildConfig,
        ScenarioConfig,
    )
    from dnd_combat_simulator.ui.run_control import (
        SingleBuildInputs,
        run_single_build_from_inputs,
    )

    build = BuildConfig(
        "Mixed",
        0,
        "1d4",
        0,
        1,
        attack_profiles=(
            AttackProfile(
                "Zero opener", 0, "1d4", 1, active_rounds="1", attack_id="zero-opener"
            ),
            AttackProfile(
                "Save effect",
                None,
                "1d4",
                1,
                resolution_type=ResolutionType.SAVING_THROW,
                save_dc=10,
                attack_id="save-effect",
            ),
            AttackProfile(
                "Aura",
                None,
                "1d4",
                1,
                resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
                attack_id="aura",
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
    from dnd_combat_simulator.simulation import (
        BuildConfig,
        ScenarioConfig,
        simulate_build,
    )
    from dnd_combat_simulator.ui.results import _round_chart_data

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
    from dnd_combat_simulator.simulation import (
        BuildConfig,
        ScenarioConfig,
        compare_builds,
    )
    from dnd_combat_simulator.ui.results import _comparison_round_chart_data

    comparison = compare_builds(
        first_build=BuildConfig("A", 20, "1d4", 1),
        second_build=BuildConfig("B", 20, "1d4+1", 1),
        scenario=ScenarioConfig(target_armor_class=1, rounds=2, simulations=1),
        seed=2,
    )

    rows = _comparison_round_chart_data(comparison)

    assert [row["Build"] for row in rows] == ["A", "A", "B", "B"]
    assert [row["Round"] for row in rows] == [1, 2, 1, 2]


def test_profile_contribution_data_keeps_order_and_automatic_profiles() -> None:
    from dnd_combat_simulator.ui.results import _profile_contribution_chart_data

    build, result = _mixed_profile_result()

    rows = _profile_contribution_chart_data(result, build.name)

    assert [row["Profile"] for row in rows] == ["Zero opener", "Save effect", "Aura"]
    assert [row["Order"] for row in rows] == [1, 2, 3]
    assert rows[2]["Resolution type"] == "Automatic Damage"


def test_single_build_and_comparison_chart_render_paths_are_separate(
    monkeypatch,
) -> None:
    import dnd_combat_simulator.ui.results as results
    from dnd_combat_simulator.simulation import (
        BuildConfig,
        ScenarioConfig,
        compare_builds,
        simulate_build,
    )

    calls: list[str] = []
    monkeypatch.setattr(
        results, "_render_single_build_charts", lambda *args: calls.append("single")
    )
    monkeypatch.setattr(
        results, "_render_comparison_charts", lambda *args: calls.append("comparison")
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
    results._render_single_build_results(build, result)
    comparison = compare_builds(
        first_build=build,
        second_build=BuildConfig("B", 20, "1d4", 1),
        scenario=ScenarioConfig(1, 1, 1),
        seed=1,
    )
    results._render_comparison_results(comparison)

    assert calls == ["single", "comparison"]


def test_feature_expander_is_collapsed_and_uses_helpful_stable_checkbox_keys(
    monkeypatch,
) -> None:
    import sys
    from types import SimpleNamespace

    from dnd_combat_simulator.combat import AttackFeature
    from dnd_combat_simulator.ui.constants import FEATURE_HELP
    from dnd_combat_simulator.ui.inputs import _attack_profile_inputs

    calls: list[tuple[str, object]] = []

    class Context:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class Column:
        def number_input(self, label, **kwargs):
            return kwargs.get("value", 1)

        def text_input(self, label, **kwargs):
            return kwargs.get("value", "")

        def selectbox(self, label, **kwargs):
            return kwargs["options"][kwargs.get("index", 0)]

    col = Column()

    def expander(label, **kwargs):
        calls.append(("expander", {"label": label, **kwargs}))
        return Context()

    def checkbox(label, **kwargs):
        calls.append(("checkbox", {"label": label, **kwargs}))
        return label == "Great Weapon Fighting"

    def columns(spec, **kwargs):
        calls.append(("columns", {"spec": spec, **kwargs}))
        return [col for _ in range(spec)]

    fake_streamlit = SimpleNamespace(
        selectbox=col.selectbox,
        text_input=col.text_input,
        number_input=col.number_input,
        columns=columns,
        expander=expander,
        checkbox=checkbox,
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

    profile = _attack_profile_inputs("first-primary", "Attack")

    assert profile.features == frozenset({AttackFeature.GREAT_WEAPON_FIGHTING})
    assert (
        "expander",
        {
            "label": "Features: None",
            "expanded": False,
            "key": "first-primary-features-expanded",
        },
    ) in calls
    assert ("columns", {"spec": 3}) in calls
    checkbox_calls = [call for kind, call in calls if kind == "checkbox"]
    assert [call["label"] for call in checkbox_calls] == [
        "Elven Accuracy",
        "Great Weapon Fighting",
        "Tavern Brawler",
        "Stop on Miss",
        "Potent Cantrip",
    ]
    assert checkbox_calls[0]["key"] == "first-primary-feature-elven_accuracy"
    assert checkbox_calls[0]["help"] == FEATURE_HELP[AttackFeature.ELVEN_ACCURACY]
    assert checkbox_calls[3]["key"] == "first-primary-feature-stop_on_miss"
    assert checkbox_calls[3]["help"] == FEATURE_HELP[AttackFeature.STOP_ON_MISS]
    assert checkbox_calls[3]["disabled"] is False


def test_profile_breakdown_rows_include_formatted_features() -> None:
    from dnd_combat_simulator.combat import AttackFeature
    from dnd_combat_simulator.simulation import (
        AttackProfile,
        BuildConfig,
        ScenarioConfig,
    )
    from dnd_combat_simulator.ui.results import _profile_breakdown_rows
    from dnd_combat_simulator.ui.run_control import (
        SingleBuildInputs,
        run_single_build_from_inputs,
    )

    result = run_single_build_from_inputs(
        SingleBuildInputs(
            build=BuildConfig(
                "Features",
                20,
                "1d4",
                1,
                attack_profiles=(
                    AttackProfile("Plain", 20, "1d4", 1, attack_id="plain"),
                    AttackProfile(
                        "Featured",
                        20,
                        "1d4",
                        1,
                        attack_id="featured",
                        features=frozenset(
                            {
                                AttackFeature.TAVERN_BRAWLER,
                                AttackFeature.GREAT_WEAPON_FIGHTING,
                            }
                        ),
                    ),
                ),
            ),
            scenario=ScenarioConfig(target_armor_class=1, rounds=1, simulations=1),
            seed=1,
        )
    )

    rows = _profile_breakdown_rows(result)
    assert rows[0]["Feats and Features"] == "None"
    assert rows[1]["Feats and Features"] == "Great Weapon Fighting, Tavern Brawler"


def test_profile_contribution_chart_data_sums_and_preserves_order() -> None:
    import pytest

    from dnd_combat_simulator.ui.results import _profile_contribution_chart_data

    build, result = _mixed_profile_result()

    rows = _profile_contribution_chart_data(result, build.name)

    assert [row["Profile"] for row in rows] == ["Zero opener", "Save effect", "Aura"]
    assert sum(row["Damage per Round contribution"] for row in rows) == pytest.approx(
        result.average_damage_per_round
    )
    assert sum(row["Contribution percentage"] for row in rows) == pytest.approx(100)


def test_profile_contribution_percentages_zero_when_dpr_is_zero() -> None:
    from dnd_combat_simulator.simulation import (
        BuildConfig,
        ScenarioConfig,
        simulate_build,
    )
    from dnd_combat_simulator.ui.results import _profile_contribution_chart_data

    result = simulate_build(
        BuildConfig("Zero", 0, "1d4", 1),
        ScenarioConfig(target_armor_class=99, rounds=2, simulations=1),
        seed=1,
    )

    rows = _profile_contribution_chart_data(result, "Zero")

    assert rows[0]["Damage per Round contribution"] == 0
    assert rows[0]["Contribution percentage"] == 0


def test_profile_damage_per_use_chart_uses_average_damage_per_use() -> None:
    from dnd_combat_simulator.combat import ResolutionType
    from dnd_combat_simulator.simulation import (
        AttackProfile,
        BuildConfig,
        ScenarioConfig,
        simulate_build,
    )
    from dnd_combat_simulator.ui.results import _profile_damage_per_use_chart_data

    build = BuildConfig(
        "Limited",
        0,
        "1d4",
        0,
        attack_profiles=(
            AttackProfile(
                "Once",
                None,
                "1d4",
                1,
                active_rounds="1",
                resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
            ),
        ),
    )
    result = simulate_build(build, ScenarioConfig(10, rounds=2, simulations=1), seed=4)

    row = _profile_damage_per_use_chart_data(result, build.name)[0]

    assert (
        row["Average damage per use"]
        == result.attack_profile_results[0].average_damage_per_use
    )
    assert (
        row["Average damage per use"]
        != result.attack_profile_results[0].average_damage_per_round
    )


def test_attack_roll_saving_throw_and_automatic_profiles_appear_in_chart_data() -> None:
    from dnd_combat_simulator.ui.results import (
        _profile_contribution_chart_data,
        _profile_damage_per_use_chart_data,
    )

    build, result = _mixed_profile_result()

    contribution_rows = _profile_contribution_chart_data(result, build.name)
    use_rows = _profile_damage_per_use_chart_data(result, build.name)

    assert {row["Resolution type"] for row in contribution_rows} == {
        "Attack Roll",
        "Saving Throw",
        "Automatic Damage",
    }
    assert [row["Build"] for row in use_rows] == [build.name, build.name, build.name]


def test_stop_on_miss_feature_input_is_unavailable_when_ineligible(monkeypatch) -> None:
    import sys
    from types import SimpleNamespace

    from dnd_combat_simulator.combat import ResolutionType
    from dnd_combat_simulator.ui.inputs import _feature_inputs

    disabled_by_label: dict[str, bool] = {}

    class Context:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def checkbox(label, **kwargs):
        disabled_by_label[label] = kwargs["disabled"]
        return True

    fake_streamlit = SimpleNamespace(
        expander=lambda *args, **kwargs: Context(),
        checkbox=checkbox,
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

    _feature_inputs("save", ResolutionType.SAVING_THROW, 1)
    assert disabled_by_label["Great Weapon Fighting"] is True
    assert disabled_by_label["Tavern Brawler"] is True
    assert disabled_by_label["Potent Cantrip"] is False
    assert disabled_by_label["Stop on Miss"] is True

    disabled_by_label.clear()
    _feature_inputs("auto", ResolutionType.AUTOMATIC_DAMAGE, 1)
    assert disabled_by_label["Great Weapon Fighting"] is True
    assert disabled_by_label["Tavern Brawler"] is True
    assert disabled_by_label["Potent Cantrip"] is True

    disabled_by_label.clear()
    _feature_inputs("multi", ResolutionType.ATTACK_ROLL, 2)
    assert disabled_by_label["Stop on Miss"] is True


def test_repository_does_not_reference_removed_url_shorteners() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    forbidden = [
        "clean" + "uri",
        "clean" + "uri.com",
        "is" + ".gd",
        "tiny" + "url",
        "v" + ".gd",
        "tiny" + "src",
    ]
    for path in root.rglob("*"):
        if (
            path.is_file()
            and ".git" not in path.parts
            and ".pytest_cache" not in path.parts
            and "__pycache__" not in path.parts
        ):
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            for value in forbidden:
                assert value not in text


def test_share_toolbar_passes_exact_first_party_url_to_v2_component(
    monkeypatch,
) -> None:
    import sys
    from types import SimpleNamespace

    import ui_test_api as app

    calls: list[tuple[str, object]] = []

    def component(name, **kwargs):
        calls.append(("component_register", {"name": name, **kwargs}))

        def mount(**mount_kwargs):
            calls.append(("component_mount", mount_kwargs))

        return mount

    state = {
        app.SCENARIO_WIDGET_KEYS["target_armor_class"]: 18,
        app.SCENARIO_WIDGET_KEYS["enemy_save_bonus"]: 5,
        app.SCENARIO_WIDGET_KEYS["rounds"]: 7,
        app.SCENARIO_WIDGET_KEYS["simulations"]: 1234,
        app.SCENARIO_WIDGET_KEYS["seed"]: 99,
        app.COMPARE_WIDGET_KEY: True,
        "first-build-name": "Build A Exact",
        "first-primary-name": "A Blade",
        "first-primary-resolution-type": "Attack Roll",
        "first-primary-attack-bonus": 8,
        "first-primary-mode": "Advantage",
        "first-primary-damage-dice": "2d6+4",
        "first-primary-attacks": 2,
        "first-primary-affected-targets": 1,
        "first-primary-active-rounds": "1-7",
        "second-build-name": "Build B Exact",
        "second-primary-name": "B Blast",
        "second-primary-resolution-type": "Saving Throw",
        "second-primary-save-dc": 16,
        "second-primary-successful-save-damage": "Half damage",
        "second-primary-damage-dice": "3d8",
        "second-primary-attacks": 1,
        "second-primary-affected-targets": 3,
        "second-primary-active-rounds": "1-4",
    }
    fake_streamlit = SimpleNamespace(
        session_state=state,
        context=SimpleNamespace(url="https://first-party.example/sim?old=1"),
        components=SimpleNamespace(v2=SimpleNamespace(component=component)),
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)
    monkeypatch.setattr(app, "_SHARE_TOOLBAR_COMPONENT", None)

    monkeypatch.setattr(app, "get_streamlit_share_store", lambda: _FakeShareStore())
    state[app.GENERATED_SHARE_URL_KEY] = (
        "https://first-party.example/sim?share=yiEwgVR97pGY"
    )

    app._render_share_configuration_button()

    registrations = [call[1] for call in calls if call[0] == "component_register"]
    assert len(registrations) == 1
    assert registrations[0]["name"] == "share_toolbar"
    assert registrations[0]["html"] == app.SHARE_TOOLBAR_HTML
    assert registrations[0]["css"] == app.SHARE_TOOLBAR_CSS
    assert registrations[0]["js"] == app.SHARE_TOOLBAR_JS

    mounts = [call[1] for call in calls if call[0] == "component_mount"]
    assert len(mounts) == 1
    assert list(mounts[0]) == ["data", "key", "on_create_share_change"]
    assert mounts[0]["key"] == "unified-share-configuration"
    assert callable(mounts[0]["on_create_share_change"])
    share_url = mounts[0]["data"]["url"]
    assert share_url == "https://first-party.example/sim?share=yiEwgVR97pGY"


def test_share_source_uses_v2_without_obsolete_copy_controls() -> None:
    from pathlib import Path

    source = Path("src/dnd_combat_simulator/ui/sharing.py").read_text()

    assert "_mount_unified_share_component" in source
    assert "st.components.v1.html" not in source
    assert "components.html" not in source
    assert "iframe" not in source.lower()
    share_source = source[source.index("def _render_share_configuration_button") :]
    assert "disabled" in share_source
    assert "create_share" in share_source


def test_render_share_configuration_button_invalid_damage_does_not_raise_or_serialize(
    monkeypatch,
) -> None:
    import sys
    from types import SimpleNamespace

    import ui_test_api as app

    mounts: list[dict[str, object]] = []
    state = {
        "first-build-name": "Build A",
        "first-additional-attack-count": 0,
        app.build_attack_ids_key("first"): ["attack-primary"],
        app.profile_widget_key("first-attack-primary", "damage_formula"): "1d6+",
    }

    def component(**kwargs):
        mounts.append(kwargs)
        return None

    fake_streamlit = SimpleNamespace(
        session_state=state,
        context=SimpleNamespace(url="https://example.test/app"),
        components=SimpleNamespace(
            v2=SimpleNamespace(component=lambda *a, **k: component)
        ),
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

    def serialize_should_not_run(configuration):
        raise AssertionError("serialization should not run while invalid")

    monkeypatch.setattr(app, "serialize_shared_configuration", serialize_should_not_run)

    app._render_share_configuration_button()

    assert len(mounts) == 1
    assert mounts[0]["data"]["disabled"] is True


def test_validate_configuration_for_ui_scopes_damage_error_to_exact_build_profile() -> (
    None
):
    import ui_test_api as app

    from dnd_combat_simulator.sharing import shared_configuration_from_configs
    from dnd_combat_simulator.simulation import (
        AttackProfile,
        BuildConfig,
        ScenarioConfig,
    )

    configuration = shared_configuration_from_configs(
        compare_enabled=True,
        scenario=ScenarioConfig(15, 3, 4, 10),
        seed=1,
        build_a=BuildConfig(
            "Build A",
            5,
            "1d6+",
            1,
            attack_profiles=(AttackProfile("A", 5, "1d6+", 1),),
        ),
        build_b=BuildConfig(
            "Build B",
            5,
            "1d6+3",
            1,
            attack_profiles=(AttackProfile("B", 5, "1d6+3", 1),),
        ),
    )

    errors = app.validate_configuration_for_ui(configuration)

    assert errors == {
        (
            "build_a",
            "profile_1",
            "damage_dice",
        ): "Damage expression cannot end with an operator."
    }


def test_run_button_not_execute_simulation_while_invalid(monkeypatch) -> None:
    import sys
    from types import SimpleNamespace

    import ui_test_api as app

    calls: list[tuple[str, dict[str, object]]] = []
    state = {
        "first-build-name": "Build A",
        "first-additional-attack-count": 0,
        app.build_attack_ids_key("first"): ["attack-primary"],
        app.profile_widget_key("first-attack-primary", "damage_formula"): "1d6+",
    }

    def component(**kwargs):
        return None

    class Column:
        def number_input(self, label, **kwargs):
            return state.get(kwargs.get("key"), kwargs.get("value", 1))

        def text_input(self, label, **kwargs):
            return state.get(kwargs.get("key"), kwargs.get("value", ""))

        def selectbox(self, label, **kwargs):
            return state.get(
                kwargs.get("key"), kwargs["options"][kwargs.get("index", 0)]
            )

    col = Column()

    def button(label, **kwargs):
        calls.append((label, kwargs))
        return False if kwargs.get("disabled") else True

    fake_streamlit = SimpleNamespace(
        session_state=state,
        set_page_config=lambda **kwargs: None,
        markdown=lambda *a, **k: None,
        title=lambda *a, **k: None,
        write=lambda *a, **k: None,
        subheader=lambda *a, **k: None,
        success=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
        button=button,
        components=SimpleNamespace(
            v2=SimpleNamespace(component=lambda *a, **k: component)
        ),
        columns=lambda spec, **kwargs: [
            col for _ in range(spec if isinstance(spec, int) else len(spec))
        ],
        number_input=col.number_input,
        text_input=col.text_input,
        selectbox=col.selectbox,
        toggle=lambda *a, **k: False,
        container=lambda **kwargs: __import__("contextlib").nullcontext(),
        expander=lambda *a, **k: __import__("contextlib").nullcontext(),
        checkbox=lambda *a, **k: False,
        divider=lambda: None,
        query_params={},
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)
    monkeypatch.setattr(
        app,
        "run_single_build_from_inputs",
        lambda inputs: (_ for _ in ()).throw(
            AssertionError("simulation should not run")
        ),
    )

    app.main()

    assert any(
        label == "Run Simulation" and kwargs["disabled"] is True
        for label, kwargs in calls
    )


def test_run_single_build_with_feedback_sets_running_state_and_duration(
    monkeypatch,
) -> None:
    import sys
    from contextlib import contextmanager
    from types import SimpleNamespace

    import ui_test_api as app

    state = {}
    events: list[str] = []

    @contextmanager
    def spinner(message):
        events.append(message)
        assert state[app.SIMULATION_RUNNING_KEY] is True
        yield

    result = object()
    monkeypatch.setitem(
        sys.modules,
        "streamlit",
        SimpleNamespace(session_state=state, spinner=spinner),
    )
    monkeypatch.setattr(app.time, "perf_counter", iter([10.0, 17.24]).__next__)
    monkeypatch.setattr(app, "run_single_build_from_inputs", lambda inputs: result)

    assert app._run_single_build_with_feedback(object()) is result

    assert events == ["Calculating..."]
    assert state[app.SIMULATION_RUNNING_KEY] is False
    assert state[app.SIMULATION_PENDING_KEY] is False
    assert state[app.SIMULATION_DURATION_MESSAGE_KEY] == (
        "Simulation complete in 7.2 seconds."
    )


def test_mark_simulation_pending_ignores_active_run(monkeypatch) -> None:
    import sys
    from types import SimpleNamespace

    import ui_test_api as app

    state = {app.SIMULATION_RUNNING_KEY: True}
    monkeypatch.setitem(sys.modules, "streamlit", SimpleNamespace(session_state=state))

    app._mark_simulation_pending()

    assert app.SIMULATION_PENDING_KEY not in state


def test_share_component_copies_inside_button_click_with_fallback() -> None:
    import ui_test_api as app

    js = app.SHARE_TOOLBAR_JS
    onclick_index = js.index("button.onclick = async () =>")
    trigger_index = js.index("setTriggerValue('create_share'")
    write_index = js.index("navigator.clipboard.writeText(targetUrl)")
    fallback_index = js.index('document.execCommand("copy")')
    assert write_index < fallback_index
    assert onclick_index < trigger_index
    show_copied_index = js.index("function showCopied()")
    render_index = js.index("function render(nextData)")
    assert "latestData = nextData || {}" in js
    assert "const targetUrl = latestData.url || ''" in js
    assert "window.isSecureContext" in js
    assert "copy_nonce" not in js
    assert "lastCopyNonce" not in js
    assert "copyUrl(data.url" not in js
    assert "copyUrl();" in js[onclick_index:]
    copy_branch = js[js.index("} else if (mode === 'copy')") :]
    assert "setTriggerValue('create_share'" not in copy_branch
    assert show_copied_index < render_index
    assert "showCopied();" in js[write_index:fallback_index]
    assert "showCopied();" in js[fallback_index:]
    assert "Copy blocked. Press Ctrl+C." in js
    assert "setTriggerValue" in js
    assert "setStateValue" not in js[:write_index]


def test_share_component_markup_and_css_are_accessible_and_theme_compatible() -> None:
    import ui_test_api as app

    html = app.SHARE_TOOLBAR_HTML
    css = app.SHARE_TOOLBAR_CSS
    combined = f"{html}\n{css}"

    assert 'class="share-button"' in html
    assert 'title="Copy share link"' in html
    assert 'aria-label="Copy share link"' in html
    assert "<svg" in html
    assert 'stroke="currentColor"' in html
    assert 'class="share-status"' in html
    assert (
        'class="share-link" href="" target="_blank" rel="noopener noreferrer" hidden'
        in html
    )
    assert 'class="share-fallback" type="text" readonly hidden' in html
    assert "min-width: 42px" in css
    assert "height: 42px" in css
    assert "border-radius: 999px" in css
    assert "text-overflow: ellipsis" in css
    assert "height: 42px" in css
    assert "--st-text-color" in css
    assert "--st-background-color" in css
    assert "--st-secondary-background-color" in css
    assert "--st-border-color" in css
    assert "--st-primary-color" in css
    assert "--st-font" in css
    assert "focus-visible" in css
    assert "black" not in combined.lower()
    assert "white" not in combined.lower().replace("white-space", "")


def test_configuration_toolbar_css_keeps_settings_and_share_compact() -> None:
    import ui_test_api as app

    toolbar_css = app.CONFIGURATION_TOOLBAR_CSS
    share_css = app.SHARE_TOOLBAR_CSS

    assert "gap: 8px" in toolbar_css
    assert "gap: 8px" in share_css
    assert "width: max-content" in toolbar_css
    assert "width: max-content" in share_css
    assert "height: 42px" in toolbar_css
    assert "height: 42px" in share_css
    assert "border: 1px solid var(--st-border-color)" in toolbar_css
    assert "border: 1px solid var(--st-border-color)" in share_css
    assert "background: var(--st-secondary-background-color)" in toolbar_css
    assert "background: var(--st-secondary-background-color)" in share_css
    assert "border-radius: 999px" in toolbar_css
    assert "border-radius: 999px" in share_css
    assert "hover:not(:disabled)" in toolbar_css
    assert "hover:not(:disabled)" in share_css
    assert "focus-visible" in toolbar_css
    assert "focus-visible" in share_css


def test_main_uses_content_width_horizontal_toolbar_not_wide_columns() -> None:
    from pathlib import Path

    source = Path("src/dnd_combat_simulator/ui/page.py").read_text()
    toolbar_source = Path("src/dnd_combat_simulator/ui/inputs.py").read_text()
    main_source = source[source.index("def main") :]
    main_toolbar_source = main_source[
        : main_source.index("with _render_section_container()")
    ]

    assert 'key="configuration-toolbar"' in toolbar_source
    assert 'width="content"' in toolbar_source
    assert "horizontal=True" in toolbar_source
    assert 'vertical_alignment="center"' in toolbar_source
    assert "gap=None" in toolbar_source
    assert "_render_simulation_settings()" in toolbar_source
    assert "_render_share_configuration_button()" in toolbar_source
    assert "st.columns([1, 8])" not in main_toolbar_source
    assert "_render_configuration_toolbar()" in main_toolbar_source


def test_build_from_state_filters_attack_roll_feature_after_automatic_damage_change(
    monkeypatch,
) -> None:
    import sys
    from types import SimpleNamespace

    from dnd_combat_simulator.combat import AttackFeature, ResolutionType
    from dnd_combat_simulator.ui.state import _build_from_state
    from dnd_combat_simulator.ui.widget_keys import (
        feature_widget_key,
        profile_widget_key,
    )

    state = {
        "first-build-name": "Build A",
        "first-additional-attack-count": 0,
        profile_widget_key("first-primary", "resolution_type"): "Automatic Damage",
        feature_widget_key("first-primary", AttackFeature.ELVEN_ACCURACY): True,
    }
    monkeypatch.setitem(sys.modules, "streamlit", SimpleNamespace(session_state=state))

    profile = _build_from_state("first", "Build A").attack_profiles[0]
    assert profile.resolution_type is ResolutionType.AUTOMATIC_DAMAGE
    assert AttackFeature.ELVEN_ACCURACY not in profile.features


@pytest.mark.parametrize(
    "resolution_label",
    ["Saving Throw", "Automatic Damage"],
)
def test_build_from_state_ignores_stale_attack_roll_only_features(
    monkeypatch, resolution_label
) -> None:
    import sys
    from types import SimpleNamespace

    from dnd_combat_simulator.combat import AttackFeature
    from dnd_combat_simulator.ui.state import _build_from_state
    from dnd_combat_simulator.ui.widget_keys import (
        feature_widget_key,
        profile_widget_key,
    )

    state = {
        "first-build-name": "Build A",
        "first-additional-attack-count": 0,
        profile_widget_key("first-primary", "resolution_type"): resolution_label,
        feature_widget_key("first-primary", AttackFeature.GREAT_WEAPON_FIGHTING): True,
        feature_widget_key("first-primary", AttackFeature.TAVERN_BRAWLER): True,
    }
    monkeypatch.setitem(sys.modules, "streamlit", SimpleNamespace(session_state=state))

    profile = _build_from_state("first", "Build A").attack_profiles[0]
    assert profile.features == frozenset()


def test_build_from_state_filters_potent_cantrip_for_automatic_damage(
    monkeypatch,
) -> None:
    import sys
    from types import SimpleNamespace

    from dnd_combat_simulator.combat import AttackFeature
    from dnd_combat_simulator.ui.state import _build_from_state
    from dnd_combat_simulator.ui.widget_keys import (
        feature_widget_key,
        profile_widget_key,
    )

    state = {
        "first-build-name": "Build A",
        "first-additional-attack-count": 0,
        profile_widget_key("first-primary", "resolution_type"): "Automatic Damage",
        feature_widget_key("first-primary", AttackFeature.POTENT_CANTRIP): True,
    }
    monkeypatch.setitem(sys.modules, "streamlit", SimpleNamespace(session_state=state))

    profile = _build_from_state("first", "Build A").attack_profiles[0]
    assert profile.features == frozenset()


def test_build_from_state_filters_stop_on_miss_when_targets_exceed_one(
    monkeypatch,
) -> None:
    import sys
    from types import SimpleNamespace

    from dnd_combat_simulator.combat import AttackFeature
    from dnd_combat_simulator.ui.state import _build_from_state
    from dnd_combat_simulator.ui.widget_keys import (
        feature_widget_key,
        profile_widget_key,
    )

    state = {
        "first-build-name": "Build A",
        "first-additional-attack-count": 0,
        profile_widget_key("first-primary", "resolution_type"): "Attack Roll",
        profile_widget_key("first-primary", "affected_targets"): 2,
        feature_widget_key("first-primary", AttackFeature.STOP_ON_MISS): True,
    }
    monkeypatch.setitem(sys.modules, "streamlit", SimpleNamespace(session_state=state))

    profile = _build_from_state("first", "Build A").attack_profiles[0]
    assert profile.features == frozenset()


def test_current_shared_configuration_url_ignores_stale_unavailable_features(
    monkeypatch,
) -> None:
    import sys
    from types import SimpleNamespace

    from dnd_combat_simulator.combat import AttackFeature
    from dnd_combat_simulator.ui.sharing import _current_shared_configuration_url
    from dnd_combat_simulator.ui.widget_keys import (
        feature_widget_key,
        profile_widget_key,
    )

    state = {
        "first-build-name": "Build A",
        "first-additional-attack-count": 0,
        profile_widget_key("first-primary", "resolution_type"): "Automatic Damage",
        feature_widget_key("first-primary", AttackFeature.ELVEN_ACCURACY): True,
        feature_widget_key("first-primary", AttackFeature.POTENT_CANTRIP): True,
    }
    fake_streamlit = SimpleNamespace(
        session_state=state,
        context=SimpleNamespace(url="https://example.test/app"),
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

    url = _current_shared_configuration_url()

    assert url.startswith("https://example.test/app?")


def test_validate_build_fields_marks_invalid_damage_field_and_message() -> None:
    from dnd_combat_simulator.simulation import AttackProfile, BuildConfig
    from dnd_combat_simulator.ui.validation import validate_build_fields
    from dnd_combat_simulator.ui.widget_keys import profile_widget_key

    build = BuildConfig(
        "Build A",
        5,
        "1d6+",
        1,
        attack_profiles=(
            AttackProfile("Primary", 5, "1d6+", 1, attack_id="attack-primary"),
        ),
    )

    errors = validate_build_fields(build, prefix="first")

    assert errors == [errors[0]]
    assert errors[0].key == profile_widget_key("first-attack-primary", "damage_formula")
    assert errors[0].message == "Damage expression cannot end with an operator."


def test_correcting_invalid_damage_clears_field_error_and_valid_build_runs() -> None:
    from dnd_combat_simulator.simulation import (
        AttackProfile,
        BuildConfig,
        ScenarioConfig,
    )
    from dnd_combat_simulator.ui.run_control import (
        SingleBuildInputs,
        run_single_build_from_inputs,
    )
    from dnd_combat_simulator.ui.validation import validate_build_fields
    from dnd_combat_simulator.ui.widget_keys import profile_widget_key

    invalid = BuildConfig(
        "Build A",
        5,
        "1d6+",
        1,
        attack_profiles=(
            AttackProfile("Primary", 5, "1d6+", 1, attack_id="attack-primary"),
        ),
    )
    valid = BuildConfig(
        "Build A",
        5,
        "1d6+1",
        1,
        attack_profiles=(
            AttackProfile("Primary", 5, "1d6+1", 1, attack_id="attack-primary"),
        ),
    )

    assert any(
        error.key == profile_widget_key("first-attack-primary", "damage_formula")
        for error in validate_build_fields(invalid, prefix="first")
    )
    assert validate_build_fields(valid, prefix="first") == []
    result = run_single_build_from_inputs(
        SingleBuildInputs(valid, ScenarioConfig(1, 1, 1), seed=1)
    )
    assert result.simulations_run == 1


def _sample_shared_configuration():
    from dnd_combat_simulator.sharing import shared_configuration_from_configs
    from dnd_combat_simulator.simulation import BuildConfig, ScenarioConfig

    return shared_configuration_from_configs(
        compare_enabled=False,
        scenario=ScenarioConfig(17, 2, 3, 100),
        seed=42,
        build_a=BuildConfig("A", 6, "1d10+4", 2),
        build_b=BuildConfig("B", 5, "1d8+3", 1),
    )


class _FakeShareStore:
    def __init__(self, configuration=None, *, load_error=None, save_error=None):
        self.configuration = configuration or _sample_shared_configuration()
        self.load_error = load_error
        self.save_error = save_error
        self.loaded = []
        self.saved = []

    def load(self, share_id):
        self.loaded.append(share_id)
        if self.load_error:
            raise self.load_error
        return self.configuration

    def save(self, configuration):
        self.saved.append(configuration)
        if self.save_error:
            raise self.save_error
        return "yiEwgVR97pGY"


def test_share_query_loads_and_hydrates_session_state(monkeypatch):
    import sys
    from types import SimpleNamespace

    import ui_test_api as app

    state = {}
    fake_streamlit = SimpleNamespace(
        query_params={"share": "abc123"},
        session_state=state,
        error=lambda message: None,
    )
    store = _FakeShareStore()
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)
    monkeypatch.setattr(app, "get_streamlit_share_store", lambda: store)

    app.load_shared_configuration_from_query()

    assert store.loaded == ["abc123"]
    assert state[app.SCENARIO_WIDGET_KEYS["target_armor_class"]] == 17
    assert state[app.LOADED_SHARE_ID_KEY] == "abc123"
    assert state[app.LOADED_SHARED_CONFIG_MESSAGE_KEY] is True

    app.load_shared_configuration_from_query()
    assert store.loaded == ["abc123"]


def test_legacy_config_query_still_loads(monkeypatch):
    import sys
    from types import SimpleNamespace

    import ui_test_api as app

    from dnd_combat_simulator.sharing import serialize_shared_configuration

    token = serialize_shared_configuration(_sample_shared_configuration())
    state = {}
    fake_streamlit = SimpleNamespace(
        query_params={"config": token}, session_state=state
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

    app.load_shared_configuration_from_query()

    assert state[app.SCENARIO_WIDGET_KEYS["target_armor_class"]] == 17
    assert state[app.LOADED_SHARED_CONFIG_TOKEN_KEY] == token


def test_share_query_takes_precedence_over_config(monkeypatch):
    import sys
    from types import SimpleNamespace

    import ui_test_api as app

    from dnd_combat_simulator.sharing import serialize_shared_configuration

    legacy = _sample_shared_configuration()
    token = serialize_shared_configuration(legacy)
    state = {}
    fake_streamlit = SimpleNamespace(
        query_params={"share": "short", "config": token},
        session_state=state,
        error=lambda message: None,
    )
    store = _FakeShareStore()
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)
    monkeypatch.setattr(app, "get_streamlit_share_store", lambda: store)

    app.load_shared_configuration_from_query()

    assert store.loaded == ["short"]
    assert app.LOADED_SHARED_CONFIG_TOKEN_KEY not in state


def test_share_load_errors_are_safe(monkeypatch):
    import sys
    from types import SimpleNamespace

    import ui_test_api as app

    from dnd_combat_simulator.share_store import (
        InvalidShareIdError,
        ShareNotFoundError,
        ShareStoreError,
    )

    cases = [
        (
            ShareNotFoundError("missing secret detail"),
            "This shared configuration could not be found.",
        ),
        (
            InvalidShareIdError("bad secret detail"),
            "Invalid shared configuration link.",
        ),
        (
            ShareStoreError("database secret detail"),
            "Shared configurations are temporarily unavailable. Try again later.",
        ),
    ]
    for error, expected in cases:
        messages = []
        fake_streamlit = SimpleNamespace(
            query_params={"share": "abc"}, session_state={}, error=messages.append
        )
        monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)
        monkeypatch.setattr(
            app,
            "get_streamlit_share_store",
            lambda e=error: _FakeShareStore(load_error=e),
        )

        app.load_shared_configuration_from_query()

        assert messages == [expected]


def test_missing_streamlit_secrets_returns_no_store():
    import ui_test_api as app

    assert app.get_supabase_share_store_from_secrets({}) is None


def test_short_share_save_success_and_failure(monkeypatch):
    import sys
    from types import SimpleNamespace

    import ui_test_api as app

    from dnd_combat_simulator.share_store import ShareStoreError

    state = {
        app.SCENARIO_WIDGET_KEYS["target_armor_class"]: 15,
        app.SCENARIO_WIDGET_KEYS["enemy_save_bonus"]: 3,
        app.SCENARIO_WIDGET_KEYS["rounds"]: 4,
        app.SCENARIO_WIDGET_KEYS["simulations"]: 10,
        app.SCENARIO_WIDGET_KEYS["seed"]: 1,
    }
    fake_streamlit = SimpleNamespace(
        session_state=state,
        context=SimpleNamespace(url="https://example.test/sim?old=1"),
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)
    store = _FakeShareStore()

    url = app._current_short_shared_configuration_url(store)

    assert url == "https://example.test/sim?share=yiEwgVR97pGY"
    assert len(store.saved) == 1

    failing = _FakeShareStore(save_error=ShareStoreError("database detail"))
    with pytest.raises(ShareStoreError):
        app._current_short_shared_configuration_url(failing)
    assert len(failing.saved) == 1


def test_unified_share_trigger_saves_once_and_rerun_does_not_repeat(monkeypatch):
    import sys
    from types import SimpleNamespace

    import ui_test_api as app

    mounts = []
    state = {
        app.SCENARIO_WIDGET_KEYS["target_armor_class"]: 15,
        app.SCENARIO_WIDGET_KEYS["enemy_save_bonus"]: 3,
        app.SCENARIO_WIDGET_KEYS["rounds"]: 4,
        app.SCENARIO_WIDGET_KEYS["simulations"]: 10,
        app.SCENARIO_WIDGET_KEYS["seed"]: 1,
    }

    def mount(**kwargs):
        mounts.append(kwargs)
        if len(mounts) == 1:
            kwargs["on_create_share_change"]()
        return None

    fake_streamlit = SimpleNamespace(
        session_state=state,
        context=SimpleNamespace(url="https://example.test/sim?old=1"),
        components=SimpleNamespace(v2=SimpleNamespace(component=lambda *a, **k: mount)),
        error=lambda message: None,
    )
    store = _FakeShareStore()
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)
    monkeypatch.setattr(app, "get_streamlit_share_store", lambda: store)
    monkeypatch.setattr(app, "_SHARE_TOOLBAR_COMPONENT", None)

    app._render_share_configuration_button()
    app._render_share_configuration_button()

    assert len(store.saved) == 1
    assert (
        state[app.GENERATED_SHARE_URL_KEY]
        == "https://example.test/sim?share=yiEwgVR97pGY"
    )
    assert len(mounts) == 2
    assert mounts[1]["data"]["url"] == "https://example.test/sim?share=yiEwgVR97pGY"


def test_unified_share_existing_url_copy_causes_no_insert(monkeypatch):
    import sys
    from types import SimpleNamespace

    import ui_test_api as app

    state = {
        app.SCENARIO_WIDGET_KEYS["target_armor_class"]: 15,
        app.SCENARIO_WIDGET_KEYS["enemy_save_bonus"]: 3,
        app.SCENARIO_WIDGET_KEYS["rounds"]: 4,
        app.SCENARIO_WIDGET_KEYS["simulations"]: 10,
        app.SCENARIO_WIDGET_KEYS["seed"]: 1,
        app.GENERATED_SHARE_URL_KEY: "https://example.test/sim?share=existing",
        app.GENERATED_SHARE_FINGERPRINT_KEY: "fp",
    }

    def mount(**kwargs):
        return None

    fake_streamlit = SimpleNamespace(
        session_state=state,
        context=SimpleNamespace(url="https://example.test/sim"),
        components=SimpleNamespace(v2=SimpleNamespace(component=lambda *a, **k: mount)),
    )
    store = _FakeShareStore()
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)
    monkeypatch.setattr(app, "get_streamlit_share_store", lambda: store)
    monkeypatch.setattr(app, "_SHARE_TOOLBAR_COMPONENT", None)
    monkeypatch.setattr(
        app, "_share_configuration_fingerprint", lambda configuration: "fp"
    )

    app._render_share_configuration_button()

    assert store.saved == []


def test_unified_share_configuration_change_invalidates_then_saves_new(monkeypatch):
    import sys
    from types import SimpleNamespace

    import ui_test_api as app

    state = {
        app.SCENARIO_WIDGET_KEYS["target_armor_class"]: 15,
        app.SCENARIO_WIDGET_KEYS["enemy_save_bonus"]: 3,
        app.SCENARIO_WIDGET_KEYS["rounds"]: 4,
        app.SCENARIO_WIDGET_KEYS["simulations"]: 10,
        app.SCENARIO_WIDGET_KEYS["seed"]: 1,
        app.GENERATED_SHARE_URL_KEY: "https://example.test/sim?share=old",
        app.GENERATED_SHARE_FINGERPRINT_KEY: "stale",
    }

    def mount(**kwargs):
        mounts.append(kwargs)
        if len(mounts) == 2:
            kwargs["on_create_share_change"]()
        return None

    mounts = []

    fake_streamlit = SimpleNamespace(
        session_state=state,
        context=SimpleNamespace(url="https://example.test/sim"),
        components=SimpleNamespace(v2=SimpleNamespace(component=lambda *a, **k: mount)),
        error=lambda message: None,
    )
    store = _FakeShareStore()
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)
    monkeypatch.setattr(app, "get_streamlit_share_store", lambda: store)
    monkeypatch.setattr(app, "_SHARE_TOOLBAR_COMPONENT", None)

    app._render_share_configuration_button()
    assert app.GENERATED_SHARE_URL_KEY not in state
    app._render_share_configuration_button()

    assert len(store.saved) == 1
    assert (
        state[app.GENERATED_SHARE_URL_KEY]
        == "https://example.test/sim?share=yiEwgVR97pGY"
    )


def test_unified_share_save_error_is_safe(monkeypatch):
    import sys
    from types import SimpleNamespace

    import ui_test_api as app

    from dnd_combat_simulator.share_store import ShareStoreError

    messages = []
    state = {
        app.SCENARIO_WIDGET_KEYS["target_armor_class"]: 15,
        app.SCENARIO_WIDGET_KEYS["enemy_save_bonus"]: 3,
        app.SCENARIO_WIDGET_KEYS["rounds"]: 4,
        app.SCENARIO_WIDGET_KEYS["simulations"]: 10,
        app.SCENARIO_WIDGET_KEYS["seed"]: 1,
    }

    def mount(**kwargs):
        kwargs["on_create_share_change"]()
        return None

    fake_streamlit = SimpleNamespace(
        session_state=state,
        context=SimpleNamespace(url="https://example.test/sim"),
        components=SimpleNamespace(v2=SimpleNamespace(component=lambda *a, **k: mount)),
    )
    store = _FakeShareStore(save_error=ShareStoreError("database secret detail"))
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)
    monkeypatch.setattr(app, "get_streamlit_share_store", lambda: store)
    monkeypatch.setattr(app, "_SHARE_TOOLBAR_COMPONENT", None)

    app._render_share_configuration_button()

    assert messages == []
    assert app.GENERATED_SHARE_URL_KEY not in state
    assert (
        state[app.SHARE_ERROR_MESSAGE_KEY]
        == "Unable to create a share link right now. Try again later."
    )


def test_missing_secrets_disable_unified_component(monkeypatch):
    import sys
    from types import SimpleNamespace

    import ui_test_api as app

    mounts = []
    fake_streamlit = SimpleNamespace(
        session_state={},
        context=SimpleNamespace(url="https://example.test/sim"),
        components=SimpleNamespace(
            v2=SimpleNamespace(component=lambda *a, **k: lambda **kw: mounts.append(kw))
        ),
        caption=lambda message: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)
    monkeypatch.setattr(app, "get_streamlit_share_store", lambda: None)
    monkeypatch.setattr(app, "_SHARE_TOOLBAR_COMPONENT", None)

    app._render_share_configuration_button()

    assert len(mounts) == 1
    assert mounts[0]["data"]["disabled"] is True
    assert "not configured" in mounts[0]["data"]["message"]


def test_fresh_session_receives_generated_seed_and_reruns_keep_it(monkeypatch) -> None:
    import ui_test_api as app

    generated = [8675309, 123]
    monkeypatch.setattr(app, "_generate_default_seed", lambda: generated.pop(0))
    state = {}

    assert app.ensure_session_random_seed(state) == 8675309
    assert state[app.SCENARIO_WIDGET_KEYS["seed"]] == 8675309
    assert app.ensure_session_random_seed(state) == 8675309
    assert generated == [123]


def test_shared_configuration_overrides_generated_seed() -> None:
    import ui_test_api as app

    from dnd_combat_simulator.sharing import (
        SharedAttackProfileConfiguration,
        SharedBuildConfiguration,
        SharedConfiguration,
        SharedScenarioConfiguration,
    )

    state = {app.SCENARIO_WIDGET_KEYS["seed"]: 111}
    from dnd_combat_simulator.combat import (
        AttackRollMode,
        ResolutionType,
        SuccessfulSaveDamage,
    )

    profile = SharedAttackProfileConfiguration(
        name="Blade",
        resolution_type=ResolutionType.ATTACK_ROLL,
        attack_bonus=5,
        save_dc=None,
        successful_save_damage=SuccessfulSaveDamage.NO_DAMAGE,
        attack_roll_mode=AttackRollMode.NORMAL,
        damage_formula="1d8+3",
        attacks_per_round=1,
        affected_targets=1,
        active_rounds="",
        features=frozenset(),
    )
    config = SharedConfiguration(
        version=1,
        compare_enabled=False,
        scenario=SharedScenarioConfiguration(
            target_armor_class=15,
            enemy_save_bonus=3,
            rounds=4,
            simulations=222,
            seed=999,
        ),
        build_a=SharedBuildConfiguration(name="Build A", attack_profiles=(profile,)),
        build_b=SharedBuildConfiguration(name="Build B", attack_profiles=(profile,)),
    )

    app.hydrate_session_state_from_shared_configuration(state, config)

    assert app.ensure_session_random_seed(state) == 999
    assert state[app.SCENARIO_WIDGET_KEYS["simulations"]] == 222


class _SettingsContainer:
    def __init__(self, calls, state):
        self.calls = calls
        self.state = state

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def number_input(self, label, **kwargs):
        self.calls.append((label, kwargs))
        key = kwargs["key"]
        return self.state.get(key, kwargs.get("value", 0))


def test_simulation_settings_keep_existing_widget_keys(monkeypatch) -> None:
    import sys
    from types import SimpleNamespace

    import ui_test_api as app

    calls = []
    state = {
        app.SCENARIO_WIDGET_KEYS["simulations"]: 321,
        app.SCENARIO_WIDGET_KEYS["seed"]: 654,
    }
    container = _SettingsContainer(calls, state)
    fake_streamlit = SimpleNamespace(
        session_state=state,
        popover=lambda *args, **kwargs: container,
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

    assert app._render_simulation_settings() == (321, 654)
    assert calls[0] == (
        "Number of simulations",
        {
            "min_value": 1,
            "value": 10_000,
            "step": 1,
            "key": app.SCENARIO_WIDGET_KEYS["simulations"],
        },
    )
    assert calls[1] == (
        "Random seed",
        {"step": 1, "key": app.SCENARIO_WIDGET_KEYS["seed"]},
    )


def test_shared_scenario_row_no_longer_contains_simulation_count_or_seed() -> None:
    from pathlib import Path

    source = Path("src/dnd_combat_simulator/ui/page.py").read_text()
    shared_block = source.split('st.subheader("Shared scenario")', 1)[1].split(
        "scenario = ScenarioConfig", 1
    )[0]

    assert '"Number of simulations"' not in shared_block
    assert '"Random seed"' not in shared_block
    assert '"Target Armor Class"' in shared_block
    assert '"Enemy Save Bonus"' in shared_block
    assert '"Number of rounds"' in shared_block
    assert '"Compare with another build"' in shared_block


def test_trigger_source_selectbox_uses_placeholder_for_missing_source(
    monkeypatch,
) -> None:
    import sys
    from types import SimpleNamespace

    from dnd_combat_simulator.simulation import AttackProfile, BuildConfig, TriggerType
    from dnd_combat_simulator.ui.inputs import _attack_profile_inputs
    from dnd_combat_simulator.ui.validation import validate_build_fields
    from dnd_combat_simulator.ui.widget_keys import profile_widget_key

    calls = []

    class Context:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class Column:
        def number_input(self, label, **kwargs):
            return kwargs.get("value", 1)

        def text_input(self, label, **kwargs):
            return kwargs.get("value", "")

        def selectbox(self, label, **kwargs):
            calls.append((label, kwargs))
            if label == "When":
                return "Another attack succeeds"
            return kwargs["options"][kwargs.get("index", 0)]

        def radio(self, label, **kwargs):
            return kwargs["options"][0]

    state = {
        "first-additional-attack-count": 1,
        profile_widget_key(
            "first-additional-1", "trigger_type"
        ): "Another attack succeeds",
        profile_widget_key("first-additional-1", "trigger_source_attack_id"): None,
    }
    col = Column()
    fake_streamlit = SimpleNamespace(
        session_state=state,
        selectbox=col.selectbox,
        text_input=col.text_input,
        number_input=col.number_input,
        radio=col.radio,
        columns=lambda spec, **kwargs: [
            col for _ in range(spec if isinstance(spec, int) else len(spec))
        ],
        expander=lambda *args, **kwargs: Context(),
        checkbox=lambda *args, **kwargs: False,
        warning=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

    profile = _attack_profile_inputs("first-additional-1", "Attack 2")

    trigger_after = next(kwargs for label, kwargs in calls if label == "What")
    assert trigger_after["options"][0] is None
    assert trigger_after["format_func"](None) == "Select an attack..."
    assert trigger_after["index"] == 0
    assert profile.trigger_source_attack_id is None

    build = BuildConfig(
        "Build A",
        5,
        "1d6",
        1,
        attack_profiles=(
            AttackProfile("Primary", 5, "1d6", 1, attack_id="first-primary"),
            AttackProfile(
                "Follow-up",
                5,
                "1d6",
                1,
                attack_id="first-additional-1",
                trigger_type=TriggerType.AFTER_SUCCESS,
            ),
        ),
    )
    errors = [
        error
        for error in validate_build_fields(build, prefix="first")
        if error.key
        == profile_widget_key("first-additional-1", "trigger_source_attack_id")
    ]
    assert [error.message for error in errors] == [
        "Select the attack that must succeed first."
    ]


def test_selecting_trigger_source_stores_stable_id_and_clears_error(
    monkeypatch,
) -> None:
    import sys
    from types import SimpleNamespace

    from dnd_combat_simulator.simulation import AttackProfile, BuildConfig, TriggerType
    from dnd_combat_simulator.ui.inputs import _attack_profile_inputs
    from dnd_combat_simulator.ui.validation import validate_build_fields
    from dnd_combat_simulator.ui.widget_keys import profile_widget_key

    class Context:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class Column:
        def number_input(self, label, **kwargs):
            return kwargs.get("value", 1)

        def text_input(self, label, **kwargs):
            return kwargs.get("value", "")

        def selectbox(self, label, **kwargs):
            if label == "When":
                return "Another attack succeeds"
            if label == "What":
                value = "first-primary"
                kwargs["key"] and state.__setitem__(kwargs["key"], value)
                return value
            return kwargs["options"][kwargs.get("index", 0)]

        def radio(self, label, **kwargs):
            return kwargs["options"][0]

    state = {"first-additional-attack-count": 1}
    col = Column()
    monkeypatch.setitem(
        sys.modules,
        "streamlit",
        SimpleNamespace(
            session_state=state,
            selectbox=col.selectbox,
            text_input=col.text_input,
            number_input=col.number_input,
            radio=col.radio,
            columns=lambda spec, **kwargs: [
                col for _ in range(spec if isinstance(spec, int) else len(spec))
            ],
            expander=lambda *args, **kwargs: Context(),
            checkbox=lambda *args, **kwargs: False,
            warning=lambda *args, **kwargs: None,
        ),
    )

    profile = _attack_profile_inputs("first-additional-1", "Attack 2")

    assert profile.trigger_source_attack_id == "first-primary"
    assert (
        state[profile_widget_key("first-additional-1", "trigger_source_attack_id")]
        == "first-primary"
    )
    build = BuildConfig(
        "Build A",
        5,
        "1d6",
        1,
        attack_profiles=(
            AttackProfile("Renamed Primary", 5, "1d6", 1, attack_id="first-primary"),
            AttackProfile(
                "Follow-up",
                5,
                "1d6",
                1,
                attack_id="first-additional-1",
                trigger_type=TriggerType.AFTER_SUCCESS,
                trigger_source_attack_id="first-primary",
            ),
        ),
    )
    assert validate_build_fields(build, prefix="first") == []


def test_saved_trigger_source_remains_selected_after_rerun_and_rename(
    monkeypatch,
) -> None:
    import sys
    from types import SimpleNamespace

    from dnd_combat_simulator.ui.inputs import _attack_profile_inputs
    from dnd_combat_simulator.ui.widget_keys import profile_widget_key

    calls = []

    class Context:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class Column:
        def number_input(self, label, **kwargs):
            return kwargs.get("value", 1)

        def text_input(self, label, **kwargs):
            return "New name" if label == "Attack name" else kwargs.get("value", "")

        def selectbox(self, label, **kwargs):
            calls.append((label, kwargs))
            if label == "When":
                return "Another attack succeeds"
            return kwargs["options"][kwargs.get("index", 0)]

        def radio(self, label, **kwargs):
            return kwargs["options"][0]

    state = {
        "first-additional-attack-count": 1,
        profile_widget_key("first-primary", "name"): "Renamed source",
        profile_widget_key(
            "first-additional-1", "trigger_source_attack_id"
        ): "first-primary",
    }
    col = Column()
    monkeypatch.setitem(
        sys.modules,
        "streamlit",
        SimpleNamespace(
            session_state=state,
            selectbox=col.selectbox,
            text_input=col.text_input,
            number_input=col.number_input,
            radio=col.radio,
            columns=lambda spec, **kwargs: [
                col for _ in range(spec if isinstance(spec, int) else len(spec))
            ],
            expander=lambda *args, **kwargs: Context(),
            checkbox=lambda *args, **kwargs: False,
            warning=lambda *args, **kwargs: None,
        ),
    )

    profile = _attack_profile_inputs("first-additional-1", "Attack 2")

    trigger_after = next(kwargs for label, kwargs in calls if label == "What")
    assert trigger_after["index"] == 1
    assert trigger_after["format_func"]("first-primary") == "Renamed source"
    assert profile.trigger_source_attack_id == "first-primary"


def test_trigger_source_options_exclude_current_later_and_show_no_eligible(
    monkeypatch,
) -> None:
    import sys
    from types import SimpleNamespace

    import ui_test_api as app

    from dnd_combat_simulator.ui.inputs import _attack_profile_inputs

    state = {"first-additional-attack-count": 2}
    monkeypatch.setitem(sys.modules, "streamlit", SimpleNamespace(session_state=state))

    assert app._trigger_source_options("first-additional-1") == [
        ("first-primary", "Attack 1"),
        ("first-additional-2", "Attack 3"),
    ]

    warnings = []

    class Context:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class Column:
        def number_input(self, label, **kwargs):
            return kwargs.get("value", 1)

        def text_input(self, label, **kwargs):
            return kwargs.get("value", "")

        def selectbox(self, label, **kwargs):
            return (
                "Another attack succeeds"
                if label == "When"
                else kwargs["options"][kwargs.get("index", 0)]
            )

        def radio(self, label, **kwargs):
            return kwargs["options"][0]

    col = Column()
    monkeypatch.setitem(
        sys.modules,
        "streamlit",
        SimpleNamespace(
            session_state={"first-additional-attack-count": 0},
            selectbox=col.selectbox,
            text_input=col.text_input,
            number_input=col.number_input,
            radio=col.radio,
            columns=lambda spec, **kwargs: [
                col for _ in range(spec if isinstance(spec, int) else len(spec))
            ],
            expander=lambda *args, **kwargs: Context(),
            checkbox=lambda *args, **kwargs: False,
            warning=lambda message, **kwargs: warnings.append(message),
        ),
    )

    profile = _attack_profile_inputs("first-primary", "Attack 1")
    assert profile.trigger_source_attack_id is None
    assert warnings == [
        "Add another attack to this build before configuring an attack trigger."
    ]


def test_selecting_sometimes_reveals_percentage_and_hides_what_frequency(monkeypatch):
    import sys
    from types import SimpleNamespace

    from dnd_combat_simulator.simulation import TriggerType
    from dnd_combat_simulator.ui.inputs import _attack_profile_inputs
    from dnd_combat_simulator.ui.widget_keys import profile_widget_key

    labels = []

    class Context:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class Column:
        def number_input(self, label, **kwargs):
            labels.append(label)
            return kwargs.get("value", 1)

        def text_input(self, label, **kwargs):
            labels.append(label)
            if label == "Percentage Chance":
                return "25"
            return kwargs.get("value", "")

        def selectbox(self, label, **kwargs):
            labels.append(label)
            if label == "When":
                return "Sometimes"
            return kwargs["options"][kwargs.get("index", 0)]

        def radio(self, label, **kwargs):
            labels.append(label)
            return kwargs["options"][0]

    col = Column()
    monkeypatch.setitem(
        sys.modules,
        "streamlit",
        SimpleNamespace(
            session_state={
                profile_widget_key("first-primary", "trigger_type"): "Sometimes"
            },
            selectbox=col.selectbox,
            text_input=col.text_input,
            number_input=col.number_input,
            radio=col.radio,
            columns=lambda spec, **kwargs: [
                col for _ in range(spec if isinstance(spec, int) else len(spec))
            ],
            expander=lambda *args, **kwargs: Context(),
            checkbox=lambda *args, **kwargs: False,
            caption=lambda *args, **kwargs: None,
        ),
    )

    profile = _attack_profile_inputs("first-primary", "Attack")

    assert profile.trigger_type is TriggerType.SOMETIMES
    assert profile.trigger_chance_percent == 25
    assert "Percentage Chance" in labels
    assert "What" not in labels
    assert "Frequency" not in labels


@pytest.mark.parametrize("percent", [1, 100])
def test_sometimes_validation_accepts_boundaries(percent):
    from dnd_combat_simulator.combat import ResolutionType
    from dnd_combat_simulator.simulation import AttackProfile, BuildConfig, TriggerType
    from dnd_combat_simulator.ui.validation import validate_build_fields

    build = BuildConfig(
        "Build",
        5,
        "1d4",
        1,
        attack_profiles=(
            AttackProfile(
                "Sometimes",
                None,
                "1",
                1,
                resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
                attack_id="a",
                trigger_type=TriggerType.SOMETIMES,
                trigger_chance_percent=percent,
            ),
        ),
    )

    assert not validate_build_fields(build, prefix="first")


@pytest.mark.parametrize("percent", [None, 0, -1, 101, "", "1.5", "abc"])
def test_sometimes_validation_rejects_invalid_percentage_values(percent):
    from dnd_combat_simulator.combat import ResolutionType
    from dnd_combat_simulator.simulation import AttackProfile, BuildConfig, TriggerType
    from dnd_combat_simulator.ui.validation import validate_build_fields
    from dnd_combat_simulator.ui.widget_keys import profile_widget_key

    build = BuildConfig(
        "Build",
        5,
        "1d4",
        1,
        attack_profiles=(
            AttackProfile(
                "Sometimes",
                None,
                "1",
                1,
                resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
                attack_id="a",
                trigger_type=TriggerType.SOMETIMES,
                trigger_chance_percent=percent,
            ),
        ),
    )

    errors = validate_build_fields(build, prefix="first")

    assert any(
        error.key == profile_widget_key("first-a", "trigger_chance_percent")
        for error in errors
    )


def test_trigger_settings_uses_stable_expander_key_without_button(monkeypatch) -> None:
    import sys
    from types import SimpleNamespace

    import ui_test_api as app

    calls = []

    class Context:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def expander(label, **kwargs):
        calls.append((label, kwargs))
        return Context()

    monkeypatch.setitem(
        sys.modules,
        "streamlit",
        SimpleNamespace(
            expander=expander,
            button=lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("trigger settings must not render a button")
            ),
        ),
    )

    with app._trigger_settings_expander("attack-id"):
        pass

    assert calls == [
        (
            "Trigger: Always",
            {"expanded": False, "key": app.trigger_expanded_state_key("attack-id")},
        )
    ]


def test_result_rows_difference_uses_higher_dpr_baseline_for_all_rows() -> None:
    from dnd_combat_simulator.simulation import BuildConfig, ScenarioConfig
    from dnd_combat_simulator.ui.results import _result_rows
    from dnd_combat_simulator.ui.run_control import (
        ComparisonInputs,
        run_comparison_from_inputs,
    )

    comparison = run_comparison_from_inputs(
        ComparisonInputs(
            first_build=BuildConfig("Build A", 20, "1d4", 2),
            second_build=BuildConfig("Build B", 20, "1d4+10", 1),
            scenario=ScenarioConfig(target_armor_class=1, rounds=1, simulations=2),
            seed=7,
        )
    )

    rows = _result_rows(comparison)
    label = "Difference (Build B − Build A)"
    assert rows[0][label] == "9.00"
    executions = next(
        row for row in rows if row["Metric"] == "Average attack executions per combat"
    )
    assert executions[label] == "1"


def test_result_rows_tied_dpr_uses_build_a_baseline() -> None:
    from dnd_combat_simulator.simulation import BuildConfig, ScenarioConfig
    from dnd_combat_simulator.ui.results import _result_rows
    from dnd_combat_simulator.ui.run_control import (
        ComparisonInputs,
        run_comparison_from_inputs,
    )

    comparison = run_comparison_from_inputs(
        ComparisonInputs(
            first_build=BuildConfig("Build A", 20, "1d4", 1),
            second_build=BuildConfig("Build B", 20, "1d4", 1),
            scenario=ScenarioConfig(target_armor_class=1, rounds=1, simulations=2),
            seed=7,
        )
    )

    rows = _result_rows(comparison)
    assert "Difference (Build A − Build B)" in rows[0]
    assert rows[0]["Difference (Build A − Build B)"] == "0.00"


def test_profile_breakdown_trigger_summaries_and_no_automatic_column() -> None:
    from dnd_combat_simulator.combat import ResolutionType
    from dnd_combat_simulator.simulation import (
        AttackProfile,
        BuildConfig,
        ScenarioConfig,
        TriggerType,
        simulate_build,
    )
    from dnd_combat_simulator.ui.results import _profile_breakdown_rows

    source = AttackProfile("Source", 20, "1", 1, attack_id="src")
    attack_trigger = AttackProfile(
        "Followup",
        20,
        "1",
        1,
        attack_id="hit",
        trigger_type=TriggerType.AFTER_SUCCESS,
        trigger_source_attack_id="src",
    )
    sometimes = AttackProfile(
        "Sometimes",
        None,
        "1",
        1,
        resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
        attack_id="sometimes",
        trigger_type=TriggerType.SOMETIMES,
        trigger_chance_percent=100,
    )
    result = simulate_build(
        BuildConfig(
            "Build", 20, "1", 1, attack_profiles=(source, attack_trigger, sometimes)
        ),
        ScenarioConfig(target_armor_class=1, rounds=1, simulations=1),
        seed=1,
    )

    rows = _profile_breakdown_rows(result)
    assert rows[0]["Trigger"] == "Executes normally each round."
    assert rows[1]["Trigger"] == "Triggered 1 times per combat after Source hits."
    assert (
        rows[2]["Trigger"]
        == "Triggered 1 times per combat from a 100% once-per-round chance."
    )
    assert "source" not in rows[2]["Trigger"].lower()
    assert all(
        "Average automatic damage applications per combat" not in row for row in rows
    )


def test_result_rows_build_a_higher_dpr_uses_build_a_baseline() -> None:
    from dnd_combat_simulator.simulation import BuildConfig, ScenarioConfig
    from dnd_combat_simulator.ui.results import _result_rows
    from dnd_combat_simulator.ui.run_control import (
        ComparisonInputs,
        run_comparison_from_inputs,
    )

    comparison = run_comparison_from_inputs(
        ComparisonInputs(
            first_build=BuildConfig("Build A", 20, "1d4+1", 1),
            second_build=BuildConfig("Build B", 20, "1d4", 1),
            scenario=ScenarioConfig(target_armor_class=1, rounds=1, simulations=2),
            seed=7,
        )
    )

    rows = _result_rows(comparison)
    assert rows[0]["Difference (Build A − Build B)"] == "1.00"


@pytest.mark.parametrize(
    ("first_profile", "second_profile", "expected_label"),
    [
        # Build A has higher DPR but lower expected damage per target resolution.
        (
            {"damage_dice": "1", "affected_targets": 2},
            {"damage_dice": "1d2", "affected_targets": 1},
            "Difference (Build A − Build B)",
        ),
        # Build B has higher DPR but lower expected damage per target resolution.
        (
            {"damage_dice": "1d2", "affected_targets": 1},
            {"damage_dice": "1", "affected_targets": 2},
            "Difference (Build B − Build A)",
        ),
    ],
)
def test_result_rows_use_nonnegative_comparison_difference_for_target_resolution(
    first_profile: dict[str, int | str],
    second_profile: dict[str, int | str],
    expected_label: str,
) -> None:
    from dnd_combat_simulator.combat import ResolutionType
    from dnd_combat_simulator.simulation import (
        AttackProfile,
        BuildConfig,
        ScenarioConfig,
        compare_builds,
    )
    from dnd_combat_simulator.ui.results import _result_rows

    first = AttackProfile(
        "Build A profile",
        None,
        str(first_profile["damage_dice"]),
        1,
        resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
        affected_targets=int(first_profile["affected_targets"]),
    )
    second = AttackProfile(
        "Build B profile",
        None,
        str(second_profile["damage_dice"]),
        1,
        resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
        affected_targets=int(second_profile["affected_targets"]),
    )
    comparison = compare_builds(
        first_build=BuildConfig("Build A", 0, "1", 1, attack_profiles=(first,)),
        second_build=BuildConfig("Build B", 0, "1", 1, attack_profiles=(second,)),
        scenario=ScenarioConfig(target_armor_class=10, rounds=1, simulations=2),
        seed=7,
    )

    rows = _result_rows(comparison)
    target_row = next(
        row for row in rows if row["Metric"] == "Expected damage per target resolution"
    )

    assert expected_label in target_row
    assert target_row[expected_label] == "0.50"
    assert "-" not in target_row[expected_label]


def test_result_rows_tied_dpr_keeps_build_a_first_and_nonnegative_differences() -> None:
    from dnd_combat_simulator.simulation import (
        BuildConfig,
        ScenarioConfig,
        compare_builds,
    )
    from dnd_combat_simulator.ui.results import _result_rows

    comparison = compare_builds(
        first_build=BuildConfig("Build A", 20, "1d4", 1),
        second_build=BuildConfig("Build B", 20, "1d4", 1),
        scenario=ScenarioConfig(target_armor_class=1, rounds=1, simulations=2),
        seed=7,
    )

    rows = _result_rows(comparison)
    label = "Difference (Build A − Build B)"

    assert label in rows[0]
    assert all("-" not in row[label] for row in rows if row[label] != "—")


def test_result_rows_all_numeric_differences_are_nonnegative() -> None:
    from dnd_combat_simulator.combat import ResolutionType
    from dnd_combat_simulator.simulation import (
        AttackProfile,
        BuildConfig,
        ScenarioConfig,
        compare_builds,
    )
    from dnd_combat_simulator.ui.results import _result_rows

    first = AttackProfile(
        "Build A profile",
        None,
        "1",
        1,
        resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
        affected_targets=2,
    )
    second = AttackProfile(
        "Build B profile",
        None,
        "1d2",
        1,
        resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
        affected_targets=1,
    )
    comparison = compare_builds(
        first_build=BuildConfig("Build A", 0, "1", 1, attack_profiles=(first,)),
        second_build=BuildConfig("Build B", 0, "1", 1, attack_profiles=(second,)),
        scenario=ScenarioConfig(target_armor_class=10, rounds=2, simulations=2),
        seed=7,
    )

    rows = _result_rows(comparison)
    label = "Difference (Build A − Build B)"

    assert all("-" not in row[label] for row in rows if row[label] != "—")


def test_stable_id_build_from_state_reconstructs_widget_prefixed_values(
    monkeypatch,
) -> None:
    import sys
    from types import SimpleNamespace

    import ui_test_api as app

    from dnd_combat_simulator.combat import AttackFeature, ResolutionType
    from dnd_combat_simulator.simulation import TriggerFrequency, TriggerType

    a1 = "attack-shared"
    a2 = "attack-second"
    wp1 = app.attack_widget_prefix("first", a1)
    wp2 = app.attack_widget_prefix("first", a2)
    state = {
        "first-build-name": "Stable Build",
        app.build_attack_ids_key("first"): [a2, a1],
        app.profile_widget_key(wp1, "name"): "Source",
        app.profile_widget_key(wp1, "resolution_type"): "Saving Throw",
        app.profile_widget_key(wp1, "save_dc"): 15,
        app.profile_widget_key(wp1, "successful_save_damage"): "Half damage",
        app.profile_widget_key(wp1, "damage_formula"): "2d6",
        app.profile_widget_key(wp1, "attacks_per_round"): 2,
        app.profile_widget_key(wp1, "affected_targets"): 3,
        app.profile_widget_key(wp1, "active_rounds"): "1-2",
        app.feature_widget_key(wp1, AttackFeature.POTENT_CANTRIP): True,
        app.profile_widget_key(wp2, "name"): "Dependent",
        app.profile_widget_key(wp2, "resolution_type"): "Attack Roll",
        app.profile_widget_key(wp2, "attack_bonus"): 7,
        app.profile_widget_key(wp2, "damage_formula"): "1d8+4",
        app.profile_widget_key(wp2, "attacks_per_round"): 1,
        app.profile_widget_key(wp2, "affected_targets"): 1,
        app.profile_widget_key(wp2, "attack_roll_mode"): "Advantage",
        app.profile_widget_key(wp2, "trigger_type"): "Another attack succeeds",
        app.profile_widget_key(wp2, "trigger_source_attack_id"): a1,
        app.profile_widget_key(wp2, "trigger_frequency"): "Once per combat",
        app.profile_widget_key(wp2, "resource_enabled"): True,
        app.profile_widget_key(wp2, "resource_id"): "resource-a",
        app.profile_widget_key(wp2, "resource_amount"): 2,
    }
    monkeypatch.setitem(sys.modules, "streamlit", SimpleNamespace(session_state=state))

    build = app._build_from_state("first", "Build A")

    assert [profile.attack_id for profile in build.attack_profiles] == [a2, a1]
    dependent, source = build.attack_profiles
    assert dependent.name == "Dependent"
    assert dependent.attack_bonus == 7
    assert dependent.attack_roll_mode.value == "advantage"
    assert dependent.trigger_type is TriggerType.AFTER_SUCCESS
    assert dependent.trigger_source_attack_id == a1
    assert dependent.trigger_frequency is TriggerFrequency.ONCE_PER_COMBAT
    assert dependent.resource_costs[0].resource_id == "resource-a"
    assert source.name == "Source"
    assert source.resolution_type is ResolutionType.SAVING_THROW
    assert source.save_dc == 15
    assert source.active_rounds == "1-2"
    assert AttackFeature.POTENT_CANTRIP in source.features


def test_delete_attack_state_is_build_scoped_for_matching_domain_ids(
    monkeypatch,
) -> None:
    import sys
    from types import SimpleNamespace

    import ui_test_api as app

    attack_id = "attack-same"
    first_prefix = app.attack_widget_prefix("first", attack_id)
    second_prefix = app.attack_widget_prefix("second", attack_id)
    state = {
        app.profile_widget_key(first_prefix, "name"): "First",
        app.profile_widget_key(second_prefix, "name"): "Second",
        f"{first_prefix}-resource-expanded": True,
        f"{second_prefix}-resource-expanded": True,
    }
    monkeypatch.setitem(sys.modules, "streamlit", SimpleNamespace(session_state=state))

    app._delete_attack_state(state, "first", attack_id)

    assert app.profile_widget_key(first_prefix, "name") not in state
    assert f"{first_prefix}-resource-expanded" not in state
    assert state[app.profile_widget_key(second_prefix, "name")] == "Second"
    assert state[f"{second_prefix}-resource-expanded"] is True


def test_trigger_options_use_domain_ids_and_build_scoped_names(monkeypatch) -> None:
    import sys
    from types import SimpleNamespace

    import ui_test_api as app

    source = "attack-shared"
    current = "attack-current"
    other_build_same = app.attack_widget_prefix("second", source)
    state = {
        app.build_attack_ids_key("first"): [current, source],
        app.build_attack_ids_key("second"): [source],
        app.profile_widget_key(
            app.attack_widget_prefix("first", source), "name"
        ): "Renamed Source",
        app.profile_widget_key(other_build_same, "name"): "Wrong Build",
    }
    monkeypatch.setitem(sys.modules, "streamlit", SimpleNamespace(session_state=state))

    assert app._trigger_source_options("first", current) == [(source, "Renamed Source")]


def test_resource_helpers_use_widget_prefixes_for_each_build(monkeypatch) -> None:
    import sys
    from types import SimpleNamespace

    import ui_test_api as app

    attack_id = "attack-same"
    first_prefix = app.attack_widget_prefix("first", attack_id)
    second_prefix = app.attack_widget_prefix("second", attack_id)
    state = {
        app.build_attack_ids_key("first"): [attack_id],
        app.build_attack_ids_key("second"): [attack_id],
        app.profile_widget_key(first_prefix, "name"): "First Attack",
        app.profile_widget_key(first_prefix, "resource_enabled"): True,
        app.profile_widget_key(first_prefix, "resource_id"): "resource-x",
        app.profile_widget_key(second_prefix, "name"): "Second Attack",
        app.profile_widget_key(second_prefix, "resource_enabled"): True,
        app.profile_widget_key(second_prefix, "resource_id"): "resource-x",
    }
    monkeypatch.setitem(sys.modules, "streamlit", SimpleNamespace(session_state=state))

    assert app._resource_usage_profile_keys("resource-x") == [
        "First Attack",
        "Second Attack",
    ]
    app._clear_resource_from_profiles("resource-x")
    assert state[app.profile_widget_key(first_prefix, "resource_id")] == ""
    assert state[app.profile_widget_key(second_prefix, "resource_id")] == ""


def test_next_default_attack_name_ignores_order_and_existing_case() -> None:
    from dnd_combat_simulator.ui.state import next_default_attack_name

    assert next_default_attack_name(["Attack 2", "attack 1"]) == "Attack 3"
    assert next_default_attack_name(["Custom", "Attack 1"]) == "Attack 2"


def test_attack_action_toolbar_uses_single_horizontal_tertiary_container(
    monkeypatch,
) -> None:
    import sys
    from types import SimpleNamespace

    import ui_test_api as app

    calls = []

    class Context:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeContainer(Context):
        def __init__(self, key=None):
            self.key = key

        def button(self, label, **kwargs):
            calls.append(("toolbar_button", self.key, label, kwargs))
            return False

        def number_input(self, label, **kwargs):
            return kwargs.get("value", 1)

        def text_input(self, label, **kwargs):
            return kwargs.get("value", "")

        def selectbox(self, label, **kwargs):
            return kwargs["options"][kwargs.get("index", 0)]

        def radio(self, label, **kwargs):
            return kwargs["options"][0]

    def container(**kwargs):
        calls.append(("container", kwargs))
        return FakeContainer(kwargs.get("key"))

    def columns(spec, **kwargs):
        calls.append(("columns", {"spec": spec, **kwargs}))
        return [
            FakeContainer() for _ in range(spec if isinstance(spec, int) else len(spec))
        ]

    state = {
        app.build_attack_ids_key("first"): ["attack-a", "attack-b"],
        app.profile_widget_key(
            app.attack_widget_prefix("first", "attack-a"), "name"
        ): "Slash",
        app.profile_widget_key(
            app.attack_widget_prefix("first", "attack-b"), "name"
        ): "Stab",
    }
    fake_streamlit = SimpleNamespace(
        session_state=state,
        container=container,
        columns=columns,
        markdown=lambda *args, **kwargs: None,
        text_input=lambda label, **kwargs: kwargs.get("value", ""),
        number_input=lambda label, **kwargs: kwargs.get("value", 1),
        selectbox=lambda label, **kwargs: kwargs["options"][kwargs.get("index", 0)],
        radio=lambda label, **kwargs: kwargs["options"][0],
        checkbox=lambda *args, **kwargs: False,
        expander=lambda *args, **kwargs: Context(),
        button=lambda *args, **kwargs: False,
        caption=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        rerun=lambda: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

    app._build_inputs("first", "Build A")

    toolbar_containers = [
        call[1]
        for call in calls
        if call[0] == "container" and str(call[1].get("key", "")).endswith("-toolbar")
    ]
    assert toolbar_containers == [
        {
            "key": "first-attack-a-toolbar",
            "border": True,
            "width": "content",
            "horizontal": True,
            "vertical_alignment": "center",
            "gap": "xsmall",
        },
        {
            "key": "first-attack-b-toolbar",
            "border": True,
            "width": "content",
            "horizontal": True,
            "vertical_alignment": "center",
            "gap": "xsmall",
        },
    ]
    toolbar_buttons = [call for call in calls if call[0] == "toolbar_button"]
    assert len(toolbar_buttons) == 8
    assert [call[2] for call in toolbar_buttons[:4]] == [
        ":material/content_copy:",
        ":material/arrow_upward:",
        ":material/arrow_downward:",
        ":material/delete:",
    ]
    assert all(call[3]["type"] == "tertiary" for call in toolbar_buttons)
    assert all(call[3]["width"] == "content" for call in toolbar_buttons)
    assert all(call[3]["type"] != "secondary" for call in toolbar_buttons)
    assert [call[3]["help"] for call in toolbar_buttons[:4]] == [
        "Duplicate Slash.",
        "This attack is already first.",
        "Move Slash down.",
        "Delete Slash. Requires confirmation.",
    ]
    assert [call[3]["disabled"] for call in toolbar_buttons[:4]] == [
        False,
        True,
        False,
        False,
    ]
    assert [call[3]["disabled"] for call in toolbar_buttons[4:]] == [
        False,
        False,
        True,
        False,
    ]
    assert not any(
        call[0] == "columns" and call[1]["spec"] == [0.18, 0.18, 0.18, 0.18, 1.0]
        for call in calls
    )


def test_attack_toolbar_delete_opens_existing_confirmation(monkeypatch) -> None:
    import sys
    from types import SimpleNamespace

    from dnd_combat_simulator.ui.constants import ATTACK_DELETE_CONFIRMATION_KEY
    from dnd_combat_simulator.ui.inputs import _build_inputs
    from dnd_combat_simulator.ui.widget_keys import build_attack_ids_key

    class Context:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeContainer(Context):
        def __init__(self, key=None):
            self.key = key

        def button(self, label, **kwargs):
            return kwargs["key"] == "first-attack-a-delete"

        def number_input(self, label, **kwargs):
            return kwargs.get("value", 1)

        def text_input(self, label, **kwargs):
            return kwargs.get("value", "")

        def selectbox(self, label, **kwargs):
            return kwargs["options"][kwargs.get("index", 0)]

        def radio(self, label, **kwargs):
            return kwargs["options"][0]

    state = {build_attack_ids_key("first"): ["attack-a", "attack-b"]}
    fake_streamlit = SimpleNamespace(
        session_state=state,
        container=lambda **kwargs: FakeContainer(kwargs.get("key")),
        columns=lambda spec, **kwargs: [
            FakeContainer() for _ in range(spec if isinstance(spec, int) else len(spec))
        ],
        markdown=lambda *args, **kwargs: None,
        text_input=lambda label, **kwargs: kwargs.get("value", ""),
        number_input=lambda label, **kwargs: kwargs.get("value", 1),
        selectbox=lambda label, **kwargs: kwargs["options"][kwargs.get("index", 0)],
        radio=lambda label, **kwargs: kwargs["options"][0],
        checkbox=lambda *args, **kwargs: False,
        expander=lambda *args, **kwargs: Context(),
        button=lambda *args, **kwargs: False,
        caption=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        rerun=lambda: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

    _build_inputs("first", "Build A")

    assert state[ATTACK_DELETE_CONFIRMATION_KEY] == "first:attack-a"
    assert state[build_attack_ids_key("first")] == ["attack-a", "attack-b"]


def test_build_inputs_uses_attack_name_input_without_markdown_heading(
    monkeypatch,
) -> None:
    import sys
    from types import SimpleNamespace

    from dnd_combat_simulator.ui.inputs import _build_inputs
    from dnd_combat_simulator.ui.widget_keys import (
        attack_widget_prefix,
        build_attack_ids_key,
        profile_widget_key,
    )

    class Context:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeContainer(Context):
        def button(self, *args, **kwargs):
            return False

        def number_input(self, label, **kwargs):
            return kwargs.get("value", 1)

        def text_input(self, label, **kwargs):
            return kwargs.get("value", "")

        def selectbox(self, label, **kwargs):
            return kwargs["options"][kwargs.get("index", 0)]

        def radio(self, label, **kwargs):
            return kwargs["options"][0]

    markdown_calls: list[str] = []
    text_input_calls: list[tuple[str, dict[str, object]]] = []
    state = {
        build_attack_ids_key("first"): ["attack-a"],
        profile_widget_key(attack_widget_prefix("first", "attack-a"), "name"): "Slash",
    }

    def markdown(body: str, **kwargs: object) -> None:
        markdown_calls.append(body)

    def text_input(label: str, **kwargs: object) -> str:
        text_input_calls.append((label, kwargs))
        return str(kwargs.get("value", ""))

    fake_streamlit = SimpleNamespace(
        session_state=state,
        container=lambda **kwargs: FakeContainer(),
        columns=lambda spec, **kwargs: [
            FakeContainer() for _ in range(spec if isinstance(spec, int) else len(spec))
        ],
        markdown=markdown,
        text_input=text_input,
        number_input=lambda label, **kwargs: kwargs.get("value", 1),
        selectbox=lambda label, **kwargs: kwargs["options"][kwargs.get("index", 0)],
        radio=lambda label, **kwargs: kwargs["options"][0],
        checkbox=lambda *args, **kwargs: False,
        expander=lambda *args, **kwargs: Context(),
        button=lambda *args, **kwargs: False,
        caption=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        rerun=lambda: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

    _build_inputs("first", "Build A")

    assert "##### Slash" not in markdown_calls
    attack_name_inputs = [
        kwargs for label, kwargs in text_input_calls if label == "Attack name"
    ]
    assert len(attack_name_inputs) == 1
    assert attack_name_inputs[0]["key"] == profile_widget_key(
        attack_widget_prefix("first", "attack-a"), "name"
    )
    assert "value" not in attack_name_inputs[0]


def test_copy_attack_widget_state_uses_persistent_allowlist_only() -> None:
    import ui_test_api as app

    from dnd_combat_simulator.combat import AttackFeature

    source = app.attack_widget_prefix("first", "attack-source")
    dest = app.attack_widget_prefix("first", "attack-dest")
    state = {}
    expected_dest_keys = set()
    for field in app.ATTACK_WIDGET_STATE_FIELDS:
        source_key = app.profile_widget_key(source, field)
        state[source_key] = f"value-{field}"
        expected_dest_keys.add(app.profile_widget_key(dest, field))
    for feature in AttackFeature:
        source_key = app.feature_widget_key(source, feature)
        state[source_key] = True
        expected_dest_keys.add(app.feature_widget_key(dest, feature))
    for suffix in (
        "duplicate",
        "up",
        "down",
        "delete",
        "toolbar",
        "confirm-delete",
        "cancel-delete",
    ):
        state[f"{source}-{suffix}"] = True
    state[app.ATTACK_DELETE_CONFIRMATION_KEY] = "first:attack-source"
    state[app.SIMULATION_RUNNING_KEY] = True
    state[app.GENERATED_SHARE_URL_KEY] = "https://example.invalid/share"
    state[app.trigger_expanded_state_key(source)] = True
    state[f"{source}-features-expanded"] = True
    state[f"{source}-resource-expanded"] = True
    expected_dest_keys.update(
        {
            app.trigger_expanded_state_key(dest),
            f"{dest}-features-expanded",
            f"{dest}-resource-expanded",
        }
    )

    app._copy_attack_widget_state(state, source, dest)

    assert expected_dest_keys <= set(state)
    assert not any(
        transient in state
        for transient in (
            f"{dest}-duplicate",
            f"{dest}-up",
            f"{dest}-down",
            f"{dest}-delete",
            f"{dest}-toolbar",
            f"{dest}-confirm-delete",
            f"{dest}-cancel-delete",
        )
    )


def test_duplicate_state_resets_self_trigger_and_copies_advanced_fields() -> None:
    import ui_test_api as app

    from dnd_combat_simulator.combat import AttackFeature

    source_id = "attack-source"
    dest_id = "attack-dest"
    source = app.attack_widget_prefix("first", source_id)
    dest = app.attack_widget_prefix("first", dest_id)
    state = {
        app.profile_widget_key(source, "name"): "Smite",
        app.profile_widget_key(source, "resolution_type"): "Saving Throw",
        app.profile_widget_key(source, "save_dc"): 17,
        app.profile_widget_key(source, "successful_save_damage"): "Half damage",
        app.profile_widget_key(source, "damage_formula"): "4d8+3",
        app.profile_widget_key(source, "attacks_per_round"): 2,
        app.profile_widget_key(source, "active_rounds"): "1, 3-4",
        app.profile_widget_key(source, "trigger_type"): "Another attack succeeds",
        app.profile_widget_key(source, "trigger_source_attack_id"): source_id,
        app.profile_widget_key(source, "trigger_frequency"): "Once per combat",
        app.profile_widget_key(source, "trigger_chance_percent"): "75",
        app.profile_widget_key(source, "resource_enabled"): True,
        app.profile_widget_key(source, "resource_id"): "resource-1",
        app.profile_widget_key(source, "resource_amount"): 2,
        app.feature_widget_key(source, AttackFeature.GREAT_WEAPON_FIGHTING): True,
        app.feature_widget_key(source, AttackFeature.TAVERN_BRAWLER): True,
        app.trigger_expanded_state_key(source): True,
        f"{source}-resource-expanded": True,
        f"{source}-duplicate": True,
    }

    copied = app._duplicate_attack_state(
        state,
        source,
        dest,
        source_attack_id=source_id,
        dest_attack_id=dest_id,
    )

    assert copied[app.profile_widget_key(dest, "name")] == "Smite copy"
    assert copied[app.profile_widget_key(dest, "resolution_type")] == "Saving Throw"
    assert copied[app.profile_widget_key(dest, "resource_id")] == "resource-1"
    assert (
        copied[app.feature_widget_key(dest, AttackFeature.GREAT_WEAPON_FIGHTING)]
        is True
    )
    assert copied[app.feature_widget_key(dest, AttackFeature.TAVERN_BRAWLER)] is True
    assert copied[app.trigger_expanded_state_key(dest)] is True
    assert copied[f"{dest}-resource-expanded"] is True
    assert copied[app.profile_widget_key(dest, "trigger_type")] == "Always"
    assert copied[app.profile_widget_key(dest, "trigger_source_attack_id")] is None
    assert (
        copied[app.profile_widget_key(dest, "trigger_frequency")]
        == "Every successful resolution"
    )
    assert f"{dest}-duplicate" not in copied


def test_empty_attack_ids_are_build_scoped_validation_errors() -> None:
    from dnd_combat_simulator.simulation import AttackProfile, BuildConfig
    from dnd_combat_simulator.ui.validation import validate_build_fields

    build = BuildConfig(
        name="Build B",
        attack_bonus=5,
        damage_dice="1d8",
        attacks_per_round=1,
        attack_profiles=(
            AttackProfile(
                name="Broken",
                attack_bonus=5,
                damage_dice="1d8",
                attacks_per_round=1,
                attack_id="",
            ),
        ),
    )

    errors = validate_build_fields(build, prefix="second")

    assert any(error.key == "second-attack-ids" for error in errors)
    assert any(
        "Build B contains an empty attack ID" in error.message for error in errors
    )


def test_attack_toolbar_css_is_scoped_and_compact() -> None:
    import ui_test_api as app

    css = app.ATTACK_TOOLBAR_CSS

    assert '[class*="st-key-first-attack-"][class*="-toolbar"]' in css
    assert '[class*="st-key-second-attack-"][class*="-toolbar"]' in css
    assert '[class$="-toolbar"]' not in css
    assert '[data-testid="stVerticalBlockBorderWrapper"]' in css
    assert '[data-testid="stVerticalBlock"]' in css
    assert '[data-testid="stHorizontalBlock"]' in css
    assert "padding: 2px 4px" in css
    assert "padding: 0" in css
    assert "height: 36px" in css
    assert "max-height: 36px" in css
    assert 'button[kind="tertiary"]' in css
    assert "min-height" not in css
    assert "padding-top: 0" in css
    assert "padding-bottom: 0" in css
    assert "focus-visible" in css
    assert "disabled styling" in css
    assert "tooltips" in css
    assert "Confirm Delete" not in css
    assert '\nbutton[kind="tertiary"]' not in css
    assert "configuration-toolbar" not in css


def test_streamlit_duplicate_button_copies_persistent_state_without_exceptions() -> (
    None
):
    import ui_test_api as app
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("src/dnd_combat_simulator/app.py", default_timeout=10)
    at.run()
    assert not at.exception
    source_id = at.session_state[app.build_attack_ids_key("first")][0]
    source_prefix = app.attack_widget_prefix("first", source_id)
    at.session_state[app.profile_widget_key(source_prefix, "name")] = "Blade"
    at.session_state[app.profile_widget_key(source_prefix, "damage_formula")] = "2d6+4"
    at.session_state[app.profile_widget_key(source_prefix, "attacks_per_round")] = 3
    at.run()
    duplicate_button = next(
        button for button in at.button if button.key == f"{source_prefix}-duplicate"
    )
    duplicate_button.click()
    at.run()

    assert not at.exception
    ids = at.session_state[app.build_attack_ids_key("first")]
    assert len(ids) == 2
    assert ids[0] == source_id
    assert ids[1] != source_id
    dest_prefix = app.attack_widget_prefix("first", ids[1])
    assert at.session_state[app.profile_widget_key(dest_prefix, "name")] == "Blade copy"
    assert (
        at.session_state[app.profile_widget_key(dest_prefix, "damage_formula")]
        == "2d6+4"
    )
    assert (
        at.session_state[app.profile_widget_key(dest_prefix, "attacks_per_round")] == 3
    )
    new_session_state = at.session_state._state._new_session_state
    assert f"{dest_prefix}-duplicate" not in new_session_state
    assert f"{dest_prefix}-toolbar" not in new_session_state


def test_stage42_build_math_keys_and_state_round_trip(monkeypatch) -> None:
    from dnd_combat_simulator.build_math import BuildMathDefaults
    from dnd_combat_simulator.sharing import (
        deserialize_shared_configuration,
        serialize_shared_configuration,
        shared_configuration_from_configs,
    )
    from dnd_combat_simulator.simulation import BuildConfig, ScenarioConfig
    from dnd_combat_simulator.ui.state import (
        _build_from_state,
        _build_math_defaults_from_state,
        hydrate_session_state_from_shared_configuration,
    )
    from dnd_combat_simulator.ui.widget_keys import build_math_state_key

    assert (
        build_math_state_key("first", "ability_modifier")
        == "first-build-math-ability-modifier"
    )
    with pytest.raises(KeyError):
        build_math_state_key("first", "unknown")

    class FakeStreamlit:
        session_state = {}

    monkeypatch.setitem(sys.modules, "streamlit", FakeStreamlit)
    assert _build_math_defaults_from_state({}, "first") == BuildMathDefaults()

    first_defaults = BuildMathDefaults(5, 4, 2, 3, 1)
    second_defaults = BuildMathDefaults(-1, 0, -2, -3, -4)
    shared = shared_configuration_from_configs(
        compare_enabled=True,
        scenario=ScenarioConfig(15, 2, 3),
        seed=9,
        build_a=BuildConfig("A", 5, "1d8", 1, math_defaults=first_defaults),
        build_b=BuildConfig("B", 6, "1d6", 1, math_defaults=second_defaults),
    )
    hydrate_session_state_from_shared_configuration(FakeStreamlit.session_state, shared)
    assert _build_from_state("first", "Build A").math_defaults == first_defaults
    assert _build_from_state("second", "Build B").math_defaults == second_defaults

    reshared = shared_configuration_from_configs(
        compare_enabled=True,
        scenario=ScenarioConfig(15, 2, 3),
        seed=9,
        build_a=_build_from_state("first", "Build A"),
        build_b=_build_from_state("second", "Build B"),
    )
    rerestored = deserialize_shared_configuration(
        serialize_shared_configuration(reshared)
    )
    assert rerestored.build_a.math_defaults == first_defaults
    assert rerestored.build_b.math_defaults == second_defaults
    assert rerestored.build_a.math_defaults != rerestored.build_b.math_defaults


def test_stage4_build_math_controls_are_not_rendered() -> None:
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("src/dnd_combat_simulator/app.py").run(timeout=10)
    assert not at.exception
    text = "\n".join(str(node.value) for node in at.text)
    assert any(title.value == APP_TITLE for title in at.title)
    assert any(button.label == "Run Simulation" for button in at.button)
    forbidden = (
        "Ability modifier",
        "Proficiency bonus",
        "Other attack bonus",
        "Other damage bonus",
        "Other Save DC bonus",
        "Calculated attack bonus",
        "Calculated damage modifier",
        "Calculated Save DC",
        "Use Build Attack Bonus",
        "Use Build Save DC",
        "Use Build Damage Modifier",
    )
    assert all(label not in text for label in forbidden)
