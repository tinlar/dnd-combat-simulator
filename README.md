# DnD Combat Simulator

Initial project setup for a browser-based DnD combat simulator built with Python 3.12 and Streamlit.

## Combat rules

The simulator includes Streamlit-independent logic for resolving damage profiles as attack rolls, saving throws, or automatic damage. Attack-roll profiles use an attack bonus, target Armor Class, damage formulas such as `1d8+3`. Saving-throw profiles use a Save DC, the shared Enemy Save Bonus, damage formulas, and a successful-save damage behavior. Automatic-damage profiles use damage formulas, attacks per active round, affected targets, and Active Rounds without requiring Attack Bonus or Save DC.

Attack-roll resolution follows these rules:

- Choose an attack roll mode: normal, advantage, or disadvantage. Normal rolls `1d20`; advantage rolls `2d20` and selects the higher die; disadvantage rolls `2d20` and selects the lower die. The selected die is added to the attack bonus to produce the modified attack total.
- A selected natural 1 automatically misses, even if the modified total would meet the target Armor Class.
- A selected natural 20 automatically hits and is a critical hit.
- Any other attack hits when the modified attack total equals or exceeds the target Armor Class.
- A normal hit evaluates the listed damage formula once.
- A critical hit evaluates the dice-pool portion twice and applies the formula's flat modifier once. For example, `1d8+3` rolls two independent `1d8` pools and adds `3` once on a critical hit.
- A miss deals zero damage.
- Final damage cannot be below zero.

Saving-throw resolution follows these rules:

- Roll `1d20` and add the shared Enemy Save Bonus. The same enemy save bonus applies to all saving throws for now.
- The enemy succeeds when the total equals or exceeds the Save DC, and fails when the total is below the Save DC.
- On a failed save, the profile deals full damage.
- On a successful save, the profile deals either no damage or half damage depending on its **Successful Save Damage** setting. Half damage rounds down.
- Formula modifiers are included before halving.
- Saving throws cannot critically hit. Natural 1 and natural 20 do not automatically fail or succeed.
- Final damage cannot be below zero.

Automatic-damage resolution follows these rules:

- No d20 is rolled: the simulator does not make an attack roll or a saving throw.
- Damage is always applied and automatic damage cannot critically hit.
- Damage is rolled separately for each attack use and each affected target.
- The formula flat modifier is applied to each automatic damage roll.
- Final damage cannot be below zero.
- Automatic damage applications are tracked separately and are excluded from attack-roll hit-rate and saving-throw rate denominators.

Automatic-damage examples:

- Acid Arrow follow-up: **Automatic Damage**, `1` attack use, `1` affected target, **Active Rounds** `2`.
- Three Magic Missile darts: **Automatic Damage**, `3` attacks per active round, `1` affected target per attack, **Active Rounds** `1`.
- Automatic effect damaging three targets: **Automatic Damage**, `1` attack per active round, `3` affected targets.

Single-profile resolution returns the resolution outcome, success state, critical-hit state where meaningful, and damage dealt. Random number generation can be injected for deterministic tests.

## Multi-target attack profiles

Every attack profile has an **Affected Targets** value. It defaults to `1`, must be a whole number of at least `1`, and applies independently to that profile. All affected targets currently share the scenario's Target Armor Class and Enemy Save Bonus.

Each use of an attack profile affects its configured number of targets. **Attacks per round** still controls how many times the profile is used during each active round; **Affected Targets** controls how many target resolutions happen for each use.

Multi-target attack rolls and multi-target saving throws intentionally consume random rolls in different orders:

- Attack-roll profiles resolve each target independently. For each simulation, round, attack profile, profile use, and target, the simulator rolls that target's attack roll, applies advantage or disadvantage for that target if configured, determines hit and critical status for that target, and rolls that target's damage separately if it hits. For example, a profile with `2` attacks per round and `3` affected targets resolves `6` separate target attack rolls per active round.
- Saving-throw profiles roll one shared damage result for each use of the attack profile, then roll an independent saving throw for every affected target. Each target applies the same shared base damage according to its own save result: full damage on a failed save, zero damage on a successful save configured for **No damage**, or half damage rounded down on a successful save configured for **Half damage**. For example, a saving-throw profile with `1` attack per round and `4` affected targets rolls damage once, rolls `4` separate saving throws, and applies that one damage result separately to all `4` targets.
- Automatic-damage profiles resolve each target independently without rolling a d20. For each simulation, round, attack profile, profile use, and target, the simulator rolls that target's damage separately and applies the full result automatically. For example, a profile with `3` attacks per active round and `1` affected target resolves `3` automatic damage applications per active round.

