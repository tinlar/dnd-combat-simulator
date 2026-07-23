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
