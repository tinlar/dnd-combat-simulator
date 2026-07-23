# Stage 4 Build Math

## Purpose

`BuildMathDefaults` will eventually provide optional build-level defaults for:

- Attack bonus
- Damage modifier
- Save DC

The model is limited to shared numerical defaults for combat math. It is not a
class system, character-sheet model, or broader rules engine.

## Formulas

```text
attack bonus =
    ability modifier
    + proficiency bonus
    + attack bonus adjustment

damage modifier =
    ability modifier
    + damage bonus adjustment

save DC =
    8
    + ability modifier
    + proficiency bonus
    + save DC adjustment
```

The initial defaults are ability modifier `3`, proficiency bonus `2`, and zero
adjustments. Those values calculate the current common starting values of attack
bonus `5`, damage modifier `3`, and save DC `13`.

## Compatibility policy

Existing configurations must retain their current results.

When inheritance is introduced in a later Stage 4 pull request:

- Existing attacks will remain manual overrides by default.
- Existing shared links must not silently begin inheriting build values.
- New inheritance behavior must be explicit.
- An attack may inherit a build value or use a manual override.
- Different attacks in the same build may use different modes.
- Build A and Build B must remain isolated.

Until that explicit inheritance work exists, existing explicit attack values remain
authoritative, including attack bonus, save DC, and damage dice. Sharing and
cache identity are unchanged in this stage.

## Scope exclusions

Stage 4 does not include:

- User accounts
- Classes
- Subclasses
- Character levels
- A full character builder
- A character sheet
- Persistent personal build libraries

## Stage 4.2: Configuration and sharing transport

Stage 4.2 carries `BuildMathDefaults` through the simulator's configuration and
sharing data path without changing combat behavior. `BuildConfig` now stores a
trailing `math_defaults` value so existing positional construction remains
compatible while new call sites can use explicit keywords. `SharedBuildConfiguration`
also stores independent trailing defaults for Build A and Build B.

Serialized shared links include a build-level `math_defaults` object under each
of `build_a` and `build_b` with exactly these stored fields:

- `ability_modifier`
- `proficiency_bonus`
- `attack_bonus_adjustment`
- `damage_bonus_adjustment`
- `save_dc_adjustment`

Derived values such as attack bonus, damage modifier, and save DC are not
serialized. Legacy links that omit the object are accepted and default to
`BuildMathDefaults()`. The shared configuration version remains unchanged because
this is additive metadata and older applications ignore unknown build-level
fields.

No visible controls exist yet. Shared defaults are transported through hidden,
stable session-state keys for each build, then reconstructed into `BuildConfig`
when the app reruns or re-shares a configuration. Build A and Build B values are
kept isolated throughout hydration, reconstruction, and serialization.

The simulator remains conservative about cache identity: `BuildMathDefaults` is a
frozen field on `BuildConfig`, so it participates in canonical request equality,
hashing, pickling, and Streamlit cache hashing. `SIMULATION_CACHE_VERSION` was
incremented to invalidate cache entries created before the schema change.

Explicit attack-profile values remain authoritative. Build math defaults do not
affect simulation output, random-number ordering, attack resolution, saving-throw
resolution, damage formulas, triggers, or managed resources in Stage 4.2. No
inheritance exists yet.

Accounts, authentication, classes, subclasses, character levels, character
sheets, inventories, spell lists, persistent build libraries, browser storage,
and database storage remain out of scope.

## Stage 4.3: Visible Build Setup controls

Stage 4.3 exposes the existing `BuildMathDefaults` data in a compact, always-visible
**Build Setup** section for each build. The section is rendered after **Build name**
and before **Add Attack** and the attack-profile cards, so the build-level values
are visible before users edit individual attacks.

The editable controls use these exact user-facing labels:

- **Ability modifier**
- **Proficiency bonus**
- **Other attack bonus**
- **Other damage bonus**
- **Other Save DC bonus**

The calculated, read-only display values use these exact labels:

- **Attack bonus**
- **Damage modifier**
- **Save DC**