Total damage metrics include damage dealt across all affected targets. Per-target metrics such as **Average damage per target per round** are included so single-target effectiveness can be compared separately from total multi-target damage.


## Feats and Features

Every attack profile includes a collapsed **Feats and Features** expander after its normal configuration fields. The expander contains stable, profile-specific checkboxes for **Elven Accuracy**, **Great Weapon Fighting**, **Tavern Brawler**, **Stop on Miss**, and **Potent Cantrip**. The Streamlit controls are arranged across responsive columns and wrap into additional rows as the feature list grows, so single-build and comparison views use the available width without forcing one long vertical list. Selected features are stored on the attack profile as an extensible feature set, and the per-profile detailed results show selected features in that order or **None** when no feature is selected. **Elven Accuracy**, **Great Weapon Fighting**, and **Tavern Brawler** are available only for Attack Roll profiles. **Potent Cantrip** is available for Attack Roll and Saving Throw profiles, but not Automatic Damage profiles. **Stop on Miss** is available only for Attack Roll profiles with exactly one affected target; Saving Throw, Automatic Damage, and multi-target Attack Roll profiles cannot use it because chained attacks should be modeled as single-target profile uses.

Feature behavior is independent from Streamlit:

- **Elven Accuracy** applies only to attack-roll profiles using Advantage. The simulator rolls the first advantage d20, the second advantage d20, then the Elven Accuracy replacement die. It rerolls the lower original die once; if the original dice tie, the second die is rerolled for deterministic behavior. The final selected d20 is the higher of the original kept die and the replacement die. Critical hits are based only on that final selected natural d20. Elven Accuracy is disabled in the interface for Saving Throw and Automatic Damage profiles, and programmatic non-attack-roll profiles using it are rejected with a readable validation error.
- **Great Weapon Fighting** applies to Attack Roll profile damage dice only. It is disabled in the interface for Saving Throw and Automatic Damage profiles, and programmatic non-attack-roll profiles using it are rejected with a readable validation error. Any damage die with a final natural face of 1 or 2 contributes 3 damage instead, while natural 3 and higher faces contribute their natural value. It does not affect flat modifiers, d20 attack rolls, d20 saving throws, or whether a natural die face triggers an explosion.
- **Tavern Brawler** applies to Attack Roll profile damage dice only. It is disabled in the interface for Saving Throw and Automatic Damage profiles, and programmatic non-attack-roll profiles using it are rejected with a readable validation error. After formula reroll clauses have produced an accepted natural face, a face of 1 is rerolled once. The replacement natural face must be used, even if it is another 1, and formula reroll clauses do not apply to that replacement.
- **Potent Cantrip** applies to Attack Roll and Saving Throw profiles only. For an Attack Roll profile, a miss rolls the profile's normal noncritical damage and deals half of that result, rounded down; it never turns a miss into a critical hit. For a Saving Throw profile, a failed save still deals full normal damage, while a successful save deals half normal damage rounded down. This overrides **Successful Save Damage: No Damage** for successful saves. Multi-target Saving Throw profiles still roll damage once per profile use and share that roll across all affected targets before applying full or half damage to each target. Potent Cantrip is disabled in the interface for Automatic Damage profiles, and programmatic Automatic Damage profiles using it are rejected with a readable validation error.

For every initial or explosion-generated damage die, feature processing order is:

1. Roll the natural face.
2. Apply Damage Formula reroll clauses until an accepted result is produced.
3. Apply Tavern Brawler once if the accepted result is 1.
4. Check whether the final natural face triggers an explosion.
5. Apply Great Weapon Fighting to determine the die's damage contribution.
6. Add the contribution to the current explosion chain.
7. Resolve any generated explosion die using the same process.
8. Apply keep/drop rules to completed chain totals.
9. Apply the formula's flat modifier once.

For multi-target Saving Throw profiles, damage is still rolled once per profile use and shared by all affected targets; Great Weapon Fighting and Tavern Brawler are applied during that single shared damage roll. Automatic Damage profiles apply damage-die features normally and never apply Elven Accuracy.



### Stop on Miss

Use **Stop on Miss** for chained attacks where each successful attack permits the next attack and the first miss ends that round's chain. For example, model a Chromatic Orb chain as:

