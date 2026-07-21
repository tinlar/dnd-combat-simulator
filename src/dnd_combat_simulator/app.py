"""Streamlit application entry point."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from textwrap import dedent

from dnd_combat_simulator import APP_TITLE
from dnd_combat_simulator.combat import (
    AttackFeature,
    AttackRollMode,
    ResolutionType,
    SuccessfulSaveDamage,
    available_features,
    is_feature_available,
    validate_feature_resolution_combination,
)
from dnd_combat_simulator.share_store import (
    InvalidShareIdError,
    ShareNotFoundError,
    ShareStore,
    ShareStoreError,
    StoredShareConfigurationError,
    SupabaseShareStore,
)
from dnd_combat_simulator.sharing import (
    SharedBuildConfiguration,
    SharedConfiguration,
    SharedConfigurationError,
    build_share_url,
    build_short_share_url,
    deserialize_shared_configuration,
    serialize_shared_configuration,
    shared_configuration_from_configs,
)
from dnd_combat_simulator.simulation import (
    AttackProfile,
    AttackProfileResult,
    BuildComparisonResult,
    BuildConfig,
    ScenarioConfig,
    SimulationResult,
    compare_builds,
    run_damage_simulations,
    simulate_build,
)

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
PROCESSED_SHARE_TRIGGER_KEY = "_processed_share_trigger"
SHARE_ERROR_MESSAGE_KEY = "_share_error_message"
LOADED_SHARED_CONFIG_MESSAGE_KEY = "_shared_config_loaded_message_pending"
INVALID_SHARED_CONFIG_MESSAGE_KEY = "_invalid_shared_config_message"


@dataclass(frozen=True)
class FieldValidationError:
    """A validation message associated with one editable Streamlit field."""

    key: str
    message: str


def _friendly_validation_message(error: ValueError) -> str:
    text = str(error)
    lower_prefix = "invalid damage expression: "
    if text.lower().startswith(lower_prefix):
        text = text[len(lower_prefix) :]
    elif ": invalid damage expression: " in text.lower():
        text = text.split(": ", 1)[1]
    if text.startswith("damage expression "):
        text = "Damage expression " + text[len("damage expression ") :]
    elif text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text


def _add_error(errors: list[FieldValidationError], key: str, message: str) -> None:
    errors.append(FieldValidationError(key, message))


def _validate_profile_fields(
    profile: AttackProfile, *, prefix: str
) -> list[FieldValidationError]:
    from dnd_combat_simulator.dice import parse_damage_expression
    from dnd_combat_simulator.simulation import parse_active_rounds

    errors: list[FieldValidationError] = []
    if not profile.name.strip():
        _add_error(
            errors, profile_widget_key(prefix, "name"), "Attack name is required."
        )
    if not profile.damage_dice.strip():
        _add_error(
            errors,
            profile_widget_key(prefix, "damage_formula"),
            "Damage expression is required.",
        )
    else:
        try:
            parse_damage_expression(profile.damage_dice)
        except ValueError as error:
            _add_error(
                errors,
                profile_widget_key(prefix, "damage_formula"),
                _friendly_validation_message(error),
            )
    if profile.attacks_per_round < 1:
        _add_error(
            errors,
            profile_widget_key(prefix, "attacks_per_round"),
            "Attacks per round must be at least 1.",
        )
    if profile.affected_targets < 1:
        _add_error(
            errors,
            profile_widget_key(prefix, "affected_targets"),
            "Affected Targets must be at least 1.",
        )
    if (
        profile.resolution_type is ResolutionType.ATTACK_ROLL
        and profile.attack_bonus is None
    ):
        _add_error(
            errors,
            profile_widget_key(prefix, "attack_bonus"),
            "Attack bonus is required.",
        )
    if profile.resolution_type is ResolutionType.SAVING_THROW:
        if profile.save_dc is None:
            _add_error(
                errors, profile_widget_key(prefix, "save_dc"), "Save DC is required."
            )
        elif profile.save_dc < 1:
            _add_error(
                errors,
                profile_widget_key(prefix, "save_dc"),
                "Save DC must be a positive integer.",
            )
    try:
        parse_active_rounds(profile.active_rounds)
    except ValueError as error:
        _add_error(errors, profile_widget_key(prefix, "active_rounds"), str(error))
    try:
        validate_feature_resolution_combination(
            profile.features,
            profile.resolution_type,
            label=profile.name or "Attack profile",
            affected_targets=profile.affected_targets,
        )
    except ValueError as error:
        _add_error(errors, profile_widget_key(prefix, "resolution_type"), str(error))
    return errors


def validate_build_fields(
    build: BuildConfig, *, prefix: str
) -> list[FieldValidationError]:
    errors: list[FieldValidationError] = []
    if not build.name.strip():
        _add_error(errors, f"{prefix}-build-name", "Build name is required.")
    profiles = build.resolved_attack_profiles()
    names = [profile.name.strip() for profile in profiles]
    duplicate_names = {name for name in names if name and names.count(name) > 1}
    for index, profile in enumerate(profiles):
        widget_prefix = profile_prefix(prefix, index)
        errors.extend(_validate_profile_fields(profile, prefix=widget_prefix))
        if profile.name.strip() in duplicate_names:
            _add_error(
                errors,
                profile_widget_key(widget_prefix, "name"),
                "Attack profile names must be unique within a build.",
            )
    return errors


def validate_scenario_fields(scenario: ScenarioConfig) -> list[FieldValidationError]:
    errors: list[FieldValidationError] = []
    if scenario.target_armor_class < 1:
        _add_error(
            errors,
            SCENARIO_WIDGET_KEYS["target_armor_class"],
            "Target Armor Class must be at least 1.",
        )
    if scenario.rounds < 1:
        _add_error(
            errors,
            SCENARIO_WIDGET_KEYS["rounds"],
            "Number of rounds must be at least 1.",
        )
    if scenario.simulations < 1:
        _add_error(
            errors,
            SCENARIO_WIDGET_KEYS["simulations"],
            "Number of simulations must be at least 1.",
        )
    return errors


def validation_errors_by_key(errors: list[FieldValidationError]) -> dict[str, str]:
    return {error.key: error.message for error in errors}


def validate_configuration_for_ui(
    configuration: SharedConfiguration,
) -> dict[tuple[str, str | None, str], str]:
    """Return structured editable-field errors for a shared configuration.

    Keys are scoped by build (``build_a``/``build_b``), profile identifier, and
    field name so similarly named fields in different builds or profiles cannot
    be conflated.
    """

    structured: dict[tuple[str, str | None, str], str] = {}
    for error in validate_scenario_fields(configuration.scenario.to_scenario_config()):
        structured[("scenario", None, error.key)] = error.message
    for build_key, prefix, build in (
        ("build_a", "first", configuration.build_a),
        ("build_b", "second", configuration.build_b),
    ):
        for error in validate_build_fields(build.to_build_config(), prefix=prefix):
            profile_id: str | None = None
            field = error.key
            if error.key.startswith(f"{prefix}-primary-"):
                profile_id = "profile_1"
                field = error.key.removeprefix(f"{prefix}-primary-").replace("-", "_")
            elif error.key.startswith(f"{prefix}-additional-"):
                parts = error.key.split("-")
                if len(parts) >= 4 and parts[2].isdigit():
                    profile_id = f"profile_{int(parts[2]) + 1}"
                    field = "_".join(parts[3:])
            elif error.key == f"{prefix}-build-name":
                field = "name"
            structured[(build_key, profile_id, field)] = error.message
    return structured


def _configuration_errors_for_current_state() -> dict[tuple[str, str | None, str], str]:
    import streamlit as st

    session_state = getattr(st, "session_state", {})
    scenario = ScenarioConfig(
        target_armor_class=int(
            session_state.get(SCENARIO_WIDGET_KEYS["target_armor_class"], 15)
        ),
        enemy_save_bonus=int(
            session_state.get(SCENARIO_WIDGET_KEYS["enemy_save_bonus"], 3)
        ),
        rounds=int(session_state.get(SCENARIO_WIDGET_KEYS["rounds"], 4)),
        simulations=int(session_state.get(SCENARIO_WIDGET_KEYS["simulations"], 10_000)),
    )
    configuration = shared_configuration_from_configs(
        compare_enabled=bool(session_state.get(COMPARE_WIDGET_KEY, False)),
        scenario=scenario,
        seed=int(session_state.get(SCENARIO_WIDGET_KEYS["seed"], 20240721)),
        build_a=_build_from_state("first", "Build A"),
        build_b=_build_from_state("second", "Build B"),
    )
    return validate_configuration_for_ui(configuration)


def _render_error(message: str) -> None:
    import streamlit as st

    error = getattr(st, "error", None)
    if error is not None:
        error(message, icon="⚠️")


def _field_error(errors_by_key: dict[str, str], key: str) -> bool:
    if message := errors_by_key.get(key):
        _render_error(message)
        return True
    return False


SHARE_TOOLBAR_HTML = """
<div class="share-toolbar" role="group" aria-label="Share configuration">
    <button
        class="share-button"
        type="button"
        title="Copy share link"
        aria-label="Copy share link"
    >
        <svg
            class="share-icon"
            viewBox="0 0 24 24"
            aria-hidden="true"
            focusable="false"
        >
            <path
                d="M6 18c.8-4.9 4-7.3 9.1-7.3h1.2"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
            />
            <path
                d="M13.8 6.2 18.6 11l-4.8 4.8"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
            />
        </svg>
        <span class="share-label">Share Configuration</span>
    </button>
    <span class="share-status" aria-live="polite"></span>
    <input class="share-fallback" type="text" readonly hidden />
