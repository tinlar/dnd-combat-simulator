from __future__ import annotations

import base64
import json
import zlib
from urllib.parse import parse_qs, urlsplit

import pytest

from dnd_combat_simulator.combat import (
    AttackFeature,
    AttackRollMode,
    ResolutionType,
    SuccessfulSaveDamage,
)
from dnd_combat_simulator.sharing import (
    MAX_ATTACK_PROFILES_PER_BUILD,
    MAX_DECOMPRESSED_JSON_BYTES,
    MAX_ENCODED_TOKEN_LENGTH,
    SharedConfigurationError,
    build_share_url,
    build_short_share_url,
    deserialize_shared_configuration,
    serialize_shared_configuration,
    shared_configuration_from_configs,
)
from dnd_combat_simulator.simulation import (
    AttackProfile,
    BuildConfig,
    ScenarioConfig,
    TriggerType,
    compare_builds,
    simulate_build,
)
from dnd_combat_simulator.ui.constants import (
    COMPARE_WIDGET_KEY,
    SCENARIO_WIDGET_KEYS,
)
from dnd_combat_simulator.ui.sharing import LOADED_SHARED_CONFIG_TOKEN_KEY
from dnd_combat_simulator.ui.state import (
    hydrate_session_state_from_shared_configuration,
)
from dnd_combat_simulator.ui.widget_keys import feature_widget_key, profile_widget_key


def profile(name="Attack", **kwargs):
    return AttackProfile(
        name=name,
        attack_bonus=kwargs.pop("attack_bonus", 7),
        damage_dice=kwargs.pop("damage_dice", "2d6r<2!kh1+3"),
        attacks_per_round=kwargs.pop("attacks_per_round", 2),
        **kwargs,
    )


def shared(compare=False):
    a = BuildConfig(
        "Build A",
        7,
        "1d8+3",
        1,
        attack_profiles=(profile("First"), profile("Second", active_rounds="1, 3-4")),
    )
    b = BuildConfig(
        "Build B",
        0,
        "1d4",
        1,
        attack_profiles=(
            profile(
                "Save",
                attack_bonus=None,
                resolution_type=ResolutionType.SAVING_THROW,
                save_dc=15,
                successful_save_damage=SuccessfulSaveDamage.HALF_DAMAGE,
                affected_targets=3,
                features=frozenset({AttackFeature.POTENT_CANTRIP}),
            ),
            profile(
                "Auto",
                attack_bonus=None,
                resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
                features=frozenset(),
            ),
        ),
    )
    return shared_configuration_from_configs(
        compare_enabled=compare,
        scenario=ScenarioConfig(16, 4, 100, 2),
        seed=42,
        build_a=a,
        build_b=b,
    )


def test_round_trip_default_configuration_and_deterministic_token():
    config = shared_configuration_from_configs(
        compare_enabled=False,
        scenario=ScenarioConfig(15, 4, 10000, 3),
        seed=20240721,
        build_a=BuildConfig("Build A", 5, "1d8+3", 1),
        build_b=BuildConfig("Build B", 5, "1d8+3", 1),
    )
    token = serialize_shared_configuration(config)
    assert deserialize_shared_configuration(token) == config
    assert serialize_shared_configuration(config) == token


def test_round_trip_preserves_comparison_hidden_build_b_profiles_order_and_fields():
    config = shared(compare=False)
    loaded = deserialize_shared_configuration(serialize_shared_configuration(config))
    assert loaded == config
    assert loaded.compare_enabled is False
    assert [p.name for p in loaded.build_a.attack_profiles] == ["First", "Second"]
    assert [p.name for p in loaded.build_b.attack_profiles] == ["Save", "Auto"]
    assert (
        loaded.build_b.attack_profiles[0].successful_save_damage
        is SuccessfulSaveDamage.HALF_DAMAGE
    )
    assert loaded.build_b.attack_profiles[0].affected_targets == 3
    assert loaded.build_a.attack_profiles[1].active_rounds == "1, 3-4"


@pytest.mark.parametrize("mode", list(AttackRollMode))
def test_attack_roll_modes_round_trip(mode):
    config = shared_configuration_from_configs(
        compare_enabled=True,
        scenario=ScenarioConfig(15, 4, 10),
        seed=1,
        build_a=BuildConfig(
            "A", 5, "1d8", 1, attack_profiles=(profile("p", attack_roll_mode=mode),)
        ),
        build_b=BuildConfig("B", 5, "1d8", 1),
    )
    assert (
        deserialize_shared_configuration(serialize_shared_configuration(config))
        .build_a.attack_profiles[0]
        .attack_roll_mode
        is mode
    )