Fresh builds use `BuildMathDefaults()` values: ability modifier `+3`, proficiency
bonus `+2`, and `+0` for each other bonus. The calculated displays therefore show
attack bonus `+5`, damage modifier `+3`, and Save DC `13`. Signed values are shown
for attack bonus and damage modifier, while Save DC is shown as a normal integer.

The UI presents the same formulas supplied by the pure model:

```text
Attack bonus = ability modifier + proficiency bonus + other attack bonus
Damage modifier = ability modifier + other damage bonus
Save DC = 8 + ability modifier + proficiency bonus + other Save DC bonus
```

Build A and Build B are fully isolated. Each control binds to the Stage 4.2 stable
session-state key returned by `build_math_state_key(build_prefix, field)`, such as
`first-build-math-ability-modifier` or
`second-build-math-save-dc-adjustment`. Comparison mode can be toggled off without
erasing hidden Build B values, and toggling comparison back on restores those
values from session state.

Shared-link hydration remains session-state safe. If a stable key already exists,
the widget binds to that key without also passing a competing default value. If a
key is absent, the widget receives the corresponding `BuildMathDefaults()` field
default. This preserves hydrated shared-link values and avoids Streamlit widget
initialization warnings. Sharing again serializes the edited `BuildConfig.math_defaults`
through the Stage 4.2 JSON shape without changing the shared configuration version
or schema.

Explicit attack values remain authoritative in Stage 4.3. Attack-profile controls
for Attack Bonus, Save DC, Damage Formula, attacks per round, resolution type,
attack-roll mode, features, triggers, and resource costs still provide the values
used by the simulator. Editing Build Setup does not rewrite attack-profile session
state, does not change simulation results, does not change random-number consumption,
and does not alter trigger or managed-resource behavior.

No inheritance is active in this stage. Stage 4.4 will address optional per-attack
inheritance separately. This pull request does not add accounts, authentication,
classes, subclasses, character levels, preset libraries, browser storage, database
storage, or any new combat mechanics. It also does not change
`SIMULATION_CACHE_VERSION`; Stage 4.2 already handled the cache schema update, and
Stage 4.3 simply ensures the visible controls attach the edited defaults to
`BuildConfig` so the existing canonical cache identity remains accurate.

## Stage 4.4: Optional per-attack Build Setup inheritance

Stage 4.4 lets each attack profile independently choose whether to inherit the build's calculated Attack Bonus, Save DC, and Damage Modifier. The stored profile remains the configuration source of truth and keeps its manual fallback values while inheritance is enabled.

Stored attack-profile fields:

- `use_build_attack_bonus`
- `use_build_save_dc`
- `use_build_damage_modifier`

Programmatic `AttackProfile` construction and legacy shared links default all three fields to `False` for manual compatibility. New attacks created in the visible interface default all three fields to `True`, with a base `1d8` formula so the fresh effective result remains `+5` to hit and `1d8+3` damage under the standard Build Setup.

Effective values are resolved centrally by `resolve_attack_profile_values()`:

- Attack-roll profiles use `BuildMathDefaults.attack_bonus` only when `use_build_attack_bonus` is true; otherwise they use the stored manual `attack_bonus`.
- Saving-throw profiles use `BuildMathDefaults.save_dc` only when `use_build_save_dc` is true; otherwise they use the stored manual `save_dc`.
- Damage uses the stored formula with surrounding whitespace stripped. When `use_build_damage_modifier` is true, the calculated build damage modifier is appended once as a signed constant. `+0` is omitted.

Critical hits continue doubling only damage dice according to the existing engine rules; the inherited build damage modifier is a constant and is not doubled. Half damage continues using the existing total-damage halving behavior and rounding rule.

Shared configuration version remains unchanged because the new fields are additive. Modern shared configurations serialize all three booleans, while legacy links that omit them remain manual. Cache identity is incremented so inherited effective values participate in cached simulation requests. Build A and Build B each resolve attack inheritance against their own Build Setup values, with no cross-build state sharing.

This stage does not add accounts, authentication, classes, subclasses, character levels, character sheets, equipment inventories, spell lists, persistent preset libraries, or browser/database storage.