</div>
"""

SHARE_TOOLBAR_CSS = """
.share-toolbar {
    min-height: 48px;
    height: 48px;
    display: flex;
    align-items: center;
    gap: 0.6rem;
    color: var(--st-text-color);
    background: var(--st-background-color);
    font-family: var(--st-font);
    overflow: hidden;
}

.share-button {
    height: 42px;
    min-width: 42px;
    padding: 0 0.9rem;
    border-radius: 999px; /* legacy circle control used border-radius: 50% */
    border: 1px solid var(--st-border-color);
    background: var(--st-secondary-background-color);
    color: var(--st-text-color);
    font-family: var(--st-font);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.45rem;
    line-height: 1;
    cursor: pointer;
}

.share-button:hover:not(:disabled) {
    border-color: var(--st-primary-color);
    color: var(--st-primary-color);
}

.share-button:focus-visible {
    outline: 2px solid var(--st-primary-color);
    outline-offset: 2px;
}

.share-button:disabled {
    cursor: not-allowed;
    opacity: 0.6;
}

.share-icon {
    width: 20px;
    height: 20px;
    flex: 0 0 auto;
}

.share-status {
    min-width: 12rem;
    color: var(--st-text-color);
    font-family: var(--st-font);
    opacity: 0;
    transition: opacity 180ms ease;
    text-overflow: ellipsis;
}

.share-status.visible {
    opacity: 1;
}

.share-fallback {
    width: min(24rem, 45vw);
    min-width: 12rem;
    font-family: var(--st-font);
}

.share-fallback[hidden] {
    display: none;
}
"""

SHARE_TOOLBAR_JS = """
export default function(component) {
    const { data, parentElement, setTriggerValue } = component;
    const button = parentElement.querySelector('.share-button');
    const label = parentElement.querySelector('.share-label');
    const status = parentElement.querySelector('.share-status');
    const fallbackInput = parentElement.querySelector('.share-fallback');
    let latestData = {};
    let statusTimer = null;
    let mode = 'create';

    function setStatus(message, temporary = false) {
        status.textContent = message || '';
        status.classList.toggle('visible', Boolean(message));
        if (statusTimer !== null) {
            window.clearTimeout(statusTimer);
            statusTimer = null;
        }
        if (temporary && message) {
            statusTimer = window.setTimeout(() => {
                setStatus('');
                if (mode === 'copy') {
                    label.textContent = 'Copy Link';
                }
            }, 1500);
        }
    }

    function revealFallback(message) {
        fallbackInput.value = latestData.url || '';
        fallbackInput.hidden = false;
        fallbackInput.focus();
        fallbackInput.select();
        label.textContent = 'Copy Link';
        setStatus(message);
    }

    function showCopied() {
        fallbackInput.hidden = true;
        label.textContent = 'Link copied';
        setStatus('Link copied', true);
    }

    function render(nextData) {
        latestData = nextData || {};
        button.disabled = Boolean(latestData.disabled || latestData.creating);
        fallbackInput.hidden = true;
        fallbackInput.value = latestData.url || '';
        button.title = latestData.url ? 'Copy share link' : 'Share configuration';
        button.setAttribute('aria-label', button.title);

        if (latestData.disabled) {
            label.textContent = 'Temporarily unavailable';
            setStatus(latestData.message || '');
            mode = 'disabled';
        } else if (latestData.creating) {
            label.textContent = 'Creating...';
            setStatus('');
            mode = 'creating';
        } else if (latestData.url) {
            label.textContent = 'Copy Link';
            setStatus('');
            mode = 'copy';
        } else {
            label.textContent = 'Share Configuration';
            setStatus(latestData.message || '');
            mode = 'create';
        }
    }

    async function copyUrl() {
        const targetUrl = latestData.url || '';
        if (!targetUrl) {
            return false;
        }
        if (navigator.clipboard && window.isSecureContext) {
            try {
                await navigator.clipboard.writeText(targetUrl);
                showCopied();
                return true;
            } catch (error) {
                // Fall through to the selectable-input fallback below.
            }
        }

        revealFallback('Copy blocked. Press Ctrl+C.');
        try {
            if (document.execCommand("copy")) {
                showCopied();
                return true;
            }
        } catch (fallbackError) {
            // Keep the selectable fallback visible.
        }
        revealFallback('Copy blocked. Press Ctrl+C.');
        return false;
    }

    render(data || {});

    button.onclick = async () => {
        if (mode === 'create') {
            label.textContent = 'Creating...';
            button.disabled = true;
            setTriggerValue('create_share', `${Date.now()}-${Math.random()}`);
        } else if (mode === 'copy') {
            await copyUrl();
        }
    };

    return () => {
        if (statusTimer !== null) {
            window.clearTimeout(statusTimer);
        }
        button.onclick = null;
    };
}
"""

_SHARE_TOOLBAR_COMPONENT = None


def _get_share_toolbar_component():
    """Register and return the v2 share toolbar component."""
    global _SHARE_TOOLBAR_COMPONENT
    if _SHARE_TOOLBAR_COMPONENT is None:
        import streamlit as st

        components = getattr(st, "components", None)
        if components is None or not hasattr(components, "v2"):
            return lambda **kwargs: None
        _SHARE_TOOLBAR_COMPONENT = st.components.v2.component(
            "share_toolbar",
            html=SHARE_TOOLBAR_HTML,
            css=SHARE_TOOLBAR_CSS,
            js=SHARE_TOOLBAR_JS,
        )
    return _SHARE_TOOLBAR_COMPONENT


def profile_prefix(build_prefix: str, index: int) -> str:
    return (
        f"{build_prefix}-primary"
        if index == 0
        else f"{build_prefix}-additional-{index}"
    )


def profile_widget_key(prefix: str, field: str) -> str:
    suffixes = {
        "name": "name",
        "resolution_type": "resolution-type",
        "attack_bonus": "attack-bonus",
        "save_dc": "save-dc",
        "successful_save_damage": "successful-save-damage",
        "attack_roll_mode": "mode",
        "damage_formula": "damage-dice",
        "attacks_per_round": "attacks",
        "affected_targets": "affected-targets",
        "active_rounds": "active-rounds",
    }
    return f"{prefix}-{suffixes[field]}"


def feature_widget_key(prefix: str, feature: AttackFeature) -> str:
    return f"{prefix}-feature-{feature.value}"


PAGE_WIDTH_CSS = """
<style>
    .stApp .block-container {
        width: 90vw;
        max-width: 90vw;
        margin-left: auto;
        margin-right: auto;
        padding-left: clamp(1rem, 2vw, 2.5rem);
        padding-right: clamp(1rem, 2vw, 2.5rem);
        box-sizing: border-box;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 14px;
        border-color: rgba(128, 128, 128, 0.28);
        box-shadow: 0 0.25rem 0.8rem rgba(0, 0, 0, 0.06);
    }

    div[data-testid="stVerticalBlockBorderWrapper"] > div {
        padding: clamp(0.75rem, 1.3vw, 1.25rem);
    }

    @media (max-width: 640px) {
        .stApp .block-container {
            width: 100%;
            max-width: 100%;
            padding-left: 1rem;
            padding-right: 1rem;
        }
    }
