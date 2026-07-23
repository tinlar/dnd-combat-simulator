# ruff: noqa
"""Focused Streamlit UI helpers."""

from __future__ import annotations

from dnd_combat_simulator.ui._shared import *  # noqa: F403

FEATURE_LABELS = {
    AttackFeature.ELVEN_ACCURACY: "Elven Accuracy",
    AttackFeature.GREAT_WEAPON_FIGHTING: "Great Weapon Fighting",
    AttackFeature.TAVERN_BRAWLER: "Tavern Brawler",
    AttackFeature.STOP_ON_MISS: "Stop on Miss",
    AttackFeature.POTENT_CANTRIP: "Potent Cantrip",
}

FEATURE_HELP = {
    AttackFeature.ELVEN_ACCURACY: (
        "When this profile makes an eligible Dexterity, Intelligence, Wisdom, or "
        "Charisma attack with Advantage, reroll one of the two d20s once. The "
        "lower die is rerolled and the highest remaining result is used."
    ),
    AttackFeature.GREAT_WEAPON_FIGHTING: (
        "Whenever this profile rolls a damage die, treat a result of 1 or 2 as a "
        "3. This changes the die's damage contribution but does not change its "
        "natural face for exploding-die checks."
    ),
    AttackFeature.TAVERN_BRAWLER: (
        "Whenever this profile rolls a damage die and the accepted result is 1, "
        "reroll that die once. The replacement result must be used, even if it "
        "is another 1."
    ),
    AttackFeature.STOP_ON_MISS: (
        "Resolve this profile's attacks in order. When one attack misses, skip all "
        "remaining attacks from this profile during that round. The sequence resets "
        "at the beginning of the next active round."
    ),
    AttackFeature.POTENT_CANTRIP: (
        "When an Attack Roll misses or a Saving Throw succeeds, roll normal "
        "noncritical damage and deal half, rounded down. Automatic Damage profiles "
        "cannot use this feature."
    ),
}

FEATURE_ORDER = (
    AttackFeature.ELVEN_ACCURACY,
    AttackFeature.GREAT_WEAPON_FIGHTING,
    AttackFeature.TAVERN_BRAWLER,
    AttackFeature.STOP_ON_MISS,
    AttackFeature.POTENT_CANTRIP,
)

DAMAGE_FORMULA_HELP = dedent("""
    **Basic**

    - `1d8`
    - `2d6+4`
    - `1d10-1`

    **Reroll**

    - `2d8r<2` — reroll 1s and 2s
    - `2d8r8` — reroll 8s
    - `2d8r1r3r5r7` — reroll odd results

    **Exploding**

    - `3d6!` — explode on 6
    - `3d6!>4` — explode on 4, 5, or 6
    - `3d6!3` — explode only on 3

    **Keep or drop**

    - `4d6kh3` — keep highest 3
    - `4d6kl3` — keep lowest 3
    - `8d100dl3` — drop lowest 3
    - `8d100dh3` — drop highest 3

    **Combined**

    - `4d6r1!kh3+2`
    - `1d6+1d4+4d4+3`
    - `4d6kh3+2d8!+1d4-2`

    **Processing order**

    Each dice group is rolled independently. Formula rerolls, Tavern Brawler,
    explosion checks, Great Weapon Fighting damage contribution, and keep/drop
    apply only to the dice group where they are written. Numeric modifiers apply
    once to the complete damage roll.
    """).strip()

NO_ELIGIBLE_TRIGGER_SOURCE_MESSAGE = (
    "Add another attack to this build before configuring an attack trigger."
)

DAMAGE_FORMULA_PLACEHOLDER = "Examples: 1d8+4, 3d6!, 3d6!>4, 4d6kh3+2, 8d100dh3."

SCENARIO_WIDGET_KEYS = {
    "target_armor_class": "scenario-target-ac",
    "enemy_save_bonus": "scenario-enemy-save-bonus",
    "rounds": "scenario-rounds",
    "simulations": "scenario-simulations",
    "seed": "scenario-seed",
}

COMPARE_WIDGET_KEY = "compare-builds-enabled"

LOADED_SHARED_CONFIG_TOKEN_KEY = "_loaded_shared_config_token"

LOADED_SHARE_ID_KEY = "_loaded_share_id"

GENERATED_SHARE_URL_KEY = "_generated_share_url"

GENERATED_SHARE_FINGERPRINT_KEY = "_generated_share_fingerprint"

SHARE_ERROR_MESSAGE_KEY = "_share_error_message"

LOADED_SHARED_CONFIG_MESSAGE_KEY = "_shared_config_loaded_message_pending"

INVALID_SHARED_CONFIG_MESSAGE_KEY = "_invalid_shared_config_message"

SIMULATION_RUNNING_KEY = "_simulation_running"

SIMULATION_PENDING_KEY = "_simulation_pending"

SIMULATION_DURATION_MESSAGE_KEY = "_simulation_duration_message"

TRIGGER_EXPANDED_KEY_SUFFIX = "trigger-expanded"

MANAGED_RESOURCE_COUNT_KEY = "scenario-managed-resource-count"

MANAGED_RESOURCE_EXPANDED_KEY = "scenario-managed-resources-expanded"

ATTACK_DELETE_CONFIRMATION_KEY = "attack-delete-confirmation-id"

RESOURCE_DELETE_CONFIRMATION_KEY = "resource-delete-confirmation-id"

MANAGED_RESOURCE_IDS_KEY = "scenario-managed-resource-ids"

MAX_ATTACKS_PER_BUILD = 11

ATTACK_IDS_KEY_SUFFIX = "attack-ids"
