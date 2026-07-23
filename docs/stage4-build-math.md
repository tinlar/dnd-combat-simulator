# Stage 4 Build Math

## Purpose

`BuildMathDefaults` provides optional build-level defaults for attack resolution:

- Attack bonus
- Save DC

Damage is intentionally entered as a complete per-profile **Damage Formula** such
as `1d8+3`, `2d6+1d4+5`, or `4d6kh3+2`. There is no separate build-level flat
damage setting.

## Formulas

```text
attack bonus =
    ability modifier
    + proficiency bonus
    + attack bonus adjustment

save DC =
    8
    + ability modifier
    + proficiency bonus
    + save DC adjustment
```

The initial defaults are ability modifier `3`, proficiency bonus `2`, and zero
adjustments. Those values calculate attack bonus `5` and save DC `13`.

## Compatibility policy

Existing configurations retain their current results while new visible-interface
attacks can opt into Build Setup defaults.

- Existing programmatic `AttackProfile` objects default to manual attack bonus
  and save DC values.
- Legacy shared links default to manual values and do not silently begin
  inheriting build values.
- Legacy links that contain removed build damage inheritance fields are migrated
  by appending the legacy flat damage value to the profile formula only when that
  profile had enabled the build modifier.
- New attacks created in the visible interface inherit Build Setup attack bonus
  or Save DC defaults when applicable.
- Each attack independently chooses inheritance or manual values for attack
  bonus and Save DC.
- Manual fallback values are preserved while inheritance is enabled and become
  authoritative whenever the corresponding inheritance option is disabled.
- Build A and Build B remain isolated, including their Build Setup values and
  per-attack inheritance choices.
- Shared configurations preserve attack bonus and Save DC inheritance choices and
  manual fallback values without changing the shared configuration version.
- Effective attack bonus and Save DC values participate in cache identity so
  cached simulation requests reflect inherited Build Setup changes.

## Serialized fields

Serialized shared links include a build-level `math_defaults` object under each
of `build_a` and `build_b` with exactly these stored fields:

- `ability_modifier`
- `proficiency_bonus`
- `attack_bonus_adjustment`
- `save_dc_adjustment`

Derived values such as attack bonus and Save DC are not serialized. Newly saved
configurations do not serialize any build damage modifier field. Legacy links
that omit `math_defaults` are accepted and default to `BuildMathDefaults()`.

## Visible Build Setup controls

The Build Setup section contains these editable controls:

- **Ability modifier**
- **Proficiency bonus**
- **Other attack bonus**
- **Other Save DC bonus**

The calculated, read-only display values are:

- **Attack bonus**
- **Save DC**

Attack-roll profiles can inherit the calculated Attack Bonus. Saving-throw
profiles can inherit the calculated Save DC. Automatic-damage profiles do not
show either inheritance row. Damage is always edited as a complete formula on its
own row and is evaluated directly by the dice parser.

## Scope exclusions

Stage 4 does not include accounts, authentication, classes, subclasses,
character levels, a full character builder, character sheets, persistent personal
build libraries, or new combat mechanics.