</style>
"""


def configure_page() -> None:
    """Configure Streamlit to use a wide, centered application layout."""
    import streamlit as st

    st.set_page_config(page_title=APP_TITLE, page_icon="🎲", layout="wide")
    st.markdown(PAGE_WIDTH_CSS, unsafe_allow_html=True)


@dataclass(frozen=True)
class SimulationInputs:
    """Validated user inputs for a damage simulation run."""

    attack_bonus: int
    target_armor_class: int
    damage_dice: str
    rounds: int
    attacks_per_round: int
    simulations: int
    enemy_save_bonus: int = 3
    attack_roll_mode: AttackRollMode = AttackRollMode.NORMAL


@dataclass(frozen=True)
class ComparisonInputs:
    """Validated user inputs for a named build comparison."""

    first_build: BuildConfig
    second_build: BuildConfig
    scenario: ScenarioConfig
    seed: int


@dataclass(frozen=True)
class SingleBuildInputs:
    """Validated user inputs for a single named build simulation."""

    build: BuildConfig
    scenario: ScenarioConfig
    seed: int


def validate_simulation_inputs(inputs: SimulationInputs) -> None:
    """Validate Streamlit form inputs before running a simulation.

    Raises:
        ValueError: If an input cannot produce a usable damage simulation.
    """
    if not inputs.damage_dice.strip():
        msg = "Damage Formula is required. Use notation such as 1d8+4."
        raise ValueError(msg)
    if inputs.target_armor_class < 1:
        msg = "Target Armor Class must be at least 1."
        raise ValueError(msg)
    if inputs.rounds < 1:
        msg = "Number of rounds must be at least 1."
        raise ValueError(msg)
    if inputs.attacks_per_round < 1:
        msg = "Attacks per round must be at least 1."
        raise ValueError(msg)
    if inputs.simulations < 1:
        msg = "Number of simulations must be at least 1."
        raise ValueError(msg)


def format_damage(value: float) -> str:
    """Format a damage value for display."""
    return f"{value:.2f}"


def format_rate(value: float) -> str:
    """Format a fractional rate as a percentage for display."""
    return f"{value:.2%}"


def format_signed_damage(value: float) -> str:
    """Format a signed damage delta for display."""
    return f"{value:+.2f}"


def format_signed_rate(value: float) -> str:
    """Format a signed fractional rate as a percentage-point delta."""
    return f"{value:+.2%}"


def run_simulation_from_inputs(inputs: SimulationInputs) -> SimulationResult:
    """Validate inputs and run the shared simulation engine."""
    validate_simulation_inputs(inputs)
    return run_damage_simulations(
        attack_bonus=inputs.attack_bonus,
        target_armor_class=inputs.target_armor_class,
        enemy_save_bonus=inputs.enemy_save_bonus,
        damage_dice=inputs.damage_dice.strip(),
        rounds=inputs.rounds,
        simulations=inputs.simulations,
        attacks_per_round=inputs.attacks_per_round,
        attack_roll_mode=inputs.attack_roll_mode,
    )


def run_single_build_from_inputs(inputs: SingleBuildInputs) -> SimulationResult:
    """Validate inputs and run the shared single-build simulation engine."""
    return simulate_build(inputs.build, inputs.scenario, inputs.seed)


def run_comparison_from_inputs(inputs: ComparisonInputs) -> BuildComparisonResult:
    """Validate inputs and run the shared comparison engine."""
    return compare_builds(
        first_build=inputs.first_build,
        second_build=inputs.second_build,
        scenario=inputs.scenario,
        seed=inputs.seed,
    )


def _render_section_container():
    """Return a bordered Streamlit container when available."""
    import streamlit as st

    container = getattr(st, "container", None)
    if container is None:
        return nullcontext()
    try:
        return container(border=True)
    except TypeError:
        return container()


def _round_chart_data(
    result: SimulationResult, build_name: str
) -> list[dict[str, int | float | str]]:
    """Build round-level chart data for one simulation result."""
    return [
        {
            "Round": round_result.round_number,
            "Average total damage": round_result.average_damage,
            "Build": build_name,
        }
        for round_result in result.round_results
    ]


def _comparison_round_chart_data(
    comparison: BuildComparisonResult,
) -> list[dict[str, int | float | str]]:
    """Build round-level chart data for both compared builds."""
    return [
        *_round_chart_data(comparison.first_result, comparison.first_build.name),
        *_round_chart_data(comparison.second_result, comparison.second_build.name),
    ]


def _profile_metadata(
    profile_result: AttackProfileResult, index: int, build_name: str
) -> dict[str, int | float | str]:
    profile = profile_result.attack_profile
    return {
        "Profile": profile.name,
        "Order": index,
        "Build": build_name,
        "Resolution type": profile.resolution_type.value.replace("_", " ").title(),
        "Active Rounds": profile.active_rounds or "Every round",
        "Maximum attacks per active round": profile.attacks_per_round,
        "Attacks per active round": profile.attacks_per_round,
        "Affected targets": profile.affected_targets,
        "Actual profile uses": profile_result.total_profile_uses,
        "Skipped profile uses": profile_result.total_skipped_profile_uses,
        "Average damage per use": profile_result.average_damage_per_use,
    }


def _profile_contribution_chart_data(
    result: SimulationResult, build_name: str
) -> list[dict[str, int | float | str]]:
    """Build profile contribution chart data in configured attack-profile order."""
    total = result.average_damage_per_round
    rows = []
    for index, profile_result in enumerate(result.attack_profile_results, start=1):
        contribution = profile_result.average_damage_per_round
        rows.append(
            {
                **_profile_metadata(profile_result, index, build_name),
                "Damage per Round contribution": contribution,
                "Contribution percentage": contribution / total * 100 if total else 0,
            }
        )
    return rows


def _profile_damage_per_use_chart_data(
    result: SimulationResult, build_name: str
) -> list[dict[str, int | float | str]]:
    """Build average damage per profile use chart data in configured order."""
    return [
        {
            **_profile_metadata(profile_result, index, build_name),
            "Average damage per use": profile_result.average_damage_per_use,
            "Actual profile uses": profile_result.total_profile_uses,
            "Skipped profile uses": profile_result.total_skipped_profile_uses,
        }
        for index, profile_result in enumerate(result.attack_profile_results, start=1)
    ]


def _line_chart(data, *, x: str, y: str, color: str):
    import altair as alt
    import pandas as pd

    return (
        alt.Chart(pd.DataFrame(data))
        .mark_line(point=True)
        .encode(
            x=alt.X(x, title="Round number", axis=alt.Axis(format="d")),
            y=alt.Y(y, title="Average total damage"),
            color=alt.Color(color, title="Build"),
            tooltip=[
                alt.Tooltip(x, title="Round"),
                alt.Tooltip(y, title="Average damage", format=".2f"),
                alt.Tooltip(color, title="Build"),
            ],
        )
    )


def _profile_contribution_bar_chart(data):
    import altair as alt
    import pandas as pd

    return (
        alt.Chart(pd.DataFrame(data))
        .mark_bar()
        .encode(
            x=alt.X("Profile:N", sort=alt.SortField("Order"), title="Attack profile"),
            y=alt.Y(
                "Damage per Round contribution:Q",
                title="Damage per Round contribution",
            ),
            tooltip=[
                alt.Tooltip("Profile:N", title="Attack name"),
                alt.Tooltip("Resolution type:N", title="Resolution type"),
                alt.Tooltip(
                    "Damage per Round contribution:Q",
                    title="Damage per Round contribution",
                    format=".2f",
                ),
                alt.Tooltip(
                    "Contribution percentage:Q",
                    title="Contribution percentage",
                    format=".1f",
                ),
                alt.Tooltip("Active Rounds:N", title="Active Rounds"),
                alt.Tooltip(
                    "Maximum attacks per active round:Q",
                    title="Maximum attacks per active round",
                ),
                alt.Tooltip("Actual profile uses:Q", title="Actual profile uses"),
                alt.Tooltip("Skipped profile uses:Q", title="Skipped profile uses"),
                alt.Tooltip(
                    "Average damage per use:Q",
                    title="Average damage per use",
                    format=".2f",
                ),
                alt.Tooltip("Affected targets:Q", title="Affected Targets"),
            ],
        )
    )


def _profile_damage_per_use_bar_chart(data):
    import altair as alt
    import pandas as pd

    return (
        alt.Chart(pd.DataFrame(data))
        .mark_bar()
        .encode(
            x=alt.X("Profile:N", sort=alt.SortField("Order"), title="Attack profile"),
            y=alt.Y(
                "Average damage per use:Q",
                title="Average total damage from one use",
            ),
            tooltip=[
                alt.Tooltip("Profile:N", title="Attack name"),
                alt.Tooltip("Resolution type:N", title="Resolution type"),
                alt.Tooltip(
                    "Average damage per use:Q",
                    title="Average damage per use",
                    format=".2f",
                ),
                alt.Tooltip("Actual profile uses:Q", title="Actual profile uses"),
                alt.Tooltip("Skipped profile uses:Q", title="Skipped profile uses"),
                alt.Tooltip(
                    "Maximum attacks per active round:Q",
                    title="Maximum attacks per active round",
                ),
                alt.Tooltip("Affected targets:Q", title="Affected Targets"),
                alt.Tooltip("Active Rounds:N", title="Active Rounds"),
            ],
        )
    )


def _render_single_build_charts(build: BuildConfig, result: SimulationResult) -> None:
    """Render focused single-build damage charts above detailed result tables."""
    import streamlit as st

    st.markdown("##### Damage per Round")
    st.caption("Average total damage in each round, including zero-damage rounds.")
    st.altair_chart(
        _line_chart(
            _round_chart_data(result, build.name),
            x="Round:O",
            y="Average total damage:Q",
            color="Build:N",
        ),
        width="stretch",
    )

    contribution_data = _profile_contribution_chart_data(result, build.name)
    damage_per_use_data = _profile_damage_per_use_chart_data(result, build.name)
    first_col, second_col = st.columns(2)
    with first_col:
        st.markdown("##### Attack Contribution to Damage per Round")
        st.caption(
            "How much each attack adds to the build's overall average Damage per Round."
        )
        st.altair_chart(
            _profile_contribution_bar_chart(contribution_data), width="stretch"
        )
    with second_col:
        st.markdown("##### Average Damage per Attack Use")
        st.caption(
            "Expected total damage each time the attack is used, including misses, "
            "saves, and all affected targets."
        )
        st.altair_chart(
            _profile_damage_per_use_bar_chart(damage_per_use_data), width="stretch"
        )


def _render_comparison_charts(comparison: BuildComparisonResult) -> None:
    """Render focused comparison charts while keeping profiles separate."""
    import streamlit as st

    st.markdown("##### Damage per Round")
    st.caption("Round-by-round damage for each build on the same round axis.")
    st.altair_chart(
        _line_chart(
            _comparison_round_chart_data(comparison),
            x="Round:O",
            y="Average total damage:Q",
            color="Build:N",
        ),
        width="stretch",
    )

    for build, result in (
        (comparison.first_build, comparison.first_result),
        (comparison.second_build, comparison.second_result),
    ):
        st.markdown(f"##### {build.name}")
        first_col, second_col = st.columns(2)
        with first_col:
            st.markdown("###### Attack Contribution to Damage per Round")
            st.caption(
                "How much each attack adds to the build's overall average "
                "Damage per Round."
            )
            st.altair_chart(
                _profile_contribution_bar_chart(
                    _profile_contribution_chart_data(result, build.name)
                ),
                width="stretch",
            )
        with second_col:
            st.markdown("###### Average Damage per Attack Use")
            st.caption(
                "Expected total damage each time the attack is used, including misses, "
                "saves, and all affected targets."
            )
            st.altair_chart(
                _profile_damage_per_use_bar_chart(
                    _profile_damage_per_use_chart_data(result, build.name)
                ),
                width="stretch",
            )


def _result_rows(comparison: BuildComparisonResult) -> list[dict[str, str]]:
    """Build side-by-side display rows for comparison results."""
    first = comparison.first_result
    second = comparison.second_result
    difference = comparison.difference
    return [
        {
            "Metric": "Average damage per round",
            comparison.first_build.name: format_damage(first.average_damage_per_round),
            comparison.second_build.name: format_damage(
                second.average_damage_per_round
            ),
            "Difference": format_signed_damage(difference.average_damage_per_round),
        },
        {
            "Metric": "Average total damage across all affected targets",
            comparison.first_build.name: format_damage(
                first.average_total_damage_per_simulation
            ),
            comparison.second_build.name: format_damage(
                second.average_total_damage_per_simulation
            ),
            "Difference": format_signed_damage(difference.average_total_damage),
        },
        {
            "Metric": "Average damage per target per round",
            comparison.first_build.name: format_damage(
                first.average_damage_per_target_per_round
            ),
            comparison.second_build.name: format_damage(
                second.average_damage_per_target_per_round
            ),
            "Difference": format_signed_damage(
                difference.average_damage_per_target_per_round
            ),
        },
        {
            "Metric": "Critical hit percentage",
            comparison.first_build.name: format_rate(first.critical_hit_rate),
            comparison.second_build.name: format_rate(second.critical_hit_rate),
            "Difference": format_signed_rate(difference.critical_hit_rate),
        },
        {
            "Metric": "Round 1 burst damage",
            comparison.first_build.name: format_damage(first.first_round_burst_damage),
            comparison.second_build.name: format_damage(
                second.first_round_burst_damage
            ),
            "Difference": format_signed_damage(
                first.first_round_burst_damage - second.first_round_burst_damage
            ),
        },
        {
            "Metric": "Average damage after round 1",
            comparison.first_build.name: format_damage(
                first.average_damage_after_round_1
            ),
            comparison.second_build.name: format_damage(
                second.average_damage_after_round_1
            ),
            "Difference": format_signed_damage(
                first.average_damage_after_round_1 - second.average_damage_after_round_1
            ),
        },
        {
            "Metric": "Highest-damage round",
            comparison.first_build.name: str(first.highest_damage_round),
            comparison.second_build.name: str(second.highest_damage_round),
            "Difference": "—",
        },
    ]


def _winner_label(
    first_name: str, first_value: float, second_name: str, second_value: float
) -> str:
    if first_value > second_value:
        return first_name
    if second_value > first_value:
        return second_name
    return "Tie"


def _round_breakdown_rows(comparison: BuildComparisonResult) -> list[dict[str, str]]:
    """Build side-by-side per-round result rows."""
    rows = []
    for first_round, second_round in zip(
        comparison.first_result.round_results,
        comparison.second_result.round_results,
        strict=True,
    ):
        rows.append(
            {
                "Round": str(first_round.round_number),
                f"{comparison.first_build.name} avg damage": format_damage(
                    first_round.average_damage
                ),
                f"{comparison.second_build.name} avg damage": format_damage(
                    second_round.average_damage
                ),
                f"{comparison.first_build.name} avg attacks": format_damage(
                    first_round.average_attacks
                ),
                f"{comparison.second_build.name} avg attacks": format_damage(
                    second_round.average_attacks
                ),
                f"{comparison.first_build.name} crit %": format_rate(
                    first_round.critical_hit_rate
                ),
                f"{comparison.second_build.name} crit %": format_rate(
                    second_round.critical_hit_rate
                ),
            }
        )
    return rows


def _render_results(result: SimulationResult) -> None:
    """Render simulation results in a compact metric grid."""
    import streamlit as st

    st.subheader("Results")

    first_row = st.columns(4)
    first_row[0].metric(
        "Average total damage per round",
        format_damage(result.average_damage_per_round),
    )
    first_row[1].metric(
        "Average total damage across targets",
        format_damage(result.average_total_damage_per_simulation),
    )
    first_row[2].metric("Attack-roll hit percentage", format_rate(result.hit_rate))
    first_row[3].metric(
        "Attack-roll critical hit percentage", format_rate(result.critical_hit_rate)
    )

    second_row = st.columns(4)
    second_row[0].metric(
        "Minimum total damage",
        format_damage(result.minimum_total_damage_in_simulation),
    )
    second_row[1].metric(
        "Maximum total damage",
        format_damage(result.maximum_total_damage_in_simulation),
    )
    second_row[2].metric("Total attacks simulated", f"{result.total_attacks_made:,}")
    second_row[3].metric(
        "Target resolutions simulated", f"{result.total_target_resolutions:,}"
    )

    st.caption(f"Attack roll mode: {result.attack_roll_mode.value.title()}")


def _profile_breakdown_rows(result: SimulationResult) -> list[dict[str, str]]:
    """Build per-profile damage breakdown rows."""
    rows = []
    for profile_result in result.attack_profile_results:
        profile = profile_result.attack_profile
        row = {
            "Attack profile": profile.name,
            "Resolution type": profile.resolution_type.value.replace("_", " ").title(),
            "Maximum attacks per active round": str(profile.attacks_per_round),
            "Affected targets": str(profile.affected_targets),
            "Active Rounds": profile.active_rounds or "Every round",
            "Feats and Features": format_features(profile.features),
            "Actual profile uses": f"{profile_result.total_profile_uses:,}",
            "Skipped profile uses": f"{profile_result.total_skipped_profile_uses:,}",
            "Average skipped uses per simulation": format_damage(
                profile_result.average_skipped_profile_uses_per_simulation
            ),
            "Target resolutions": f"{profile_result.total_target_resolutions:,}",
            "Average damage per use": format_damage(
                profile_result.average_damage_per_use
            ),
            "Damage per Round contribution": format_damage(
                profile_result.average_damage_per_round
            ),
            "Average damage per target per round": format_damage(
                profile_result.average_damage_per_target_per_round
            ),
            "Average total damage across all affected targets": format_damage(
                profile_result.average_total_damage_per_simulation
            ),
        }
        if profile.resolution_type is ResolutionType.AUTOMATIC_DAMAGE:
            row["Automatic damage applications"] = (
                f"{profile_result.automatic_damage_applications:,}"
            )
        elif profile.resolution_type is ResolutionType.SAVING_THROW:
            row["Failed save percentage"] = format_rate(profile_result.failed_save_rate)
            row["Successful save percentage"] = format_rate(
                profile_result.successful_save_rate
            )
        else:
            row["Hit percentage"] = format_rate(profile_result.hit_rate)
            row["Critical hit percentage"] = format_rate(
                profile_result.critical_hit_rate
            )
        rows.append(row)
    return rows


def _single_result_rows(result: SimulationResult) -> list[dict[str, str]]:
    """Build aggregate rows for a single-build result table."""
    return [
        {
            "Metric": "Average total damage per round",
            "Value": format_damage(result.average_damage_per_round),
        },
        {
            "Metric": "Average total damage across the combat",
            "Value": format_damage(result.average_total_damage_per_simulation),
        },
        {
            "Metric": "Average damage per target per round",
            "Value": format_damage(result.average_damage_per_target_per_round),
        },
        {
            "Metric": "Round 1 burst damage",
            "Value": format_damage(result.first_round_burst_damage),
        },
        {
            "Metric": "Average damage after round 1",
            "Value": format_damage(result.average_damage_after_round_1),
        },
        {
            "Metric": "Highest-damage round",
            "Value": (
                f"{result.highest_damage_round} "
                f"({format_damage(result.highest_round_average_damage)})"
            ),
        },
        {
            "Metric": "Minimum total damage",
            "Value": format_damage(result.minimum_total_damage_in_simulation),
        },
        {
            "Metric": "Maximum total damage",
            "Value": format_damage(result.maximum_total_damage_in_simulation),
        },
        {"Metric": "Total attack uses", "Value": f"{result.total_attacks_made:,}"},
        {
            "Metric": "Total target resolutions",
            "Value": f"{result.total_target_resolutions:,}",
        },
    ]


def _single_round_breakdown_rows(result: SimulationResult) -> list[dict[str, str]]:
    """Build per-round rows for a single-build result."""
    return [
        {
            "Round": str(round_result.round_number),
            "Average damage": format_damage(round_result.average_damage),
            "Average attack uses": format_damage(round_result.average_attacks),
            "Hit percentage": format_rate(round_result.hit_rate),
            "Critical hit percentage": format_rate(round_result.critical_hit_rate),
            "Failed save percentage": format_rate(round_result.failed_save_rate),
            "Successful save percentage": format_rate(
                round_result.successful_save_rate
            ),
        }
        for round_result in result.round_results
    ]


def _render_single_build_results(build: BuildConfig, result: SimulationResult) -> None:
    """Render complete results for one build without comparison labels or deltas."""
    import streamlit as st

    heading = build.name.strip() or "Simulation"
    with _render_section_container():
        st.subheader(f"{heading} results")
        metric_rows = st.columns(5)
        metric_rows[0].metric(
            "Average damage per round", format_damage(result.average_damage_per_round)
        )
        metric_rows[1].metric(
            "Average total damage",
            format_damage(result.average_total_damage_per_simulation),
        )
        metric_rows[2].metric(
            "Round 1 burst", format_damage(result.first_round_burst_damage)
        )
        metric_rows[3].metric(
            "Sustained after round 1",
            format_damage(result.average_damage_after_round_1),
        )
        metric_rows[4].metric(
            "Highest-damage round",
            (
                f"{result.highest_damage_round} "
                f"({format_damage(result.highest_round_average_damage)})"
            ),
        )
        _render_single_build_charts(build, result)
        with st.expander("Detailed Results", expanded=False):
            st.table(_single_result_rows(result))
            st.markdown("##### Per-round breakdown")
            st.table(_single_round_breakdown_rows(result))
            st.markdown("##### Per-attack-profile breakdown")
            st.table(_profile_breakdown_rows(result))


def _render_comparison_results(comparison: BuildComparisonResult) -> None:
    """Render two build results side by side with deltas."""
    import streamlit as st

    with _render_section_container():
        st.subheader("Build comparison")
        if comparison.higher_average_damage_build_name is None:
            st.success("Both builds have the same average damage per round.")
        else:
            st.success(
                f"{comparison.higher_average_damage_build_name} has higher "
                "average damage."
            )
        first_cols = st.columns(5)
        for cols, build, result in (
            (first_cols, comparison.first_build, comparison.first_result),
            (st.columns(5), comparison.second_build, comparison.second_result),
        ):
            cols[0].metric(
                f"{build.name} avg/round",
                format_damage(result.average_damage_per_round),
            )
            cols[1].metric(
                f"{build.name} total",
                format_damage(result.average_total_damage_per_simulation),
            )
            cols[2].metric(
                f"{build.name} round 1", format_damage(result.first_round_burst_damage)
            )
            cols[3].metric(
                f"{build.name} sustained",
                format_damage(result.average_damage_after_round_1),
            )
            cols[4].metric(
                f"{build.name} highest round",
                (
                    f"{result.highest_damage_round} "
                    f"({format_damage(result.highest_round_average_damage)})"
                ),
            )
        st.markdown("##### Winners")
        st.write(
            "Round 1 burst: "
            + _winner_label(
                comparison.first_build.name,
                comparison.first_result.first_round_burst_damage,
                comparison.second_build.name,
                comparison.second_result.first_round_burst_damage,
            )
        )
        st.write(
            "Sustained damage after round 1: "
            + _winner_label(
                comparison.first_build.name,
                comparison.first_result.average_damage_after_round_1,
                comparison.second_build.name,
                comparison.second_result.average_damage_after_round_1,
            )
        )
        st.write(
            "Total average damage: "
            + _winner_label(
                comparison.first_build.name,
                comparison.first_result.average_total_damage_per_simulation,
                comparison.second_build.name,
                comparison.second_result.average_total_damage_per_simulation,
            )
        )
        _render_comparison_charts(comparison)
        with st.expander("Detailed Results", expanded=False):
            st.table(_result_rows(comparison))
            st.markdown("##### Per-round damage")
            st.table(_round_breakdown_rows(comparison))
            st.markdown(f"##### {comparison.first_build.name} attack breakdown")
            st.table(_profile_breakdown_rows(comparison.first_result))
            st.markdown(f"##### {comparison.second_build.name} attack breakdown")
            st.table(_profile_breakdown_rows(comparison.second_result))
            st.caption(
                "Difference is first build minus second build. Both builds used "
                "separate random-number-generator instances initialized with the "
                "same seed."
            )


def format_features(features: frozenset[AttackFeature]) -> str:
    """Format selected profile features in stable interface order."""
    selected = [
        FEATURE_LABELS[feature] for feature in FEATURE_ORDER if feature in features
    ]
    return ", ".join(selected) if selected else "None"


def _feature_inputs(
    prefix: str, resolution_type: ResolutionType, affected_targets: int = 1
) -> frozenset[AttackFeature]:
    """Render feats and features controls for one attack profile."""
    import streamlit as st

    selected = set()
    expander = getattr(st, "expander", None)
    checkbox = getattr(st, "checkbox", None)
    if expander is None or checkbox is None:
        return frozenset()
    with expander("Feats and Features", expanded=False):
        columns = getattr(st, "columns", None)
        feature_columns = columns(min(3, len(FEATURE_ORDER))) if columns else None
        for index, feature in enumerate(FEATURE_ORDER):
            disabled = not is_feature_available(
                feature, resolution_type, affected_targets=affected_targets
            )
            if disabled:
                getattr(st, "session_state", {}).pop(
                    feature_widget_key(prefix, feature), None
                )
            target = (
                feature_columns[index % len(feature_columns)] if feature_columns else st
            )
            target_checkbox = getattr(target, "checkbox", checkbox)
            checked = target_checkbox(
                FEATURE_LABELS[feature],
                value=False,
                key=feature_widget_key(prefix, feature),
                help=FEATURE_HELP[feature],
                disabled=disabled,
            )
            if checked and not disabled:
                selected.add(feature)
    return frozenset(selected)


def _attack_profile_inputs(
    prefix: str, default_name: str, errors_by_key: dict[str, str] | None = None
) -> AttackProfile:
    """Render and collect one attack profile's input controls."""
    import streamlit as st

    errors_by_key = errors_by_key or {}
    attack_name = st.text_input(
        "Attack name", value=default_name, key=profile_widget_key(prefix, "name")
    )
    _field_error(errors_by_key, profile_widget_key(prefix, "name"))
    resolution_type_label = st.selectbox(
        "Resolution Type",
        options=["Attack Roll", "Saving Throw", "Automatic Damage"],
        index=0,
        key=profile_widget_key(prefix, "resolution_type"),
    )
    resolution_type = {
        "Attack Roll": ResolutionType.ATTACK_ROLL,
        "Saving Throw": ResolutionType.SAVING_THROW,
        "Automatic Damage": ResolutionType.AUTOMATIC_DAMAGE,
    }[resolution_type_label]
    _field_error(errors_by_key, profile_widget_key(prefix, "resolution_type"))
    row_one = st.columns(2)
    if resolution_type is ResolutionType.ATTACK_ROLL:
        attack_bonus = row_one[0].number_input(
            "Attack bonus",
            value=5,
            step=1,
            key=profile_widget_key(prefix, "attack_bonus"),
        )
        _field_error(errors_by_key, profile_widget_key(prefix, "attack_bonus"))
        save_dc = None
    elif resolution_type is ResolutionType.SAVING_THROW:
        attack_bonus = None
        save_dc = row_one[0].number_input(
            "Save DC",
            min_value=1,
            value=13,
            step=1,
            key=profile_widget_key(prefix, "save_dc"),
        )
        _field_error(errors_by_key, profile_widget_key(prefix, "save_dc"))
    else:
        attack_bonus = None
        save_dc = None
    damage_dice = row_one[1].text_input(
        "Damage Formula",
        value="1d8+3",
        placeholder=DAMAGE_FORMULA_PLACEHOLDER,
        help=DAMAGE_FORMULA_HELP,
        key=profile_widget_key(prefix, "damage_formula"),
    )
    if not _field_error(errors_by_key, profile_widget_key(prefix, "damage_formula")):
        current_damage_errors = _validate_profile_fields(
            AttackProfile(default_name, 0, damage_dice, 1), prefix=prefix
        )
        for error in current_damage_errors:
            if error.key == profile_widget_key(prefix, "damage_formula"):
                _render_error(error.message)
                break
    row_two = st.columns(3)
    attacks_per_round = row_two[0].number_input(
        "Attacks per round",
        min_value=1,
        value=1,
        step=1,
        key=profile_widget_key(prefix, "attacks_per_round"),
    )
    _field_error(errors_by_key, profile_widget_key(prefix, "attacks_per_round"))
    affected_targets = row_two[1].number_input(
        "Affected Targets",
        min_value=1,
        value=1,
        step=1,
        key=profile_widget_key(prefix, "affected_targets"),
    )
    _field_error(errors_by_key, profile_widget_key(prefix, "affected_targets"))
    if resolution_type is ResolutionType.ATTACK_ROLL:
        attack_roll_mode_label = row_two[2].selectbox(
            "Attack roll mode",
            options=[mode.value.title() for mode in AttackRollMode],
            index=0,
            key=profile_widget_key(prefix, "attack_roll_mode"),
        )
        attack_roll_mode = AttackRollMode(attack_roll_mode_label.lower())
        successful_save_damage = SuccessfulSaveDamage.NO_DAMAGE
    elif resolution_type is ResolutionType.SAVING_THROW:
        successful_save_damage_label = row_two[2].selectbox(
            "Successful Save Damage",
            options=["No damage", "Half damage"],
            index=0,
            key=profile_widget_key(prefix, "successful_save_damage"),
        )
        attack_roll_mode = AttackRollMode.NORMAL
        successful_save_damage = (
            SuccessfulSaveDamage.HALF_DAMAGE
            if successful_save_damage_label == "Half damage"
            else SuccessfulSaveDamage.NO_DAMAGE
        )
    else:
        attack_roll_mode = AttackRollMode.NORMAL
        successful_save_damage = SuccessfulSaveDamage.NO_DAMAGE
    active_rounds = st.text_input(
        "Active Rounds",
        value="",
        help="Leave blank for every round. Examples: 1-5 or 1, 3-5, 8.",
        key=profile_widget_key(prefix, "active_rounds"),
    )
    _field_error(errors_by_key, profile_widget_key(prefix, "active_rounds"))
    features = _feature_inputs(prefix, resolution_type, int(affected_targets))
    return AttackProfile(
        name=attack_name,
        attack_bonus=None if attack_bonus is None else int(attack_bonus),
        damage_dice=damage_dice,
        attacks_per_round=int(attacks_per_round),
        affected_targets=int(affected_targets),
        attack_roll_mode=attack_roll_mode,
        active_rounds=active_rounds,
        resolution_type=resolution_type,
        save_dc=None if save_dc is None else int(save_dc),
        successful_save_damage=successful_save_damage,
        features=features,
    )