@pytest.mark.parametrize("resolution", list(ResolutionType))
def test_every_resolution_type_round_trips(resolution):
    kwargs = {"resolution_type": resolution}
    if resolution is ResolutionType.SAVING_THROW:
        kwargs |= {"attack_bonus": None, "save_dc": 13}
    if resolution is ResolutionType.AUTOMATIC_DAMAGE:
        kwargs |= {"attack_bonus": None}
    config = shared_configuration_from_configs(
        compare_enabled=True,
        scenario=ScenarioConfig(15, 4, 10),
        seed=1,
        build_a=BuildConfig(
            "A", 0, "1d8", 1, attack_profiles=(profile("p", **kwargs),)
        ),
        build_b=BuildConfig("B", 5, "1d8", 1),
    )
    assert (
        deserialize_shared_configuration(serialize_shared_configuration(config))
        .build_a.attack_profiles[0]
        .resolution_type
        is resolution
    )


def test_all_features_stop_on_miss_and_complex_formula_round_trip():
    config = shared_configuration_from_configs(
        compare_enabled=True,
        scenario=ScenarioConfig(15, 4, 10),
        seed=1,
        build_a=BuildConfig(
            "A",
            5,
            "1d8",
            1,
            attack_profiles=(
                profile(
                    "p",
                    damage_dice="4d6r1!kh3+2",
                    features=frozenset(
                        feature
                        for feature in AttackFeature
                        if feature is not AttackFeature.POTENT_CANTRIP
                    ),
                    attack_roll_mode=AttackRollMode.ADVANTAGE,
                ),
            ),
        ),
        build_b=BuildConfig("B", 5, "1d8", 1),
    )
    loaded = deserialize_shared_configuration(serialize_shared_configuration(config))
    assert loaded.build_a.attack_profiles[0].features == frozenset(
        feature
        for feature in AttackFeature
        if feature is not AttackFeature.POTENT_CANTRIP
    )
    assert loaded.build_a.attack_profiles[0].damage_formula == "4d6r1!kh3+2"


def test_url_generation_one_encoded_config_param_and_no_python_or_results():
    token = serialize_shared_configuration(shared(True))
    url = build_share_url("https://example.test/sim?old=1", token + "+/")
    parsed = urlsplit(url)
    qs = parse_qs(parsed.query)
    assert parsed.geturl().startswith("https://example.test/sim?config=")
    assert set(qs) == {"config"}
    assert qs["config"] == [token + "+/"]
    decoded = zlib.decompress(
        base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    ).decode()
    assert "SimulationResult" not in decoded and "dataclass" not in decoded


def test_missing_padding_is_restored():
    token = serialize_shared_configuration(shared())
    assert "=" not in token
    assert deserialize_shared_configuration(token) == shared()


@pytest.mark.parametrize(
    "token, message", [("abcd", "compressed"), ("not-base64%%%%", "Base64")]
)
def test_invalid_base64_or_compressed_content(token, message):
    with pytest.raises(SharedConfigurationError, match=message):
        deserialize_shared_configuration(token)


def token_for_raw(raw: bytes) -> str:
    return base64.urlsafe_b64encode(zlib.compress(raw)).decode().rstrip("=")


def test_invalid_json_and_unsupported_version_and_missing_fields():
    with pytest.raises(SharedConfigurationError, match="JSON"):
        deserialize_shared_configuration(token_for_raw(b"{"))
    raw = shared().to_json_dict()
    raw["version"] = 999
    with pytest.raises(SharedConfigurationError, match="Unsupported"):
        deserialize_shared_configuration(token_for_raw(json.dumps(raw).encode()))
    del raw["scenario"]
    with pytest.raises(SharedConfigurationError):
        deserialize_shared_configuration(token_for_raw(json.dumps(raw).encode()))


