# Stage 4 Build Math

## Purpose

`BuildMathDefaults` currently provides optional build-level defaults for:

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

Existing configurations retain their current results while new visible-interface
attacks can opt into Build Setup defaults.

- Existing programmatic `AttackProfile` objects default to manual attack bonus,
  save DC, and damage modifier values.
- Legacy shared links default to manual values and do not silently begin
  inheriting build values.
- New attacks created in the visible interface inherit Build Setup values by
  default.
- Each attack independently chooses inheritance or manual values for attack
  bonus, save DC, and damage modifier.
- Manual fallback values are preserved while inheritance is enabled and become
  authoritative whenever the corresponding inheritance option is disabled.
- Build A and Build B remain isolated, including their Build Setup values and
  per-attack inheritance choices.
- Shared configurations preserve the inheritance choices and manual fallback
  values without changing the shared configuration version.
- Effective values participate in cache identity so cached simulation requests
  reflect inherited Build Setup changes.

## Scope exclusions

Stage 4 does not include:

- User accounts
- Authentication
- Classes
- Subclasses
- Character levels
- A full character builder
- A character sheet
- Persistent personal build libraries

## Stage 4.2: Configuration and sharing transport

Stage 4.2 added `BuildMathDefaults` to the simulator's configuration and sharing
data path without changing combat behavior. `BuildConfig` stores a trailing
`math_defaults` value so existing positional construction remains compatible
while new call sites can use explicit keywords. `SharedBuildConfiguration` also
stores independent trailing defaults for Build A and Build B.

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

Stage 4.2 did not yet expose visible controls; those controls were added in Stage
4.3. Shared defaults were transported through hidden, stable session-state keys
for each build, then reconstructed into `BuildConfig` when the app reran or
re-shared a configuration. Build A and Build B values stayed isolated throughout
hydration, reconstruction, and serialization.

The simulator remains conservative about cache identity: `BuildMathDefaults` is a
frozen field on `BuildConfig`, so it participates in canonical request equality,
hashing, pickling, and Streamlit cache hashing. `SIMULATION_CACHE_VERSION` was
incremented to invalidate cache entries created before the schema change.

Stage 4.2 transported the values without applying inheritance; inheritance was
added in Stage 4.4. At the time, explicit attack-profile values continued to
supply simulation output, random-number ordering, attack resolution, saving-throw
resolution, damage formulas, triggers, and managed resources.

Accounts, authentication, classes, subclasses, character levels, character
sheets, inventories, spell lists, persistent build libraries, browser storage,
and database storage remain out of scope.

## Stage 4.3: Visible Build Setup controls

Stage 4.3 exposed the existing `BuildMathDefaults` data in a compact,
always-visible **Build Setup** section for each build. The section is rendered
after **Build name** and before **Add Attack** and the attack-profile cards, so
the build-level values are visible before users edit individual attacks.

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
initialization warnings. Sharing again serializes the edited
`BuildConfig.math_defaults` through the Stage 4.2 JSON shape without changing the
shared configuration version or schema.

Stage 4.3 kept explicit attack values authoritative because optional per-attack
inheritance was added later in Stage 4.4. Attack-profile controls for Attack
Bonus, Save DC, Damage Formula, attacks per round, resolution type, attack-roll
mode, features, triggers, and resource costs still provided the values used by
the simulator during that pass. Editing Build Setup did not rewrite
attack-profile session state, change simulation results, change random-number
consumption, or alter trigger or managed-resource behavior.

Stage 4.3 did not add accounts, authentication, classes, subclasses, character
levels, preset libraries, browser storage, database storage, or any new combat
mechanics. It also did not change `SIMULATION_CACHE_VERSION`; Stage 4.2 already
handled the cache schema update, and Stage 4.3 ensured the visible controls
attached the edited defaults to `BuildConfig` so the existing canonical cache
identity remained accurate.

## Stage 4.4: Optional per-attack Build Setup inheritance

Stage 4.4 added per-attack choices to inherit the build's calculated Attack
Bonus, Save DC, and Damage Modifier. The stored profile remains the configuration
source of truth and keeps its manual fallback values while inheritance is enabled.

Stored attack-profile fields:

- `use_build_attack_bonus`
- `use_build_save_dc`
- `use_build_damage_modifier`

Programmatic `AttackProfile` construction and legacy shared links default all
three fields to `False` for manual compatibility. New attacks created in the
visible interface default all three fields to `True`, with a base `1d8` formula so
the fresh effective result remains `+5` to hit and `1d8+3` damage under the
standard Build Setup.

Effective values are resolved centrally by `resolve_attack_profile_values()`:

- Attack-roll profiles use `BuildMathDefaults.attack_bonus` only when
  `use_build_attack_bonus` is true; otherwise they use the stored manual
  `attack_bonus`.
- Saving-throw profiles use `BuildMathDefaults.save_dc` only when
  `use_build_save_dc` is true; otherwise they use the stored manual `save_dc`.
- Damage uses the stored formula with surrounding whitespace stripped. When
  `use_build_damage_modifier` is true, the calculated build damage modifier is
  appended once as a signed constant. `+0` is omitted.

Critical hits continue doubling only damage dice according to the existing engine
rules; the inherited build damage modifier is a constant and is not doubled. Half
damage continues using the existing total-damage halving behavior and rounding
rule.

Shared configuration version remains unchanged because the new fields are
additive. Modern shared configurations serialize all three booleans, while legacy
links that omit them remain manual. Cache identity was incremented so inherited
effective values participate in cached simulation requests. Build A and Build B
each resolve attack inheritance against their own Build Setup values, with no
cross-build state sharing.

This stage did not add accounts, authentication, classes, subclasses, character
levels, character sheets, equipment inventories, spell lists, persistent preset
libraries, or browser/database storage.

## Stage 4 completion

Stage 4 now provides Build Setup values, calculated Attack Bonus, calculated
Damage Modifier, calculated Save DC, per-attack optional inheritance, manual
fallback preservation, sharing compatibility, manual defaults for legacy links,
independent Build A and Build B behavior, and cache identity support for effective
values.

Stage 4 remains intentionally limited. It adds no accounts, authentication,
classes, subclasses, character levels, full character builder, or persistent
personal preset library.
