import base64
import json
import zlib
from dataclasses import replace

from dnd_combat_simulator.combat import AttackRollMode
from dnd_combat_simulator.sharing import (
    SharedConfigurationError,
    deserialize_shared_configuration,
    serialize_shared_configuration,
    shared_configuration_from_configs,
)
from dnd_combat_simulator.simulation import (
    AttackProfile,
    BuildConfig,
    ManagedResource,
    ResourceCost,
    ScenarioConfig,
    TriggerFrequency,
    TriggerType,
    compare_builds,
    simulate_build,
)


def _encode_raw(raw: dict[str, object]) -> str:
    payload = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(zlib.compress(payload)).decode().rstrip("=")


def resource_build(*profiles: AttackProfile) -> BuildConfig:
    return BuildConfig("Caster", 5, "1d6", 1, AttackRollMode.NORMAL, profiles)


def test_no_resources_configured_has_no_usage_results() -> None:
    result = simulate_build(
        resource_build(AttackProfile("Cantrip", 5, "1", 1)),
        ScenarioConfig(15, 1, 3),
        1,
    )

    assert result.resource_usage_results == ()


def test_resource_serializes_and_restores_renamed_stable_id() -> None:
    resource = ManagedResource("spell-slots", "Spell Slots", 2)
    profile = AttackProfile(
        "Smite", 5, "1", 1, resource_costs=(ResourceCost("spell-slots", 1),)
    )
    config = shared_configuration_from_configs(
        compare_enabled=False,
        scenario=ScenarioConfig(15, 1, 1, managed_resources=(resource,)),
        seed=7,
        build_a=resource_build(profile),
        build_b=resource_build(AttackProfile("Other", 5, "1", 1)),
    )

    raw = config.to_json_dict()
    assert raw["scenario"]["managed_resources"][0]["resource_id"] == "spell-slots"
    assert "managed_resources" not in raw["build_a"]
    assert "managed_resources" not in raw["build_b"]

    restored = deserialize_shared_configuration(serialize_shared_configuration(config))
    restored_resource = restored.scenario.managed_resources[0]

    assert restored_resource.resource_id == "spell-slots"
    assert restored_resource.name == "Spell Slots"
    assert restored.build_a.attack_profiles[0].resource_costs[0].resource_id == (
        "spell-slots"
    )


def test_independent_resource_pools_for_build_a_and_build_b() -> None:
    resource = ManagedResource("rage", "Rage Uses", 1)
    profile = AttackProfile(
        "Rage hit", 5, "1", 2, resource_costs=(ResourceCost("rage", 1),)
    )

    comparison = compare_builds(
        first_build=resource_build(profile),
        second_build=resource_build(profile),
        scenario=ScenarioConfig(15, 1, 1, managed_resources=(resource,)),
        seed=1,
    )

    assert comparison.first_result.total_attacks_made == 1
    assert comparison.second_result.total_attacks_made == 1
    assert (
        comparison.first_result.resource_usage_results[0].average_consumed_per_combat
        == 1
    )
    assert (
        comparison.second_result.resource_usage_results[0].average_consumed_per_combat
        == 1
    )


def test_resource_deduction_multiple_uses_and_insufficient_skip() -> None:
    resource = ManagedResource("dice", "Superiority Dice", 2)
    profile = AttackProfile(
        "Maneuver", 5, "1", 3, resource_costs=(ResourceCost("dice", 1),)
    )

    result = simulate_build(
        resource_build(profile),
        ScenarioConfig(15, 1, 1, managed_resources=(resource,)),
        1,
    )

    usage = result.resource_usage_results[0]
    assert result.total_attacks_made == 2
    assert result.total_skipped_profile_uses == 1
    assert usage.average_consumed_per_combat == 2
    assert usage.average_remaining_per_combat == 0
    assert usage.exhausted_combat_rate == 1
    assert usage.average_skipped_executions_per_combat == 1