- Resolution Type: Attack Roll
- Attacks per Active Round: 4
- Affected Targets: 1
- Stop on Miss: enabled

The simulator resolves the profile's attacks in order each active round. If attack 1, 2, or 3 misses, all later attacks from that same profile are skipped for that round only; the chain resets at the beginning of the next active round. Skipped profile uses do not consume attack rolls or damage rolls and are reported separately from actual profile uses.

## Damage simulations

The project also includes Streamlit-independent simulation logic for repeated damage estimates. A simulation uses the existing single-attack combat resolver and runs one or more distinct attack profiles per round for a requested number of rounds. Each attack profile has its own attack name, attack bonus, damage formula, attacks per round, attack roll mode, and optional Active Rounds expression. That full combat is repeated for the requested number of simulations.

Simulation inputs are:

- One or more reusable attack profiles, each with:
  - Attack name
  - Resolution Type (`Attack Roll`, `Saving Throw`, or `Automatic Damage`), defaulting to attack roll for backward compatibility
  - Attack bonus for attack-roll profiles
  - Save DC for saving-throw profiles
  - Successful Save Damage for saving-throw profiles, defaulting to no damage
  - No Attack Bonus, Attack Roll Mode, Save DC, or Successful Save Damage requirement for automatic-damage profiles
  - Damage Formula, including any flat modifier
  - Attacks per round, defaulting to 1
  - Affected Targets, defaulting to 1
  - Attack roll mode for attack-roll profiles, defaulting to normal
  - Active Rounds, defaulting to blank for every round
  - Feats and Features, defaulting to none
- Target Armor Class
- Enemy Save Bonus, defaulting to +3
- Number of rounds
- Number of simulations

Active Rounds controls which rounds use an attack profile. Blank means the profile is active every scenario round. A single value such as `1` means round 1 only; a range such as `1-5` means rounds 1 through 5; and a comma-separated expression such as `1, 3-5, 8` means rounds 1, 3, 4, 5, and 8. Optional whitespace is allowed around commas and ranges. Duplicate or overlapping values such as `1-3, 2-4` are deduplicated and processed in ascending order as rounds 1, 2, 3, and 4. Round numbers must be positive integers, reversed ranges such as `5-3` are invalid, and rounds greater than the scenario's round count are valid but ignored during that simulation. During each simulated round, only profiles with blank Active Rounds or an Active Rounds set containing the current round are resolved, using that profile's attacks-per-round value. A build may intentionally have zero attacks in a round. Existing attack profiles without Active Rounds remain valid and behave as active every round.

Simulation results summarize aggregate outcomes without retaining every individual attack result. The returned summary includes simulations run, rounds per simulation, average attacks per round, total attacks made, total target resolutions, automatic damage applications, average automatic damage per application, average total damage per simulation across all affected targets, average total damage per round across all affected targets, average damage per target per round, attack-roll hit rate, critical hit rate for attack rolls, failed save rate, successful save rate, and the minimum and maximum total damage observed in a simulation. Results also include a per-attack-profile breakdown with each profile's affected targets, selected feats and features, total attacks, total target resolutions, average damage, average damage per target per round, attack-roll hit and critical-hit rates where meaningful, and saving-throw failed/successful save rates where meaningful. A per-round breakdown reports each round number, average damage, average attacks, full damage success percentage, critical-hit percentage, failed-save percentage, and successful-save percentage. Summary metrics include first-round burst damage, average damage after round 1, highest-damage round, highest-round average damage, average damage per round, and average total damage. The Streamlit comparison summary does not calculate a misleading combined success rate across attack rolls, saving throws, and automatic damage. Resolution-specific rates remain in the per-profile breakdown.

Random number generation can be injected so simulations are deterministic in tests. For attack-roll profiles, random rolls are consumed by simulation, round, attack profile, attack use, target, attack roll, then damage roll if that target hits. For saving-throw profiles with multiple affected targets, random rolls are consumed by simulation, round, attack profile, attack use, one shared damage roll, then one saving throw for each target. For automatic-damage profiles, random rolls are consumed by simulation, round, attack profile, attack use, target, then that target's damage roll. Rounds, attacks per round, affected targets, and simulation counts must all be at least 1; lower values are rejected with clear errors.

## Build comparisons

The simulator can compare two named builds side by side while running both builds against the same shared scenario inputs:

- Target Armor Class
- Enemy Save Bonus
- Number of rounds
- Number of simulations

