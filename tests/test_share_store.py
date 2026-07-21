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


class FakeSupabaseError(Exception):
    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeTableQuery:
    def __init__(self, client, table_name: str) -> None:
        self.client = client
        self.table_name = table_name
        self.operations = []
        self.payload = None

    def insert(self, payload):
        self.operations.append(("insert", payload))
        self.payload = payload
        return self

    def select(self, columns: str):
        self.operations.append(("select", columns))
        return self

    def eq(self, column: str, value: str):
        self.operations.append(("eq", column, value))
        return self

    def limit(self, count: int):
        self.operations.append(("limit", count))
        return self

    def execute(self):
        self.client.queries.append(self)
        if self.operations and self.operations[0][0] == "insert":
            if self.client.insert_errors:
                raise self.client.insert_errors.pop(0)
            self.client.rows[self.payload["id"]] = self.payload["config_token"]
            return FakeResponse([self.payload])
        if self.client.select_error is not None:
            raise self.client.select_error
        share_id = next(op[2] for op in self.operations if op[0] == "eq")
        if share_id not in self.client.rows:
            return FakeResponse([])
        return FakeResponse([{"config_token": self.client.rows[share_id]}])


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.rows = {}
        self.queries = []
        self.insert_errors = []
        self.select_error = None

    def table(self, table_name: str):
        return FakeTableQuery(self, table_name)


def test_supabase_store_can_be_constructed_from_url_and_key(monkeypatch):
    import sys
    import types

    from dnd_combat_simulator.share_store import SupabaseShareStore

    created = {}
    fake_client = FakeSupabaseClient()

    def create_client(url, key):
        created["url"] = url
        created["key"] = key
        return fake_client

    monkeypatch.setitem(
        sys.modules, "supabase", types.SimpleNamespace(create_client=create_client)
    )

    store = SupabaseShareStore.from_url_and_key("https://example.supabase.co", "secret")

    assert isinstance(store, SupabaseShareStore)
    assert created == {"url": "https://example.supabase.co", "key": "secret"}


def test_supabase_save_uses_expected_insert_table_and_payload():
    from dnd_combat_simulator.share_store import SupabaseShareStore

    client = FakeSupabaseClient()
    config = shared_configuration()
    share_id = SupabaseShareStore(client, id_generator=lambda _: "abc123").save(config)

    assert share_id == "abc123"
    query = client.queries[0]
    assert query.table_name == "shared_configurations"
    assert query.operations == [
        (
            "insert",
            {"id": "abc123", "config_token": serialize_shared_configuration(config)},
        )
    ]


def test_supabase_save_and_load_round_trip():
    from dnd_combat_simulator.share_store import SupabaseShareStore

    client = FakeSupabaseClient()
    store = SupabaseShareStore(client, id_generator=lambda _: "roundtrip")
    config = shared_configuration()

    assert store.load(store.save(config)) == config


def test_supabase_load_uses_expected_select_filter_and_limit():
    from dnd_combat_simulator.share_store import SupabaseShareStore

    client = FakeSupabaseClient()
    client.rows["saved"] = serialize_shared_configuration(shared_configuration())

    SupabaseShareStore(client).load("saved")

    assert client.queries[0].table_name == "shared_configurations"
    assert client.queries[0].operations == [
        ("select", "config_token"),
        ("eq", "id", "saved"),
        ("limit", 1),
    ]


def test_supabase_unknown_id_raises_expected_exception():
    from dnd_combat_simulator.share_store import SupabaseShareStore

    with pytest.raises(ShareNotFoundError, match="not found"):
        SupabaseShareStore(FakeSupabaseClient()).load("missing")


def test_supabase_invalid_id_is_rejected_before_database_request():
    from dnd_combat_simulator.share_store import SupabaseShareStore

    client = FakeSupabaseClient()
    with pytest.raises(InvalidShareIdError):
        SupabaseShareStore(client).load("bad/id")

    assert client.queries == []


def test_supabase_corrupted_stored_token_raises_expected_exception():
    from dnd_combat_simulator.share_store import SupabaseShareStore

    client = FakeSupabaseClient()
    client.rows["bad"] = "not-compressed"

    with pytest.raises(
        StoredShareConfigurationError, match="Stored shared configuration"
    ):
        SupabaseShareStore(client).load("bad")


@pytest.mark.parametrize(
    "data", [None, {}, [{"wrong": "value"}], ["token"], [{"config_token": ""}]]
)
def test_supabase_malformed_database_response_raises_store_error(data):
    from dnd_combat_simulator.share_store import ShareStoreError, SupabaseShareStore

    class MalformedQuery(FakeTableQuery):
        def execute(self):
            self.client.queries.append(self)
            return FakeResponse(data)

    class MalformedClient(FakeSupabaseClient):
        def table(self, table_name: str):
            return MalformedQuery(self, table_name)

    with pytest.raises(ShareStoreError, match="malformed"):
        SupabaseShareStore(MalformedClient()).load("saved")


def test_supabase_insert_failure_raises_store_error():
    from dnd_combat_simulator.share_store import ShareStoreError, SupabaseShareStore

    client = FakeSupabaseClient()
    client.insert_errors.append(FakeSupabaseError("network down"))

    with pytest.raises(ShareStoreError, match="Failed to save"):
        SupabaseShareStore(client, id_generator=lambda _: "newid").save(
            shared_configuration()
        )


def test_supabase_select_failure_raises_store_error():
    from dnd_combat_simulator.share_store import ShareStoreError, SupabaseShareStore

    client = FakeSupabaseClient()
    client.select_error = FakeSupabaseError("api unavailable")

    with pytest.raises(ShareStoreError, match="Failed to load"):
        SupabaseShareStore(client).load("saved")


def test_supabase_duplicate_collision_retries_and_then_succeeds():
    from dnd_combat_simulator.share_store import SupabaseShareStore

    ids = ["duplicate", "replacement"]
    client = FakeSupabaseClient()
    client.insert_errors.append(FakeSupabaseError("duplicate", code="23505"))

    share_id = SupabaseShareStore(client, id_generator=lambda _: ids.pop(0)).save(
        shared_configuration()
    )

    assert share_id == "replacement"
    assert [q.payload["id"] for q in client.queries] == ["duplicate", "replacement"]


def test_supabase_collision_retry_exhaustion_raises_store_error():
    from dnd_combat_simulator.share_store import ShareStoreError, SupabaseShareStore

    client = FakeSupabaseClient()
    client.insert_errors.extend(
        [FakeSupabaseError("duplicate", code="23505") for _ in range(2)]
    )

    with pytest.raises(ShareStoreError, match="collisions"):
        SupabaseShareStore(
            client, id_generator=lambda _: "duplicate", collision_retries=2
        ).save(shared_configuration())


def test_supabase_invalid_configuration_rejected_before_database_request():
    from dnd_combat_simulator.share_store import SupabaseShareStore

    client = FakeSupabaseClient()
    with pytest.raises(SharedConfigurationError, match="invalid values"):
        SupabaseShareStore(client, id_generator=lambda _: "unused").save(
            invalid_configuration()
        )

    assert client.queries == []