def _profile_definitions(
    build_prefix: str, additional_attack_count: int
) -> tuple[tuple[str, str, str], ...]:
    """Return stable key prefixes, headings, and default names for visible profiles."""
    if additional_attack_count < 0:
        msg = "Additional attack count must be at least 0."
        raise ValueError(msg)
    if additional_attack_count > 10:
        msg = "Additional attack count must be no more than 10."
        raise ValueError(msg)

    return (
        (f"{build_prefix}-primary", "Primary Attack", "Primary attack"),
        *(
            (
                f"{build_prefix}-additional-{index}",
                f"Additional Attack {index}",
                f"Additional attack {index}",
            )
            for index in range(1, additional_attack_count + 1)
        ),
    )


def _build_config_from_profiles(
    name: str,
    profiles: tuple[AttackProfile, ...],
) -> BuildConfig:
    """Create a build config with every displayed profile attached."""
    primary = profiles[0]
    return BuildConfig(
        name=name,
        attack_bonus=primary.attack_bonus or 0,
        damage_dice=primary.damage_dice,
        attacks_per_round=primary.attacks_per_round,
        attack_roll_mode=primary.attack_roll_mode,
        attack_profiles=profiles,
    )


def _build_inputs(
    prefix: str, default_name: str, errors_by_key: dict[str, str] | None = None
) -> BuildConfig:
    """Render and collect one build's input controls."""
    import streamlit as st

    errors_by_key = errors_by_key or {}
    with _render_section_container():
        st.markdown(f"#### {default_name}")
        name = st.text_input(
            "Build name", value=default_name, key=f"{prefix}-build-name"
        )
        _field_error(errors_by_key, f"{prefix}-build-name")
        additional_attack_count = st.number_input(
            "Additional Distinct Attacks",
            min_value=0,
            max_value=10,
            value=0,
            step=1,
            key=f"{prefix}-additional-attack-count",
        )

        profiles = []
        for profile_prefix, heading, default_attack_name in _profile_definitions(
            prefix, int(additional_attack_count)
        ):
            divider = getattr(st, "divider", None)
            if divider is None:
                st.markdown("---")
            else:
                divider()
            st.markdown(f"##### {heading}")
            profiles.append(
                _attack_profile_inputs(
                    profile_prefix, default_attack_name, errors_by_key
                )
            )

    return _build_config_from_profiles(name, tuple(profiles))