Each compared build has its own build name and one or more attack profiles. Existing single-profile build configurations remain supported by treating the legacy attack fields as one default attack profile. Build A and Build B may use different affected-target counts. The comparison output shows each build's average damage per round, average total damage across all affected targets, average damage per target per round, hit percentage, and critical hit percentage side by side, plus first-build-minus-second-build differences for those metrics. This separates single-target effectiveness from total multi-target damage. It also clearly identifies which build has the higher average damage per round, or reports a tie.

Build comparisons are implemented in Streamlit-independent simulation code. For repeatable and fair comparisons, the comparison runner creates separate random-number-generator instances for the two builds and initializes both with the same seed.

## Damage Formula Syntax

Damage is entered as one inline **Damage Formula**; there is no separate flat damage modifier field. A formula can contain any number of independent dice groups and numeric modifiers:

```text
XdY[reroll clauses][explosion][keep-or-drop][+/- next group or modifier]
```

Each dice group retains its own die size, quantity, rerolls, explosion rule, and keep/drop rule. Groups are resolved independently even when they use the same die size, so `1d4+4d4` stays two separate groups. Numeric modifiers (`+N` or `-N`) are applied once to the complete damage roll, and final damage is never below zero. Critical hits evaluate each dice-group portion twice as independent pools, then apply numeric modifiers once.

| Feature | Syntax | Meaning | Examples |
| --- | --- | --- | --- |
| Basic dice | `XdY` | Roll X dice with Y sides. | `1d8`, `2d6` |
| Modifier | `+N`, `-N` | Add or subtract once after dice processing. | `1d8+4`, `2d6-1` |
| Compound groups | `group+group`, `group-group` | Resolve multiple dice groups independently. | `1d6+1d4+4d4+3`, `4d6kh3+2d8!+1d4-2` |
| Reroll exact | `rN` | Reroll accepted dice showing N until another value appears. | `2d8r8` |
| Reroll low/high | `r<N`, `r>N` | Inclusive reroll threshold (`<= N` or `>= N`). | `2d8r<2`, `2d8r>6` |
| Multiple rerolls | repeated `r...` | Reroll if any condition matches. | `2d8r1r3r5r7` |
| Explode max | `!` | Explode when a die rolls its maximum. | `3d6!` |
| Explode exact | `!N` | Explode only on N. | `3d6!3` |
| Explode threshold | `!>N`, `!<N` | Inclusive explosion threshold (`>= N` or `<= N`). | `3d6!>4`, `3d6!<3` |
| Keep highest | `kN`, `khN` | Keep the highest N completed die chains. | `8d100k4`, `4d6kh3` |
| Keep lowest | `klN` | Keep the lowest N completed die chains. | `8d100kl3` |
| Drop lowest | `dN`, `dlN` | Drop the lowest N completed die chains. | `8d100d3`, `8d100dl3` |
| Drop highest | `dhN` | Drop the highest N completed die chains. | `8d100dh3` |

Processing order for each dice-pool evaluation is deterministic: roll each initial die, apply formula rerolls, apply Tavern Brawler if enabled, check explosion using the final natural face, apply Great Weapon Fighting to the damage contribution if enabled, resolve that die's explosion chain using the same process, continue to the next initial die, apply keep/drop to completed adjusted chain totals, and sum retained values. After every dice group is resolved, numeric modifiers are added or subtracted once. Rerolls, explosions, and keep/drop never spill over to neighboring dice groups. Rerolls and explosions include safety limits to prevent infinite rolling, and formulas that would reroll or explode on every possible face are rejected.

Examples: `1d8+4`, `2d6-1`, `3d6!`, `3d6!>4`, `3d6!3`, `4d6r1!kh3+2`, `8d100r100dh3`, `1d6+1d4+4d4+3`, `2d6kh1+1d8+4`, `1d10!+2d4`, `4d6kh3+2d8!+1d4-2`.

## Requirements

- Python 3.12

## Install

Create and activate a virtual environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

Install the project with development dependencies:

```bash
pip install -e ".[dev]"
```

## Run the Streamlit app

```bash
streamlit run src/dnd_combat_simulator/app.py
```

