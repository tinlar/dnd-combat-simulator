from __future__ import annotations

import re

import pytest

from dnd_combat_simulator.share_store import (
    InMemoryShareStore,
    InvalidShareIdError,
    ShareNotFoundError,
    StoredShareConfigurationError,
)
from dnd_combat_simulator.sharing import (
    SHARED_CONFIGURATION_VERSION,
    SharedAttackProfileConfiguration,
    SharedBuildConfiguration,
    SharedConfiguration,
    SharedConfigurationError,
    SharedScenarioConfiguration,
    deserialize_shared_configuration,
    serialize_shared_configuration,
    shared_configuration_from_configs,
)
from dnd_combat_simulator.simulation import AttackProfile, BuildConfig, ScenarioConfig


def shared_configuration() -> SharedConfiguration:
    return shared_configuration_from_configs(
        compare_enabled=True,
        scenario=ScenarioConfig(15, 3, 100, 2),
        seed=123,
        build_a=BuildConfig(
            "Warrior",
            7,
            "1d8+4",
            2,
            attack_profiles=(AttackProfile("Sword", 7, "1d8+4", 2),),
        ),
        build_b=BuildConfig("Mage", 5, "2d6", 1),
    )


def invalid_configuration() -> SharedConfiguration:
    profile = SharedAttackProfileConfiguration.from_attack_profile(
        AttackProfile("Sword", 7, "1d8+4", 2)
    )
    return SharedConfiguration(
        SHARED_CONFIGURATION_VERSION,
        False,
        SharedScenarioConfiguration(0, 3, 1, 100, 123),
        SharedBuildConfiguration("Warrior", (profile,)),
        SharedBuildConfiguration("Mage", (profile,)),
    )


def test_save_returns_non_empty_url_safe_short_id():
    share_id = InMemoryShareStore().save(shared_configuration())

    assert share_id
    assert len(share_id) < 32
    assert re.fullmatch(r"[A-Za-z0-9_-]+", share_id)


def test_save_and_load_restores_exact_shared_configuration():
    store = InMemoryShareStore()
    config = shared_configuration()

    assert store.load(store.save(config)) == config


def test_separate_saves_produce_separate_ids():
    ids = ["first", "second"]
    store = InMemoryShareStore(id_generator=lambda _: ids.pop(0))

    assert store.save(shared_configuration()) == "first"
    assert store.save(shared_configuration()) == "second"


def test_unknown_id_raises_expected_exception():
    with pytest.raises(ShareNotFoundError, match="not found"):
        InMemoryShareStore().load("missing")


@pytest.mark.parametrize("share_id", ["", "with space", "slash/id", "ümlaut"])
def test_empty_or_malformed_ids_are_rejected(share_id: str):
    with pytest.raises(InvalidShareIdError):
        InMemoryShareStore().load(share_id)


def test_collision_causes_another_id_to_be_generated():
    ids = ["duplicate", "duplicate", "replacement"]
    store = InMemoryShareStore(id_generator=lambda _: ids.pop(0))

    assert store.save(shared_configuration()) == "duplicate"
    assert store.save(shared_configuration()) == "replacement"


def test_invalid_configurations_are_rejected_during_save():
    with pytest.raises(SharedConfigurationError, match="invalid values"):
        InMemoryShareStore().save(invalid_configuration())


def test_corrupted_stored_data_is_rejected_during_load():
    store = InMemoryShareStore(id_generator=lambda _: "stored")
    share_id = store.save(shared_configuration())
    store._tokens_by_id[share_id] = "not-compressed"

    with pytest.raises(
        StoredShareConfigurationError, match="Stored shared configuration"
    ):
        store.load(share_id)


def test_existing_serialization_behavior_remains_unchanged():
    config = shared_configuration()
    token = serialize_shared_configuration(config)

    assert deserialize_shared_configuration(token) == config
    assert serialize_shared_configuration(config) == token