def _resolution_type_label(resolution_type: ResolutionType) -> str:
    return {
        ResolutionType.ATTACK_ROLL: "Attack Roll",
        ResolutionType.SAVING_THROW: "Saving Throw",
        ResolutionType.AUTOMATIC_DAMAGE: "Automatic Damage",
    }[resolution_type]


def _successful_save_damage_label(value: SuccessfulSaveDamage) -> str:
    return "Half damage" if value is SuccessfulSaveDamage.HALF_DAMAGE else "No damage"


def _hydrate_build_session_state(
    session_state, prefix: str, build: SharedBuildConfiguration
) -> None:
    session_state[f"{prefix}-build-name"] = build.name
    session_state[f"{prefix}-additional-attack-count"] = len(build.attack_profiles) - 1
    for index, profile in enumerate(build.attack_profiles):
        widget_prefix = profile_prefix(prefix, index)
        session_state[profile_widget_key(widget_prefix, "name")] = profile.name
        session_state[profile_widget_key(widget_prefix, "resolution_type")] = (
            _resolution_type_label(profile.resolution_type)
        )
        session_state[profile_widget_key(widget_prefix, "attack_bonus")] = (
            profile.attack_bonus if profile.attack_bonus is not None else 5
        )
        session_state[profile_widget_key(widget_prefix, "save_dc")] = (
            profile.save_dc if profile.save_dc is not None else 13
        )
        session_state[profile_widget_key(widget_prefix, "successful_save_damage")] = (
            _successful_save_damage_label(profile.successful_save_damage)
        )
        session_state[profile_widget_key(widget_prefix, "attack_roll_mode")] = (
            profile.attack_roll_mode.value.title()
        )
        session_state[profile_widget_key(widget_prefix, "damage_formula")] = (
            profile.damage_formula
        )
        session_state[profile_widget_key(widget_prefix, "attacks_per_round")] = (
            profile.attacks_per_round
        )
        session_state[profile_widget_key(widget_prefix, "affected_targets")] = (
            profile.affected_targets
        )
        session_state[profile_widget_key(widget_prefix, "active_rounds")] = (
            profile.active_rounds
        )
        for feature in FEATURE_ORDER:
            session_state[feature_widget_key(widget_prefix, feature)] = (
                feature in profile.features
            )