The app opens a browser interface for simulating one named build by default, with optional side-by-side comparison. Configure the shared target Armor Class, Enemy Save Bonus, number of rounds, number of simulations, and random seed once, then enter Build A's name plus one required primary attack profile. Leave **Compare with another build** off to give Build A the full input width and run a single-build simulation with **Run Simulation**. Turn **Compare with another build** on to restore the two-column Build A / Build B layout and use **Compare Builds** for side-by-side results. Each build also has an independent **Additional Distinct Attacks** number input with Streamlit plus/minus controls. It defaults to `0`, accepts whole-step values from `0` through `10`, and immediately adds or removes attack profile sections as the value changes because the dynamic build controls are rendered outside a Streamlit form. A value of `0` shows only **Primary Attack**; `1` adds **Additional Attack 1**; `2` adds **Additional Attack 2**; and so on through the selected count. Remaining visible profiles keep stable, build-specific Streamlit keys so reruns preserve current input values without renumbering. Every displayed profile includes an attack name, **Resolution Type**, damage formula, attacks per round, **Affected Targets**, and **Active Rounds** field, followed by a collapsed **Feats and Features** expander. Attack-roll profiles show Attack Bonus and Attack Roll Mode while hiding Save DC and Successful Save Damage. Saving-throw profiles show Save DC and Successful Save Damage while hiding Attack Bonus and Attack Roll Mode. Automatic-damage profiles hide Attack Bonus, Attack Roll Mode, Save DC, and Successful Save Damage while continuing to show damage formula, attacks per active round, Affected Targets, and Active Rounds. Every displayed profile is passed into the active simulation mode. In single-build mode, only Build A is rendered, validated, and simulated; Build B's Streamlit keys and entered values are preserved while hidden so they return if comparison is re-enabled. Single-build results include aggregate damage metrics, total attack uses, target resolutions, per-round breakdowns, per-profile breakdowns, and resolution-specific statistics for attack rolls, saving throws, and automatic damage. Select **Compare Builds** in comparison mode to view side-by-side aggregate damage, per-target damage, per-round damage, burst/sustained/total winners, hit-rate, and critical-hit-rate results with differences and per-profile breakdowns.

The Streamlit interface uses rounded, bordered containers for the shared scenario, visible build configuration, and simulation results while preserving the wide centered layout and dark-mode compatibility. Attack profiles are separated with clear dividers and headings such as **Primary Attack** and **Additional Attack 1**. Results keep compact headline cards above three focused damage charts: **Damage per Round**, **Attack Contribution to Damage per Round**, and **Average Damage per Attack Use**. Detailed aggregate, per-round, and per-profile tables remain available below the charts in a **Detailed Results** expander.

### Damage result definitions

- **Damage per Round** is the average total damage produced during each numbered combat round, including every active attack profile, every affected target, and rounds with zero damage. In comparison mode, both builds share one round axis so their per-round trends can be compared directly.
- **Attack Contribution to Damage per Round** is the damage value each attack profile adds to the build's overall average Damage per Round. It is calculated as that profile's total simulated damage divided by total simulated combat rounds, with an additional percentage showing that value's share of the build's total Damage per Round.
- **Average Damage per Attack Use** is the average total damage produced each time an attack profile is executed once before multiplying by the number of affected targets. It includes misses, critical hits, failed saves, successful saves, half-damage saves, automatic damage, all affected targets, and zero-damage uses; it is zero when an attack profile is never used because its active rounds fall outside the simulated combat.

## Run tests

```bash
pytest
```

## Lint and format

Check linting and formatting:

```bash
ruff check .
ruff format --check .
```

Apply formatting:

```bash
ruff format .
```

## Sharing Configurations

1. Configure the simulation, including the shared Scenario inputs and Build A/Build B inputs you want to send.
2. Click the single **Share Configuration** control near the top of the app. The app creates the link and then changes the same control to **Copy Link** without attempting an automatic clipboard copy after the rerun.
3. Click **Copy Link** to copy the generated URL without creating another share record. If browser clipboard permissions block the copy, the app displays and selects the URL so you can press Ctrl+C manually.
4. New share links are short first-party URLs in the form `?share=<short-id>`, such as `?share=yiEwgVR97pGY`. The configuration inputs are stored in the application database and the URL contains only the short record ID.
5. A brief **Link copied** message confirms the link was copied.
6. Anyone who opens that URL receives the same simulator configuration, including Scenario, Build A, and Build B values. They must click **Run Simulation** or **Compare Builds** to generate results from the restored inputs.

Share links contain configuration inputs only, not saved simulation results. Existing legacy `?config=<compressed-token>` links remain supported indefinitely. If a database record for a short `?share=` link is missing or deleted, that short link cannot be restored.