def test_trigger_frequency_limit_prevents_resource_consumption() -> None:
    resource = ManagedResource("charges", "Charges", 2)
    source = AttackProfile("Auto", None, "0", 2, resolution_type="automatic_damage")
    triggered = AttackProfile(
        "Follow-up",
        None,
        "1",
        1,
        resolution_type="automatic_damage",
        trigger_type=TriggerType.AFTER_SUCCESS,
        trigger_source_attack_id="source",
        trigger_frequency=TriggerFrequency.ONCE_PER_ROUND,
        resource_costs=(ResourceCost("charges", 1),),
    )
    source = AttackProfile(
        "Auto", None, "0", 2, resolution_type="automatic_damage", attack_id="source"
    )

    result = simulate_build(
        resource_build(source, triggered),
        ScenarioConfig(15, 1, 1, managed_resources=(resource,)),
        1,
    )

    usage = result.resource_usage_results[0]
    assert triggered in [row.attack_profile for row in result.attack_profile_results]
    assert usage.average_consumed_per_combat == 1
    assert usage.average_remaining_per_combat == 1


def test_invalid_resource_input_caught_before_simulation() -> None:
    resource = ManagedResource("", "", -1)
    profile = AttackProfile(
        "Bad", 5, "1", 1, resource_costs=(ResourceCost("missing", 0),)
    )

    try:
        simulate_build(
            resource_build(profile),
            ScenarioConfig(15, 1, 1, managed_resources=(resource,)),
            1,
        )
    except ValueError as error:
        assert "Managed resource" in str(error)
    else:  # pragma: no cover
        raise AssertionError("invalid resource configuration was accepted")


def test_resource_ends_at_zero_without_blocking_execution() -> None:
    resource = ManagedResource("slot", "Spell Slot", 1)
    profile = AttackProfile(
        "Spell",
        None,
        "1",
        1,
        resolution_type="automatic_damage",
        resource_costs=(ResourceCost("slot", 1),),
    )

    result = simulate_build(
        resource_build(profile),
        ScenarioConfig(15, 1, 1, managed_resources=(resource,)),
        1,
    )

    usage = result.resource_usage_results[0]
    assert usage.ended_at_zero_combat_rate == 1
    assert usage.average_blocked_executions_per_combat == 0
    assert usage.blocked_execution_combat_rate == 0


def test_resource_reaches_zero_and_later_blocks_execution() -> None:
    resource = ManagedResource("slot", "Spell Slot", 1)
    profile = AttackProfile(
        "Spell",
        None,
        "1",
        2,
        resolution_type="automatic_damage",
        resource_costs=(ResourceCost("slot", 1),),
    )

    result = simulate_build(
        resource_build(profile),
        ScenarioConfig(15, 1, 1, managed_resources=(resource,)),
        1,
    )

    usage = result.resource_usage_results[0]
    assert usage.ended_at_zero_combat_rate == 1
    assert usage.average_blocked_executions_per_combat == 1
    assert usage.blocked_execution_combat_rate == 1


def test_resource_never_reaches_zero() -> None:
    resource = ManagedResource("slot", "Spell Slot", 3)
    profile = AttackProfile(
        "Spell",
        None,
        "1",
        1,
        resolution_type="automatic_damage",
        resource_costs=(ResourceCost("slot", 1),),
    )

    result = simulate_build(
        resource_build(profile),
        ScenarioConfig(15, 1, 1, managed_resources=(resource,)),
        1,
    )

    usage = result.resource_usage_results[0]
    assert usage.ended_at_zero_combat_rate == 0
    assert usage.average_remaining_per_combat == 2
    assert usage.blocked_execution_combat_rate == 0


def test_multiple_resources_only_one_blocks_execution() -> None:
    first = ManagedResource("a", "A", 1)
    second = ManagedResource("b", "B", 1)
    profiles = (
        AttackProfile(
            "A",
            None,
            "1",
            2,
            resolution_type="automatic_damage",
            resource_costs=(ResourceCost("a", 1),),
        ),
        AttackProfile(
            "B",
            None,
            "1",
            1,
            resolution_type="automatic_damage",
            resource_costs=(ResourceCost("b", 1),),
        ),
    )

    result = simulate_build(
        resource_build(*profiles),
        ScenarioConfig(15, 1, 1, managed_resources=(first, second)),
        1,
    )

    by_id = {
        usage.resource.resource_id: usage for usage in result.resource_usage_results
    }
    assert by_id["a"].blocked_execution_combat_rate == 1
    assert by_id["b"].blocked_execution_combat_rate == 0