def test_invalid_enum_feature_profile_values_and_too_many_profiles():
    raw = shared().to_json_dict()
    raw["build_a"]["attack_profiles"][0]["resolution_type"] = "bad"
    with pytest.raises(SharedConfigurationError, match="enum"):
        deserialize_shared_configuration(token_for_raw(json.dumps(raw).encode()))
    raw = shared().to_json_dict()
    raw["build_a"]["attack_profiles"][0]["features"] = ["bad"]
    with pytest.raises(SharedConfigurationError, match="enum"):
        deserialize_shared_configuration(token_for_raw(json.dumps(raw).encode()))
    raw = shared().to_json_dict()
    raw["build_a"]["attack_profiles"] *= MAX_ATTACK_PROFILES_PER_BUILD + 1
    with pytest.raises(SharedConfigurationError, match="too many"):
        deserialize_shared_configuration(token_for_raw(json.dumps(raw).encode()))
    raw = shared().to_json_dict()
    raw["build_a"]["attack_profiles"][0]["damage_formula"] = "not dice"
    with pytest.raises(SharedConfigurationError, match="invalid data"):
        deserialize_shared_configuration(token_for_raw(json.dumps(raw).encode()))


def test_size_limits():
    with pytest.raises(SharedConfigurationError, match="too large"):
        deserialize_shared_configuration("a" * (MAX_ENCODED_TOKEN_LENGTH + 1))
    with pytest.raises(SharedConfigurationError, match="too large"):
        deserialize_shared_configuration(
            token_for_raw(b" " * (MAX_DECOMPRESSED_JSON_BYTES + 1))
        )


def test_hydration_loads_scenario_compare_counts_profiles_both_builds_and_replaces():
    state = {LOADED_SHARED_CONFIG_TOKEN_KEY: "old"}
    config = shared(True)
    hydrate_session_state_from_shared_configuration(state, config)
    assert state[SCENARIO_WIDGET_KEYS["rounds"]] == 4
    assert state[COMPARE_WIDGET_KEY] is True
    assert state["first-additional-attack-count"] == 1
    assert state["second-additional-attack-count"] == 1
    assert state[profile_widget_key("first-additional-1", "name")] == "Second"
    assert (
        state[profile_widget_key("second-primary", "resolution_type")] == "Saving Throw"
    )
    assert (
        state[feature_widget_key("second-primary", AttackFeature.POTENT_CANTRIP)]
        is True
    )
    new = shared(False)
    hydrate_session_state_from_shared_configuration(state, new)
    assert state[COMPARE_WIDGET_KEY] is False


def test_invalid_configuration_does_not_partially_mutate_session_state():
    state = {"keep": "me"}
    raw = shared().to_json_dict()
    raw["scenario"]["rounds"] = 0
    with pytest.raises(SharedConfigurationError):
        deserialize_shared_configuration(token_for_raw(json.dumps(raw).encode()))
    assert state == {"keep": "me"}


def test_loaded_configuration_can_be_simulated_single_and_comparison_results_match():
    config = shared(True)
    loaded = deserialize_shared_configuration(serialize_shared_configuration(config))
    scenario = loaded.scenario.to_scenario_config()
    assert simulate_build(
        loaded.build_a.to_build_config(), scenario, loaded.scenario.seed
    ) == simulate_build(
        config.build_a.to_build_config(), scenario, config.scenario.seed
    )
    assert compare_builds(
        first_build=loaded.build_a.to_build_config(),
        second_build=loaded.build_b.to_build_config(),
        scenario=scenario,
        seed=loaded.scenario.seed,
    ) == compare_builds(
        first_build=config.build_a.to_build_config(),
        second_build=config.build_b.to_build_config(),
        scenario=scenario,
        seed=config.scenario.seed,
    )


def test_invalid_shared_configuration_can_decode_without_validation_for_field_marking():
    config = shared_configuration_from_configs(
        compare_enabled=True,
        scenario=ScenarioConfig(15, 4, 10),
        seed=1,
        build_a=BuildConfig(
            "Build A",
            5,
            "1d6+",
            1,
            attack_profiles=(profile("Bad", damage_dice="1d6+"),),
        ),
        build_b=BuildConfig("Build B", 5, "1d8", 1),
    )
    payload = json.dumps(
        config.to_json_dict(), sort_keys=True, separators=(",", ":")
    ).encode()
    token = base64.urlsafe_b64encode(zlib.compress(payload)).decode().rstrip("=")

    with pytest.raises(SharedConfigurationError):
        deserialize_shared_configuration(token)

    decoded = deserialize_shared_configuration(token, validate=False)
    assert decoded.build_a.attack_profiles[0].damage_formula == "1d6+"


