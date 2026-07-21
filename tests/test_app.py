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


def test_damage_formula_help_uses_markdown_lists() -> None:
    from dnd_combat_simulator.app import DAMAGE_FORMULA_HELP

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
    ]
    lines = DAMAGE_FORMULA_HELP.splitlines()

    for example in examples:
        matches = [line for line in lines if f"`{example}`" in line]
        assert len(matches) == 1
        assert matches[0].startswith(f"- `{example}`")


def test_damage_formula_input_keeps_streamlit_help_icon(monkeypatch) -> None:
    import sys
    from types import SimpleNamespace

    from dnd_combat_simulator.app import DAMAGE_FORMULA_HELP, _attack_profile_inputs

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


def test_profile_contribution_data_keeps_order_and_automatic_profiles() -> None:
    from dnd_combat_simulator.app import _profile_contribution_chart_data

    build, result = _mixed_profile_result()

    rows = _profile_contribution_chart_data(result, build.name)

    assert [row["Profile"] for row in rows] == ["Zero opener", "Save effect", "Aura"]
    assert [row["Order"] for row in rows] == [1, 2, 3]
    assert rows[2]["Resolution type"] == "Automatic Damage"


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


def test_feature_expander_is_collapsed_and_uses_helpful_stable_checkbox_keys(
    monkeypatch,
) -> None:
    import sys
    from types import SimpleNamespace

    from dnd_combat_simulator.app import FEATURE_HELP, _attack_profile_inputs
    from dnd_combat_simulator.combat import AttackFeature

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

    fake_streamlit = SimpleNamespace(
        selectbox=col.selectbox,
        text_input=col.text_input,
        number_input=col.number_input,
        columns=lambda spec, **kwargs: [col for _ in range(spec)],
        expander=expander,
        checkbox=checkbox,
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

    profile = _attack_profile_inputs("first-primary", "Attack")

    assert profile.features == frozenset({AttackFeature.GREAT_WEAPON_FIGHTING})
    assert ("expander", {"label": "Feats and Features", "expanded": False}) in calls
    checkbox_calls = [call for kind, call in calls if kind == "checkbox"]
    assert [call["label"] for call in checkbox_calls] == [
        "Elven Accuracy",
        "Great Weapon Fighting",
        "Tavern Brawler",
        "Stop on Miss",
    ]
    assert checkbox_calls[0]["key"] == "first-primary-feature-elven_accuracy"
    assert checkbox_calls[0]["help"] == FEATURE_HELP[AttackFeature.ELVEN_ACCURACY]
    assert checkbox_calls[3]["key"] == "first-primary-feature-stop_on_miss"
    assert checkbox_calls[3]["help"] == FEATURE_HELP[AttackFeature.STOP_ON_MISS]
    assert checkbox_calls[3]["disabled"] is False


def test_profile_breakdown_rows_include_formatted_features() -> None:
    from dnd_combat_simulator.app import (
        SingleBuildInputs,
        _profile_breakdown_rows,
        run_single_build_from_inputs,
    )
    from dnd_combat_simulator.combat import AttackFeature
    from dnd_combat_simulator.simulation import (
        AttackProfile,
        BuildConfig,
        ScenarioConfig,
    )

    result = run_single_build_from_inputs(
        SingleBuildInputs(
            build=BuildConfig(
                "Features",
                20,
                "1d4",
                1,
                attack_profiles=(
                    AttackProfile("Plain", 20, "1d4", 1),
                    AttackProfile(
                        "Featured",
                        20,
                        "1d4",
                        1,
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

    from dnd_combat_simulator.app import _profile_contribution_chart_data

    build, result = _mixed_profile_result()

    rows = _profile_contribution_chart_data(result, build.name)

    assert [row["Profile"] for row in rows] == ["Zero opener", "Save effect", "Aura"]
    assert sum(row["Damage per Round contribution"] for row in rows) == pytest.approx(
        result.average_damage_per_round
    )
    assert sum(row["Contribution percentage"] for row in rows) == pytest.approx(100)


def test_profile_contribution_percentages_zero_when_dpr_is_zero() -> None:
    from dnd_combat_simulator.app import _profile_contribution_chart_data
    from dnd_combat_simulator.simulation import (
        BuildConfig,
        ScenarioConfig,
        simulate_build,
    )

    result = simulate_build(
        BuildConfig("Zero", 0, "1d4", 1),
        ScenarioConfig(target_armor_class=99, rounds=2, simulations=1),
        seed=1,
    )

    rows = _profile_contribution_chart_data(result, "Zero")

    assert rows[0]["Damage per Round contribution"] == 0
    assert rows[0]["Contribution percentage"] == 0


def test_profile_damage_per_use_chart_uses_average_damage_per_use() -> None:
    from dnd_combat_simulator.app import _profile_damage_per_use_chart_data
    from dnd_combat_simulator.combat import ResolutionType
    from dnd_combat_simulator.simulation import (
        AttackProfile,
        BuildConfig,
        ScenarioConfig,
        simulate_build,
    )

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
    from dnd_combat_simulator.app import (
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

    from dnd_combat_simulator.app import _feature_inputs
    from dnd_combat_simulator.combat import ResolutionType

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
    assert disabled_by_label["Stop on Miss"] is True

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


def test_share_toolbar_displays_exact_first_party_url_without_external_call(
    monkeypatch,
) -> None:
    import sys
    from types import SimpleNamespace

    from dnd_combat_simulator import app
    from dnd_combat_simulator.sharing import deserialize_shared_configuration

    calls: list[tuple[str, object]] = []

    class Column:
        def __enter__(self):
            calls.append(("enter_column", self.name))
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def __init__(self, name):
            self.name = name

    def columns(spec, **kwargs):
        calls.append(("columns", {"spec": spec, **kwargs}))
        return [Column("left"), Column("right")]

    def button(label, **kwargs):
        calls.append(("button", {"label": label, **kwargs}))
        return True

    def code(body, **kwargs):
        calls.append(("code", {"body": body, **kwargs}))

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
        columns=columns,
        button=button,
        code=code,
        markdown=lambda *args, **kwargs: calls.append(("markdown", args[0])),
        toast=lambda *args, **kwargs: calls.append(("toast", args[0])),
        warning=lambda *args, **kwargs: calls.append(("warning", args[0])),
        success=lambda *args, **kwargs: calls.append(("success", args[0])),
        link_button=lambda *args, **kwargs: calls.append(("link_button", args[0])),
        caption=lambda *args, **kwargs: calls.append(("caption", args[0])),
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

    app._render_share_configuration_button()

    code_calls = [call[1] for call in calls if call[0] == "code"]
    assert len(code_calls) == 1
    share_url = code_calls[0]["body"]
    assert share_url.startswith("https://first-party.example/sim?config=")
    assert code_calls[0] == {"body": share_url, "language": None, "wrap_lines": False}
    assert state[app.GENERATED_SHARE_URL_SESSION_KEY] == share_url
    assert ("columns", {"spec": [0.06, 0.94], "vertical_alignment": "center"}) in calls
    button_index = next(i for i, call in enumerate(calls) if call[0] == "button")
    assert calls[button_index - 1] == ("enter_column", "left")
    assert calls[button_index][1] == {
        "label": "⤴",
        "help": "Create share link",
        "key": app.SHARE_BUTTON_KEY,
    }
    assert all(call[1].get("label") != "📤" for call in calls if call[0] == "button")
    assert ("toast", "Share link ready") in calls
    assert not any(
        call[0] in {"warning", "success", "caption", "link_button"} for call in calls
    )

    token = share_url.split("config=", 1)[1]
    config = deserialize_shared_configuration(token)
    assert config.compare_enabled is True
    assert config.scenario.target_armor_class == 18
    assert config.scenario.seed == 99
    assert config.build_a.name == "Build A Exact"
    assert config.build_b.name == "Build B Exact"
    assert config.build_b.attack_profiles[0].affected_targets == 3


def test_share_source_has_no_auto_copy_or_obsolete_controls() -> None:
    from pathlib import Path

    source = Path("src/dnd_combat_simulator/app.py").read_text()

    assert "def _copy_share_url_to_clipboard" not in source
    assert "components.html" not in source
    assert "navigator.clipboard.writeText" not in source
    assert "document.execCommand" not in source
    assert "copied" not in source.lower()
    assert "Open Shared Configuration" not in source
    assert "urlopen" not in source
    assert "Request(" not in source


def test_share_button_css_is_scoped_and_theme_compatible() -> None:
    from dnd_combat_simulator import app

    css = app.SHARE_BUTTON_CSS

    assert ".st-key-share-configuration-button button" in css
    assert "42px" in css
    assert "border-radius: 999px" in css
    assert "currentColor" in css
    assert "var(--text-color" in css
    assert "var(--primary-color" in css
    assert "black" not in css.lower()
    assert "white" not in css.lower()