def hydrate_session_state_from_shared_configuration(
    session_state, configuration: SharedConfiguration
) -> None:
    """Populate Streamlit widget state from a fully validated shared config."""
    scenario = configuration.scenario
    session_state[SCENARIO_WIDGET_KEYS["target_armor_class"]] = (
        scenario.target_armor_class
    )
    session_state[SCENARIO_WIDGET_KEYS["enemy_save_bonus"]] = scenario.enemy_save_bonus
    session_state[SCENARIO_WIDGET_KEYS["rounds"]] = scenario.rounds
    session_state[SCENARIO_WIDGET_KEYS["simulations"]] = scenario.simulations
    session_state[SCENARIO_WIDGET_KEYS["seed"]] = scenario.seed
    session_state[COMPARE_WIDGET_KEY] = configuration.compare_enabled
    _hydrate_build_session_state(session_state, "first", configuration.build_a)
    _hydrate_build_session_state(session_state, "second", configuration.build_b)


def share_store_ui_message(error: Exception) -> str:
    """Map share storage exceptions to safe end-user messages."""
    if isinstance(error, ShareNotFoundError):
        return "This shared configuration could not be found."
    if isinstance(error, InvalidShareIdError):
        return "Invalid shared configuration link."
    if isinstance(
        error,
        (ShareStoreError, StoredShareConfigurationError, SharedConfigurationError),
    ):
        return "Shared configurations are temporarily unavailable. Try again later."
    return "Shared configurations are temporarily unavailable. Try again later."


