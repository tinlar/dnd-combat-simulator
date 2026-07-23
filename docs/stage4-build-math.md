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