def test_short_share_url_one_encoded_share_param_and_strips_query():
    url = build_short_share_url("https://example.test/sim?old=1#frag", "id +/")
    parsed = urlsplit(url)
    qs = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "example.test"
    assert parsed.path == "/sim"
    assert parsed.fragment == ""
    assert set(qs) == {"share"}
    assert qs["share"] == ["id +/"]


def test_shared_urls_preserve_trigger_settings_and_source_rename() -> None:
    from dnd_combat_simulator.sharing import (
        deserialize_shared_configuration,
        serialize_shared_configuration,
        shared_configuration_from_configs,
    )
    from dnd_combat_simulator.simulation import (
        AttackProfile,
        BuildConfig,
        ScenarioConfig,
    )

    build = BuildConfig(
        "Build",
        5,
        "1d4",
        1,
        attack_profiles=(
            AttackProfile("Renamed Greatsword", 5, "1d4", 1, attack_id="src"),
            AttackProfile(
                "Followup",
                5,
                "1d4",
                1,
                attack_id="dep",
                trigger_type="after_success",
                trigger_source_attack_id="src",
                trigger_frequency="once_if_any",
            ),
        ),
    )
    config = shared_configuration_from_configs(
        compare_enabled=False,
        scenario=ScenarioConfig(15, 1, 1),
        seed=1,
        build_a=build,
        build_b=build,
    )
    loaded = deserialize_shared_configuration(serialize_shared_configuration(config))
    dep = loaded.build_a.to_build_config().attack_profiles[1]
    assert dep.trigger_source_attack_id == "src"
    assert dep.trigger_frequency == "once_if_any"


def test_existing_shared_profile_without_trigger_data_loads_as_always() -> None:
    from dnd_combat_simulator.sharing import _profile_from_json

    profile = _profile_from_json(
        {
            "name": "Attack",
            "resolution_type": "attack_roll",
            "attack_bonus": 5,
            "save_dc": None,
            "successful_save_damage": "no_damage",
            "attack_roll_mode": "normal",
            "damage_formula": "1d4",
            "attacks_per_round": 1,
            "affected_targets": 1,
            "active_rounds": "",
            "features": [],
        },
        "profile",
    )
    assert profile.trigger_type == "always"


def test_sometimes_trigger_survives_serialization_round_trip() -> None:
    profile = AttackProfile(
        name="sometimes",
        attack_bonus=None,
        damage_dice="1d4",
        attacks_per_round=1,
        resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
        attack_id="sometimes",
        trigger_type=TriggerType.SOMETIMES,
        trigger_chance_percent=25,
    )
    config = shared_configuration_from_configs(
        build_a=BuildConfig("A", 5, "1d4", 1, attack_profiles=(profile,)),
        build_b=BuildConfig("B", 5, "1d4", 1),
        scenario=ScenarioConfig(target_armor_class=15, rounds=3, simulations=10),
        seed=123,
        compare_enabled=False,
    )

    decoded = deserialize_shared_configuration(serialize_shared_configuration(config))
    decoded_profile = decoded.build_a.to_build_config().attack_profiles[0]

    assert decoded_profile.trigger_type == TriggerType.SOMETIMES
    assert decoded_profile.trigger_chance_percent == 25