def _build(name, resources=(), profiles=()):
    return BuildConfig(
        name,
        5,
        "1",
        1,
        attack_profiles=profiles or (AttackProfile("Hit", 5, "1", 1),),
        managed_resources=resources,
    )


def test_build_scoped_resources_are_independent_and_not_shared_serialized():
    a_res = (ManagedResource("a", "A Dice", 1),)
    b_res = (ManagedResource("b", "B Slots", 2),)
    a = _build(
        "A",
        a_res,
        (
            AttackProfile(
                "A use",
                None,
                "1",
                2,
                resolution_type="automatic_damage",
                resource_costs=(ResourceCost("a", 1),),
            ),
        ),
    )
    b = _build(
        "B",
        b_res,
        (
            AttackProfile(
                "B use",
                None,
                "1",
                2,
                resolution_type="automatic_damage",
                resource_costs=(ResourceCost("b", 1),),
            ),
        ),
    )
    result = compare_builds(
        first_build=a, second_build=b, scenario=ScenarioConfig(15, 1, 1), seed=1
    )
    assert result.first_result.resource_usage_results[0].resource.resource_id == "a"
    assert (
        result.first_result.resource_usage_results[0].average_consumed_per_combat == 1
    )
    assert result.second_result.resource_usage_results[0].resource.resource_id == "b"
    assert (
        result.second_result.resource_usage_results[0].average_consumed_per_combat == 2
    )
    shared = shared_configuration_from_configs(
        compare_enabled=True,
        scenario=ScenarioConfig(15, 1, 1, managed_resources=a_res + b_res),
        seed=1,
        build_a=a,
        build_b=b,
    )
    raw = shared.to_json_dict()
    assert [r["resource_id"] for r in raw["scenario"]["managed_resources"]] == [
        "a",
        "b",
    ]
    assert "managed_resources" not in raw["build_a"]
    assert "managed_resources" not in raw["build_b"]


def test_resource_pool_resets_every_simulation_iteration():
    res = (ManagedResource("slot", "Slot", 1),)
    build = _build(
        "A",
        res,
        (
            AttackProfile(
                "Spell",
                None,
                "1",
                1,
                resolution_type="automatic_damage",
                resource_costs=(ResourceCost("slot", 1),),
            ),
        ),
    )
    result = simulate_build(build, ScenarioConfig(15, 1, 3), 1)
    assert result.resource_usage_results[0].average_consumed_per_combat == 1
    assert result.total_resource_blocked_executions == 0


def test_renaming_resource_keeps_reference_and_deleting_only_clears_same_build():
    profile = AttackProfile(
        "Spend", 5, "1", 1, resource_costs=(ResourceCost("stable", 1),)
    )
    renamed = ManagedResource("stable", "New Name", 1)
    build = _build("A", (renamed,), (profile,))
    assert build.attack_profiles[0].resource_costs[0].resource_id == renamed.resource_id
    other = _build("B", (ManagedResource("stable", "Other", 1),), (profile,))
    repaired_a = replace(
        build,
        managed_resources=(),
        attack_profiles=(replace(profile, resource_costs=()),),
    )
    assert repaired_a.attack_profiles[0].resource_costs == ()
    assert other.attack_profiles[0].resource_costs[0].resource_id == "stable"


def test_shared_url_round_trip_and_legacy_shared_resources_migrate():
    legacy_res = ManagedResource("ki", "Ki", 1)
    prof = AttackProfile("Spend", 5, "1", 1, resource_costs=(ResourceCost("ki", 1),))
    legacy = shared_configuration_from_configs(
        compare_enabled=True,
        scenario=ScenarioConfig(15, 1, 1, managed_resources=(legacy_res,)),
        seed=1,
        build_a=_build("A", profiles=(prof,)),
        build_b=_build("B", profiles=(prof,)),
    )
    token = serialize_shared_configuration(legacy)
    restored = deserialize_shared_configuration(token)
    assert restored.scenario.managed_resources[0].resource_id == "ki"
    assert restored.build_a.managed_resources == ()
    assert restored.build_b.managed_resources == ()
    assert "managed_resources" not in restored.build_a.to_json_dict()
    assert "managed_resources" not in restored.build_b.to_json_dict()


