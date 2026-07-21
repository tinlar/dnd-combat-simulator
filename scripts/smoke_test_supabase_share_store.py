"""Smoke-test the Supabase-backed shared configuration store."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

from dnd_combat_simulator.share_store import SupabaseShareStore
from dnd_combat_simulator.sharing import shared_configuration_from_configs
from dnd_combat_simulator.simulation import AttackProfile, BuildConfig, ScenarioConfig

SECRETS_PATH = Path(".streamlit/secrets.toml")


def _read_secret(name: str, secrets: dict[str, object]) -> str:
    value = secrets.get(name)
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"Missing required {name} in {SECRETS_PATH}.")
    return value


def main() -> int:
    if not SECRETS_PATH.exists():
        print(
            f"Supabase smoke test failed: {SECRETS_PATH} does not exist.",
            file=sys.stderr,
        )
        return 1
    try:
        secrets = tomllib.loads(SECRETS_PATH.read_text())
        supabase_url = _read_secret("SUPABASE_URL", secrets)
        supabase_key = _read_secret("SUPABASE_KEY", secrets)
        configuration = shared_configuration_from_configs(
            compare_enabled=False,
            scenario=ScenarioConfig(15, 3, 10, 2),
            seed=20260721,
            build_a=BuildConfig(
                "Smoke Fighter",
                5,
                "1d8+3",
                1,
                attack_profiles=(AttackProfile("Longsword", 5, "1d8+3", 1),),
            ),
            build_b=BuildConfig("Smoke Target", 4, "1d6+2", 1),
        )
        store = SupabaseShareStore.from_url_and_key(supabase_url, supabase_key)
        share_id = store.save(configuration)
        loaded = store.load(share_id)
        assert loaded == configuration
    except Exception as error:
        print(f"Supabase smoke test failed: {error}", file=sys.stderr)
        return 1
    print(f"Supabase share store smoke test succeeded for share ID: {share_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
