from dnd_combat_simulator.combat import AttackRollMode
from dnd_combat_simulator.sharing import (
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