def _shared_raw_with_resources(
    scenario_resources=(), a_resources=(), b_resources=(), cost_id="ki"
):
    profile = AttackProfile(
        "Spend",
        5,
        "1",
        1,
        attack_id="spend",
        resource_costs=(ResourceCost(cost_id, 1),),
    )
    shared = shared_configuration_from_configs(
        compare_enabled=True,
        scenario=ScenarioConfig(15, 1, 1, managed_resources=scenario_resources),
        seed=1,
        build_a=_build("A", profiles=(profile,)),
        build_b=_build("B", profiles=(profile,)),
    ).to_json_dict()
    if a_resources:
        shared["build_a"]["managed_resources"] = [
            {
                "resource_id": r.resource_id,
                "name": r.name,
                "starting_value": r.starting_value,
            }
            for r in a_resources
        ]
    if b_resources:
        shared["build_b"]["managed_resources"] = [
            {
                "resource_id": r.resource_id,
                "name": r.name,
                "starting_value": r.starting_value,
            }
            for r in b_resources
        ]
    return shared


def test_scenario_resource_survives_round_trip_and_cost_refs_for_both_builds():
    resource = ManagedResource("ki", "Ki", 1)
    profile = AttackProfile(
        "Spend", 5, "1", 1, resource_costs=(ResourceCost("ki", 1),)
    )
    shared = shared_configuration_from_configs(
        compare_enabled=True,
        scenario=ScenarioConfig(15, 1, 1, managed_resources=(resource,)),
        seed=1,
        build_a=_build("A", profiles=(profile,)),
        build_b=_build("B", profiles=(profile,)),
    )
    restored = deserialize_shared_configuration(serialize_shared_configuration(shared))
    assert restored.scenario.managed_resources[0].resource_id == "ki"
    assert restored.build_a.attack_profiles[0].resource_costs[0].resource_id == "ki"
    assert restored.build_b.attack_profiles[0].resource_costs[0].resource_id == "ki"


def test_legacy_build_resources_migrate_and_conflicts_raise():
    ki = ManagedResource("ki", "Ki", 1)
    raw = _shared_raw_with_resources(a_resources=(ki,))
    raw["scenario"].pop("managed_resources", None)
    token = serialize_shared_configuration(
        deserialize_shared_configuration(_encode_raw(raw))
    )
    restored = deserialize_shared_configuration(token)
    assert restored.scenario.managed_resources[0].resource_id == "ki"
    assert "managed_resources" not in restored.to_json_dict()["build_a"]

    raw = _shared_raw_with_resources(b_resources=(ki,))
    raw["scenario"].pop("managed_resources", None)
    restored = deserialize_shared_configuration(_encode_raw(raw))
    assert restored.scenario.managed_resources[0].resource_id == "ki"

    raw = _shared_raw_with_resources(a_resources=(ki,), b_resources=(ki,))
    raw["scenario"].pop("managed_resources", None)
    restored = deserialize_shared_configuration(_encode_raw(raw))
    assert len(restored.scenario.managed_resources) == 1

    conflict = ManagedResource("ki", "Different", 1)
    raw = _shared_raw_with_resources(a_resources=(ki,), b_resources=(conflict,))
    raw["scenario"].pop("managed_resources", None)
    try:
        deserialize_shared_configuration(_encode_raw(raw))
    except SharedConfigurationError as error:
        assert "conflict" in str(error)
    else:  # pragma: no cover
        raise AssertionError("conflicting legacy resources were accepted")


def test_invalid_or_missing_shared_resource_references_raise():
    raw = _shared_raw_with_resources(
        scenario_resources=(ManagedResource("ki", "Ki", 1),), cost_id="missing"
    )
    try:
        deserialize_shared_configuration(_encode_raw(raw))
    except SharedConfigurationError as error:
        assert "resource costs" in str(error)
    else:  # pragma: no cover
        raise AssertionError("missing resource reference was accepted")

    raw = _shared_raw_with_resources(
        scenario_resources=(ManagedResource("", "", -1),), cost_id="ki"
    )
    try:
        deserialize_shared_configuration(_encode_raw(raw))
    except SharedConfigurationError as error:
        assert "managed resource" in str(error)
    else:  # pragma: no cover
        raise AssertionError("invalid resource definition was accepted")