def _decode_payload(token: str) -> dict[str, object]:
    return json.loads(
        zlib.decompress(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
    )


def test_math_defaults_round_trip_and_legacy_default() -> None:
    from dnd_combat_simulator.build_math import BuildMathDefaults

    a_defaults = BuildMathDefaults(5, 4, 2, 1)
    b_defaults = BuildMathDefaults(-1, 0, -2, -4)
    config = shared_configuration_from_configs(
        compare_enabled=True,
        scenario=ScenarioConfig(15, 2, 3),
        seed=7,
        build_a=BuildConfig("A", 5, "1d8", 1, math_defaults=a_defaults),
        build_b=BuildConfig("B", 5, "1d6", 1, math_defaults=b_defaults),
    )
    token = serialize_shared_configuration(config)
    payload = _decode_payload(token)
    assert payload["version"] == 1
    assert payload["build_a"]["math_defaults"] == {
        "ability_modifier": 5,
        "proficiency_bonus": 4,
        "attack_bonus_adjustment": 2,
        "save_dc_adjustment": 1,
    }
    restored = deserialize_shared_configuration(token)
    assert restored.build_a.math_defaults == a_defaults
    assert restored.build_b.math_defaults == b_defaults

    del payload["build_a"]["math_defaults"]
    legacy_token = (
        base64.urlsafe_b64encode(
            zlib.compress(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            )
        )
        .decode()
        .rstrip("=")
    )
    assert (
        deserialize_shared_configuration(legacy_token).build_a.math_defaults
        == BuildMathDefaults()
    )


@pytest.mark.parametrize("bad", [{}, {"ability_modifier": 1}, [], None])
def test_malformed_math_defaults_are_rejected(bad: object) -> None:
    config = shared_configuration_from_configs(
        compare_enabled=False,
        scenario=ScenarioConfig(15, 2, 3),
        seed=7,
        build_a=BuildConfig("A", 5, "1d8", 1),
        build_b=BuildConfig("B", 5, "1d6", 1),
    )
    payload = _decode_payload(serialize_shared_configuration(config))
    payload["build_a"]["math_defaults"] = bad
    token = (
        base64.urlsafe_b64encode(zlib.compress(json.dumps(payload).encode()))
        .decode()
        .rstrip("=")
    )
    with pytest.raises(SharedConfigurationError, match="build_a.*math_defaults"):
        deserialize_shared_configuration(token)


@pytest.mark.parametrize("value", [1.2, "1", True, None, [], {}])
def test_malformed_math_default_values_are_rejected(value: object) -> None:
    config = shared_configuration_from_configs(
        compare_enabled=False,
        scenario=ScenarioConfig(15, 2, 3),
        seed=7,
        build_a=BuildConfig("A", 5, "1d8", 1),
        build_b=BuildConfig("B", 5, "1d6", 1),
    )
    payload = _decode_payload(serialize_shared_configuration(config))
    payload["build_b"]["math_defaults"]["ability_modifier"] = value
    token = (
        base64.urlsafe_b64encode(zlib.compress(json.dumps(payload).encode()))
        .decode()
        .rstrip("=")
    )
    with pytest.raises(
        SharedConfigurationError, match="build_b.*math_defaults.*ability_modifier"
    ):
        deserialize_shared_configuration(token)


def test_stage44_shared_profile_inheritance_round_trip() -> None:
    profile = AttackProfile(
        name="Inherited",
        attack_bonus=8,
        save_dc=15,
        damage_dice="2d6",
        attacks_per_round=1,
        attack_id="attack-inherited",
        use_build_attack_bonus=True,
        use_build_save_dc=True,
    )
    config = shared_configuration_from_configs(
        compare_enabled=False,
        scenario=ScenarioConfig(15, 3, 1, 10),
        seed=7,
        build_a=BuildConfig("A", 5, "1d8+3", 1, attack_profiles=(profile,)),
        build_b=BuildConfig("B", 5, "1d8+3", 1, attack_profiles=(profile,)),
    )

    raw = config.to_json_dict()["build_a"]["attack_profiles"][0]
    assert raw["use_build_attack_bonus"] is True
    assert raw["use_build_save_dc"] is True
    assert "use_build_damage_modifier" not in raw
    token = serialize_shared_configuration(config)
    decoded = deserialize_shared_configuration(token)

    round_tripped = decoded.build_a.attack_profiles[0].to_attack_profile()
    assert round_tripped.use_build_attack_bonus is True
    assert round_tripped.use_build_save_dc is True


def test_stage44_legacy_shared_profile_defaults_to_manual() -> None:
    config = shared_configuration_from_configs(
        compare_enabled=False,
        scenario=ScenarioConfig(15, 3, 1, 10),
        seed=7,
        build_a=BuildConfig(
            "A",
            5,
            "1d8+3",
            1,
            attack_profiles=(AttackProfile("Manual", 5, "1d8+3", 1, attack_id="a"),),
        ),
        build_b=BuildConfig(
            "B",
            5,
            "1d8+3",
            1,
            attack_profiles=(AttackProfile("Manual", 5, "1d8+3", 1, attack_id="b"),),
        ),
    ).to_json_dict()
    for build_key in ("build_a", "build_b"):
        for key in (
            "use_build_attack_bonus",
            "use_build_save_dc",
            "inherit_triggering_critical",
            "require_matching_damage_dice_to_continue",
        ):
            config[build_key]["attack_profiles"][0].pop(key)
    token = (
        base64.urlsafe_b64encode(zlib.compress(json.dumps(config).encode()))
        .decode()
        .rstrip("=")
    )

    decoded = deserialize_shared_configuration(token)

    assert decoded.build_a.attack_profiles[0].use_build_attack_bonus is False
    assert decoded.build_a.attack_profiles[0].use_build_save_dc is False
    assert decoded.build_a.attack_profiles[0].inherit_triggering_critical is False
    assert (
        decoded.build_a.attack_profiles[0].require_matching_damage_dice_to_continue
        is False
    )


def test_legacy_enabled_build_damage_modifier_merges_into_formula() -> None:
    config = shared_configuration_from_configs(
        compare_enabled=False,
        scenario=ScenarioConfig(15, 3, 1, 10),
        seed=7,
        build_a=BuildConfig(
            "A",
            5,
            "1d8",
            1,
            attack_profiles=(AttackProfile("Legacy", 5, "1d8", 1, attack_id="a"),),
        ),
        build_b=BuildConfig(
            "B",
            5,
            "1d8",
            1,
            attack_profiles=(AttackProfile("Legacy", 5, "1d8", 1, attack_id="b"),),
        ),
    ).to_json_dict()
    config["build_a"]["math_defaults"]["damage_bonus_adjustment"] = -5
    config["build_a"]["attack_profiles"][0]["use_build_damage_modifier"] = True
    config["build_b"]["math_defaults"]["damage_bonus_adjustment"] = 2
    config["build_b"]["attack_profiles"][0]["use_build_damage_modifier"] = True
    token = (
        base64.urlsafe_b64encode(zlib.compress(json.dumps(config).encode()))
        .decode()
        .rstrip("=")
    )

    decoded = deserialize_shared_configuration(token)

    assert decoded.build_a.attack_profiles[0].damage_formula == "1d8-2"
    assert decoded.build_b.attack_profiles[0].damage_formula == "1d8+5"


def test_legacy_disabled_build_damage_modifier_is_not_merged() -> None:
    config = shared_configuration_from_configs(
        compare_enabled=False,
        scenario=ScenarioConfig(15, 3, 1, 10),
        seed=7,
        build_a=BuildConfig(
            "A",
            5,
            "1d8",
            1,
            attack_profiles=(AttackProfile("Legacy", 5, "1d8", 1, attack_id="a"),),
        ),
        build_b=BuildConfig(
            "B",
            5,
            "1d8",
            1,
            attack_profiles=(AttackProfile("Legacy", 5, "1d8", 1, attack_id="b"),),
        ),
    ).to_json_dict()
    config["build_a"]["math_defaults"]["damage_bonus_adjustment"] = 3
    config["build_a"]["attack_profiles"][0]["use_build_damage_modifier"] = False
    token = (
        base64.urlsafe_b64encode(zlib.compress(json.dumps(config).encode()))
        .decode()
        .rstrip("=")
    )

    decoded = deserialize_shared_configuration(token)

    assert decoded.build_a.attack_profiles[0].damage_formula == "1d8"


def test_stage44_shared_profile_rejects_non_boolean_inheritance() -> None:
    config = shared_configuration_from_configs(
        compare_enabled=False,
        scenario=ScenarioConfig(15, 3, 1, 10),
        seed=7,
        build_a=BuildConfig(
            "A",
            5,
            "1d8+3",
            1,
            attack_profiles=(AttackProfile("Manual", 5, "1d8+3", 1, attack_id="a"),),
        ),
        build_b=BuildConfig(
            "B",
            5,
            "1d8+3",
            1,
            attack_profiles=(AttackProfile("Manual", 5, "1d8+3", 1, attack_id="b"),),
        ),
    ).to_json_dict()
    config["build_a"]["attack_profiles"][0]["use_build_attack_bonus"] = 1
    token = (
        base64.urlsafe_b64encode(zlib.compress(json.dumps(config).encode()))
        .decode()
        .rstrip("=")
    )

    with pytest.raises(SharedConfigurationError, match="must be a boolean"):
        deserialize_shared_configuration(token)