def resolve_shared_query_params(query_params) -> tuple[str, str | None] | None:
    """Return the active share query parameter.

    Short ``?share=`` links take precedence over legacy ``?config=`` links when
    both are present.
    """

    def first_value(name: str) -> str | None:
        value = query_params.get(name) if hasattr(query_params, "get") else None
        if isinstance(value, list):
            value = value[0] if value else None
        return value if isinstance(value, str) and value else None

    share_id = first_value("share")
    if share_id:
        return ("share", share_id)
    token = first_value("config")
    if token:
        return ("config", token)
    return None


def get_supabase_share_store_from_secrets(secrets) -> ShareStore | None:
    """Construct a Supabase share store from Streamlit secrets if configured."""
    supabase_url = secrets.get("SUPABASE_URL") if hasattr(secrets, "get") else None
    supabase_key = secrets.get("SUPABASE_KEY") if hasattr(secrets, "get") else None
    if not supabase_url or not supabase_key:
        return None
    return SupabaseShareStore.from_url_and_key(str(supabase_url), str(supabase_key))


def get_streamlit_share_store() -> ShareStore | None:
    """Return the cached production share store, or ``None`` if unconfigured."""
    import streamlit as st

    cache_resource = getattr(st, "cache_resource", lambda **_: lambda func: func)

    @cache_resource(show_spinner=False)
    def cached_store(supabase_url: str, supabase_key: str) -> ShareStore:
        return SupabaseShareStore.from_url_and_key(supabase_url, supabase_key)

    secrets = getattr(st, "secrets", {})
    supabase_url = secrets.get("SUPABASE_URL") if hasattr(secrets, "get") else None
    supabase_key = secrets.get("SUPABASE_KEY") if hasattr(secrets, "get") else None
    if not supabase_url or not supabase_key:
        return None
    try:
        return cached_store(str(supabase_url), str(supabase_key))
    except Exception:
        return None


def load_configuration_from_share_store(
    share_store: ShareStore, share_id: str
) -> SharedConfiguration:
    return share_store.load(share_id)


def _validation_errors_for_configuration(
    configuration: SharedConfiguration,
) -> list[FieldValidationError]:
    return [
        *validate_scenario_fields(configuration.scenario.to_scenario_config()),
        *validate_build_fields(configuration.build_a.to_build_config(), prefix="first"),
        *validate_build_fields(
            configuration.build_b.to_build_config(), prefix="second"
        ),
    ]


def load_shared_configuration_from_query() -> None:
    """Apply a shared configuration query token once before widgets are created."""
    import streamlit as st

    query_params = getattr(st, "query_params", {})
    resolved = resolve_shared_query_params(query_params)
    if not resolved:
        return
    kind, value = resolved
    if kind == "share":
        if getattr(st, "session_state", {}).get(LOADED_SHARE_ID_KEY) == value:
            return
        share_store = get_streamlit_share_store()
        if share_store is None:
            st.error(
                "Shared configurations are temporarily unavailable. Try again later."
            )
            return
        try:
            configuration = load_configuration_from_share_store(share_store, value)
        except Exception as error:
            st.error(share_store_ui_message(error))
            return
        loaded_key = LOADED_SHARE_ID_KEY
    else:
        if (
            getattr(st, "session_state", {}).get(LOADED_SHARED_CONFIG_TOKEN_KEY)
            == value
        ):
            return
        try:
            configuration = deserialize_shared_configuration(value, validate=False)
        except SharedConfigurationError as error:
            st.error(f"Invalid shared configuration link: {error}")
            return
        loaded_key = LOADED_SHARED_CONFIG_TOKEN_KEY

    hydrate_session_state_from_shared_configuration(st.session_state, configuration)
    validation_errors = _validation_errors_for_configuration(configuration)
    if validation_errors:
        st.session_state[INVALID_SHARED_CONFIG_MESSAGE_KEY] = (
            "Shared configuration loaded with invalid fields. Fix the highlighted "
            "fields before running calculations."
        )
    st.session_state[loaded_key] = value
    st.session_state[LOADED_SHARED_CONFIG_MESSAGE_KEY] = True


def save_shared_configuration(
    share_store: ShareStore, configuration: SharedConfiguration
) -> str:
    return share_store.save(configuration)


def _current_shared_configuration() -> SharedConfiguration:
    import streamlit as st

    session_state = getattr(st, "session_state", {})
    scenario = ScenarioConfig(
        target_armor_class=int(
            session_state.get(SCENARIO_WIDGET_KEYS["target_armor_class"], 15)
        ),
        enemy_save_bonus=int(
            session_state.get(SCENARIO_WIDGET_KEYS["enemy_save_bonus"], 3)
        ),
        rounds=int(session_state.get(SCENARIO_WIDGET_KEYS["rounds"], 4)),
        simulations=int(session_state.get(SCENARIO_WIDGET_KEYS["simulations"], 10_000)),
    )
    return shared_configuration_from_configs(
        compare_enabled=bool(session_state.get(COMPARE_WIDGET_KEY, False)),
        scenario=scenario,
        seed=int(session_state.get(SCENARIO_WIDGET_KEYS["seed"], 20240721)),
        build_a=_build_from_state("first", "Build A"),
        build_b=_build_from_state("second", "Build B"),
    )


def _current_short_shared_configuration_url(share_store: ShareStore) -> str:
    import streamlit as st

    share_id = save_shared_configuration(share_store, _current_shared_configuration())
    return build_short_share_url(
        getattr(getattr(st, "context", None), "url", ""), share_id
    )


def _legacy_current_shared_configuration_url() -> str:
    import streamlit as st

    token = serialize_shared_configuration(_current_shared_configuration())
    return build_share_url(getattr(getattr(st, "context", None), "url", ""), token)


def _current_shared_configuration_url() -> str:
    """Build the legacy long configuration URL for backwards-compatible tests."""
    return _legacy_current_shared_configuration_url()


def _build_from_state(prefix: str, default_build_name: str) -> BuildConfig:
    """Build a configuration from existing session-state values or widget defaults."""
    import streamlit as st

    session_state = getattr(st, "session_state", {})
    if f"{prefix}-build-name" not in session_state:
        return _build_config_from_profiles(
            default_build_name, (AttackProfile("Primary attack", 5, "1d8+3", 1),)
        )
    count = int(session_state.get(f"{prefix}-additional-attack-count", 0))
    profiles = []
    for index, (_, _, default_name) in enumerate(_profile_definitions(prefix, count)):
        widget_prefix = profile_prefix(prefix, index)
        resolution = {
            "Attack Roll": ResolutionType.ATTACK_ROLL,
            "Saving Throw": ResolutionType.SAVING_THROW,
            "Automatic Damage": ResolutionType.AUTOMATIC_DAMAGE,
        }.get(
            session_state.get(
                profile_widget_key(widget_prefix, "resolution_type"), "Attack Roll"
            ),
            ResolutionType.ATTACK_ROLL,
        )
        affected_targets = int(
            session_state.get(profile_widget_key(widget_prefix, "affected_targets"), 1)
        )
        features = available_features(
            frozenset(
                feature
                for feature in FEATURE_ORDER
                if session_state.get(feature_widget_key(widget_prefix, feature), False)
            ),
            resolution,
            affected_targets=affected_targets,
        )
        profiles.append(
            AttackProfile(
                session_state.get(
                    profile_widget_key(widget_prefix, "name"), default_name
                ),
                (
                    int(
                        session_state.get(
                            profile_widget_key(widget_prefix, "attack_bonus"), 5
                        )
                    )
                    if resolution is ResolutionType.ATTACK_ROLL
                    else None
                ),
                session_state.get(
                    profile_widget_key(widget_prefix, "damage_formula"), "1d8+3"
                ),
                int(
                    session_state.get(
                        profile_widget_key(widget_prefix, "attacks_per_round"), 1
                    )
                ),
                affected_targets,
                AttackRollMode(
                    str(
                        session_state.get(
                            profile_widget_key(widget_prefix, "attack_roll_mode"),
                            "Normal",
                        )
                    ).lower()
                ),
                session_state.get(
                    profile_widget_key(widget_prefix, "active_rounds"), ""
                ),
                resolution,
                (
                    int(
                        session_state.get(
                            profile_widget_key(widget_prefix, "save_dc"), 13
                        )
                    )
                    if resolution is ResolutionType.SAVING_THROW
                    else None
                ),
                (
                    SuccessfulSaveDamage.HALF_DAMAGE
                    if session_state.get(
                        profile_widget_key(widget_prefix, "successful_save_damage"),
                        "No damage",
                    )
                    == "Half damage"
                    else SuccessfulSaveDamage.NO_DAMAGE
                ),
                features,
            )
        )
    return _build_config_from_profiles(
        session_state.get(f"{prefix}-build-name", default_build_name),
        tuple(profiles),
    )


def _default_second_build_from_state() -> BuildConfig:
    """Build hidden Build B from existing session-state values or widget defaults."""
    return _build_from_state("second", "Build B")


def _share_configuration_fingerprint(configuration: SharedConfiguration) -> str:
    return serialize_shared_configuration(configuration)


def _share_component_requested_creation(result: object) -> str | None:
    value = getattr(result, "create_share", None)
    if value is not None:
        return str(value)
    if isinstance(result, dict):
        value = result.get("create_share")
        if value is not None:
            return str(value)
    return None


def _mount_unified_share_component(data: dict[str, object]) -> object:
    share_toolbar = _get_share_toolbar_component()
    return share_toolbar(
        data=data,
        key="unified-share-configuration",
        on_create_share_change=lambda: None,
    )


def _render_share_configuration_button() -> None:
    import streamlit as st

    state = getattr(st, "session_state", {})
    base_data: dict[str, object] = {
        "url": "",
        "creating": False,
        "disabled": False,
        "message": state.pop(SHARE_ERROR_MESSAGE_KEY, ""),
    }

    if _configuration_errors_for_current_state():
        state.pop(GENERATED_SHARE_URL_KEY, None)
        state.pop(GENERATED_SHARE_FINGERPRINT_KEY, None)
        base_data.update(
            {"disabled": True, "message": "Fix field errors before sharing."}
        )
        _mount_unified_share_component(base_data)
        return

    share_store = get_streamlit_share_store()
    if share_store is None:
        state.pop(GENERATED_SHARE_URL_KEY, None)
        state.pop(GENERATED_SHARE_FINGERPRINT_KEY, None)
        base_data.update(
            {
                "disabled": True,
                "message": "Share links are not configured for this deployment.",
            }
        )
        _mount_unified_share_component(base_data)
        caption = getattr(st, "caption", None)
        if caption is not None:
            caption("Share links are not configured for this deployment.")
        return

    try:
        configuration = _current_shared_configuration()
        fingerprint = _share_configuration_fingerprint(configuration)
    except SharedConfigurationError:
        state.pop(GENERATED_SHARE_URL_KEY, None)
        state.pop(GENERATED_SHARE_FINGERPRINT_KEY, None)
        base_data.update(
            {"disabled": True, "message": "Fix field errors before sharing."}
        )
        _mount_unified_share_component(base_data)
        return

    stored_fingerprint = state.get(GENERATED_SHARE_FINGERPRINT_KEY)
    if stored_fingerprint is None and state.get(GENERATED_SHARE_URL_KEY):
        state[GENERATED_SHARE_FINGERPRINT_KEY] = fingerprint
    elif stored_fingerprint != fingerprint:
        state.pop(GENERATED_SHARE_URL_KEY, None)
        state[GENERATED_SHARE_FINGERPRINT_KEY] = fingerprint

    share_url = state.get(GENERATED_SHARE_URL_KEY, "")
    base_data["url"] = share_url
    result = _mount_unified_share_component(base_data)
    trigger_value = _share_component_requested_creation(result)

    if not trigger_value or share_url:
        return
    if state.get(PROCESSED_SHARE_TRIGGER_KEY) == trigger_value:
        return

    state[PROCESSED_SHARE_TRIGGER_KEY] = trigger_value
    try:
        share_id = save_shared_configuration(share_store, configuration)
        state[GENERATED_SHARE_URL_KEY] = build_short_share_url(
            getattr(getattr(st, "context", None), "url", ""), share_id
        )
        state[GENERATED_SHARE_FINGERPRINT_KEY] = fingerprint
        rerun = getattr(st, "rerun", None)
        if rerun is not None:
            rerun()
    except (SharedConfigurationError, ShareStoreError):
        state.pop(GENERATED_SHARE_URL_KEY, None)
        state[SHARE_ERROR_MESSAGE_KEY] = (
            "Unable to create a share link right now. Try again later."
        )
        st.error("Unable to create a share link right now. Try again later.")


def main() -> None:
    """Render the Streamlit simulation page."""
    import streamlit as st

    configure_page()
    load_shared_configuration_from_query()
    if getattr(st, "session_state", {}).pop(LOADED_SHARED_CONFIG_MESSAGE_KEY, False):
        st.success("Shared configuration loaded.")
    if message := getattr(st, "session_state", {}).pop(
        INVALID_SHARED_CONFIG_MESSAGE_KEY, None
    ):
        st.warning(message)
    st.title(APP_TITLE)
    st.write(
        "Compare two named DnD combat builds against the same target Armor "
        "Class, round count, and simulation count."
    )
    _render_share_configuration_button()

    with _render_section_container():
        st.subheader("Shared scenario")
        scenario_row = st.columns(5)
        target_armor_class = scenario_row[0].number_input(
            "Target Armor Class",
            min_value=1,
            value=15,
            step=1,
            key=SCENARIO_WIDGET_KEYS["target_armor_class"],
        )
        enemy_save_bonus = scenario_row[1].number_input(
            "Enemy Save Bonus",
            value=3,
            step=1,
            key=SCENARIO_WIDGET_KEYS["enemy_save_bonus"],
        )
        rounds = scenario_row[2].number_input(
            "Number of rounds",
            min_value=1,
            value=4,
            step=1,
            key=SCENARIO_WIDGET_KEYS["rounds"],
        )
        simulations = scenario_row[3].number_input(
            "Number of simulations",
            min_value=1,
            value=10_000,
            step=1,
            key=SCENARIO_WIDGET_KEYS["simulations"],
        )
        seed = scenario_row[4].number_input(
            "Random seed", value=20240721, step=1, key=SCENARIO_WIDGET_KEYS["seed"]
        )
        scenario_pre_errors = validation_errors_by_key(
            validate_scenario_fields(
                ScenarioConfig(
                    target_armor_class=int(target_armor_class),
                    enemy_save_bonus=int(enemy_save_bonus),
                    rounds=int(rounds),
                    simulations=int(simulations),
                )
            )
        )
        for key in (
            SCENARIO_WIDGET_KEYS["target_armor_class"],
            SCENARIO_WIDGET_KEYS["rounds"],
            SCENARIO_WIDGET_KEYS["simulations"],
        ):
            _field_error(scenario_pre_errors, key)

        compare_enabled = st.toggle(
            "Compare with another build",
            value=False,
            key=COMPARE_WIDGET_KEY,
        )

    scenario = ScenarioConfig(
        target_armor_class=int(target_armor_class),
        enemy_save_bonus=int(enemy_save_bonus),
        rounds=int(rounds),
        simulations=int(simulations),
    )

    if compare_enabled:
        pre_render_errors = validation_errors_by_key(
            [
                *validate_build_fields(
                    _build_from_state("first", "Build A"), prefix="first"
                ),
                *validate_build_fields(
                    _build_from_state("second", "Build B"), prefix="second"
                ),
            ]
        )
        build_columns = st.columns(2)
        with build_columns[0]:
            first_build = _build_inputs("first", "Build A", pre_render_errors)
        with build_columns[1]:
            second_build = _build_inputs("second", "Build B", pre_render_errors)

        current_errors = [
            *validate_scenario_fields(scenario),
            *validate_build_fields(first_build, prefix="first"),
            *validate_build_fields(second_build, prefix="second"),
        ]
        if current_errors:
            st.warning("Fix the highlighted fields before comparing builds.")
        if st.button("Compare Builds", disabled=bool(current_errors)):
            inputs = ComparisonInputs(
                first_build=first_build,
                second_build=second_build,
                scenario=scenario,
                seed=int(seed),
            )
            try:
                comparison = run_comparison_from_inputs(inputs)
            except (ValueError, SharedConfigurationError) as error:
                st.error(_friendly_validation_message(error))
            else:
                _render_comparison_results(comparison)
    else:
        pre_render_errors = validation_errors_by_key(
            validate_build_fields(_build_from_state("first", "Build A"), prefix="first")
        )
        first_build = _build_inputs("first", "Build A", pre_render_errors)

        current_errors = [
            *validate_scenario_fields(scenario),
            *validate_build_fields(first_build, prefix="first"),
        ]
        if current_errors:
            st.warning("Fix the highlighted fields before running the simulation.")
        if st.button("Run Simulation", disabled=bool(current_errors)):
            inputs = SingleBuildInputs(
                build=first_build,
                scenario=scenario,
                seed=int(seed),
            )
            try:
                result = run_single_build_from_inputs(inputs)
            except (ValueError, SharedConfigurationError) as error:
                st.error(_friendly_validation_message(error))
            else:
                _render_single_build_results(first_build, result)


if __name__ == "__main__":
    main()
