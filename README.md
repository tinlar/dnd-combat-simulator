# DnD Combat Simulator

Initial project setup for a browser-based DnD combat simulator built with Python 3.12 and Streamlit.

## Combat rules

The simulator includes Streamlit-independent logic for resolving damage profiles as attack rolls, saving throws, or automatic damage. Attack-roll profiles use an attack bonus, target Armor Class, damage dice such as `1d8`, and a separate damage modifier. Saving-throw profiles use a Save DC, the shared Enemy Save Bonus, damage dice, a damage modifier, and a successful-save damage behavior. Automatic-damage profiles use damage dice, a damage modifier, attacks per active round, affected targets, and Active Rounds without requiring Attack Bonus or Save DC.

Attack-roll resolution follows these rules:

- Choose an attack roll mode: normal, advantage, or disadvantage. Normal rolls `1d20`; advantage rolls `2d20` and selects the higher die; disadvantage rolls `2d20` and selects the lower die. The selected die is added to the attack bonus to produce the modified attack total.
- A selected natural 1 automatically misses, even if the modified total would meet the target Armor Class.
- A selected natural 20 automatically hits and is a critical hit.
- Any other attack hits when the modified attack total equals or exceeds the target Armor Class.
- A normal hit rolls the listed damage dice once and adds the damage modifier once.
- A critical hit doubles only the number of damage dice, then adds the damage modifier once. For example, `1d8 + 3` becomes `2d8 + 3` on a critical hit.
- A miss deals zero damage.
- Final damage cannot be below zero.

Saving-throw resolution follows these rules:

- Roll `1d20` and add the shared Enemy Save Bonus. The same enemy save bonus applies to all saving throws for now.
- The enemy succeeds when the total equals or exceeds the Save DC, and fails when the total is below the Save DC.
- On a failed save, the profile deals full damage.
- On a successful save, the profile deals either no damage or half damage depending on its **Successful Save Damage** setting. Half damage rounds down.
- Damage modifiers are included before halving.
- Saving throws cannot critically hit. Natural 1 and natural 20 do not automatically fail or succeed.
- Final damage cannot be below zero.

Automatic-damage resolution follows these rules:

- No d20 is rolled: the simulator does not make an attack roll or a saving throw.
- Damage is always applied and automatic damage cannot critically hit.
- Damage is rolled separately for each attack use and each affected target.
- The damage modifier is added to each automatic damage roll.
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


## Damage simulations

The project also includes Streamlit-independent simulation logic for repeated damage estimates. A simulation uses the existing single-attack combat resolver and runs one or more distinct attack profiles per round for a requested number of rounds. Each attack profile has its own attack name, attack bonus, damage dice, damage modifier, attacks per round, attack roll mode, and optional Active Rounds expression. That full combat is repeated for the requested number of simulations.

Simulation inputs are:

- One or more reusable attack profiles, each with:
  - Attack name
  - Resolution Type (`Attack Roll`, `Saving Throw`, or `Automatic Damage`), defaulting to attack roll for backward compatibility
  - Attack bonus for attack-roll profiles
  - Save DC for saving-throw profiles
  - Successful Save Damage for saving-throw profiles, defaulting to no damage
  - No Attack Bonus, Attack Roll Mode, Save DC, or Successful Save Damage requirement for automatic-damage profiles
  - Damage dice, without an embedded modifier
  - Damage modifier
  - Attacks per round, defaulting to 1
  - Affected Targets, defaulting to 1
  - Attack roll mode for attack-roll profiles, defaulting to normal
  - Active Rounds, defaulting to blank for every round
- Target Armor Class
- Enemy Save Bonus, defaulting to +3
- Number of rounds
- Number of simulations

Active Rounds controls which rounds use an attack profile. Blank means the profile is active every scenario round. A single value such as `1` means round 1 only; a range such as `1-5` means rounds 1 through 5; and a comma-separated expression such as `1, 3-5, 8` means rounds 1, 3, 4, 5, and 8. Optional whitespace is allowed around commas and ranges. Duplicate or overlapping values such as `1-3, 2-4` are deduplicated and processed in ascending order as rounds 1, 2, 3, and 4. Round numbers must be positive integers, reversed ranges such as `5-3` are invalid, and rounds greater than the scenario's round count are valid but ignored during that simulation. During each simulated round, only profiles with blank Active Rounds or an Active Rounds set containing the current round are resolved, using that profile's attacks-per-round value. A build may intentionally have zero attacks in a round. Existing attack profiles without Active Rounds remain valid and behave as active every round.

Simulation results summarize aggregate outcomes without retaining every individual attack result. The returned summary includes simulations run, rounds per simulation, average attacks per round, total attacks made, total target resolutions, automatic damage applications, average automatic damage per application, average total damage per simulation across all affected targets, average total damage per round across all affected targets, average damage per target per round, attack-roll hit rate, critical hit rate for attack rolls, failed save rate, successful save rate, and the minimum and maximum total damage observed in a simulation. Results also include a per-attack-profile breakdown with each profile's affected targets, total attacks, total target resolutions, average damage, average damage per target per round, attack-roll hit and critical-hit rates where meaningful, and saving-throw failed/successful save rates where meaningful. A per-round breakdown reports each round number, average damage, average attacks, full damage success percentage, critical-hit percentage, failed-save percentage, and successful-save percentage. Summary metrics include first-round burst damage, average damage after round 1, highest-damage round, highest-round average damage, average damage per round, and average total damage. The Streamlit comparison summary does not calculate a misleading combined success rate across attack rolls, saving throws, and automatic damage. Resolution-specific rates remain in the per-profile breakdown.

Random number generation can be injected so simulations are deterministic in tests. For attack-roll profiles, random rolls are consumed by simulation, round, attack profile, attack use, target, attack roll, then damage roll if that target hits. For saving-throw profiles with multiple affected targets, random rolls are consumed by simulation, round, attack profile, attack use, one shared damage roll, then one saving throw for each target. For automatic-damage profiles, random rolls are consumed by simulation, round, attack profile, attack use, target, then that target's damage roll. Rounds, attacks per round, affected targets, and simulation counts must all be at least 1; lower values are rejected with clear errors.

## Build comparisons

The simulator can compare two named builds side by side while running both builds against the same shared scenario inputs:

- Target Armor Class
- Enemy Save Bonus
- Number of rounds
- Number of simulations

Each compared build has its own build name and one or more attack profiles. Existing single-profile build configurations remain supported by treating the legacy attack fields as one default attack profile. Build A and Build B may use different affected-target counts. The comparison output shows each build's average damage per round, average total damage across all affected targets, average damage per target per round, hit percentage, and critical hit percentage side by side, plus first-build-minus-second-build differences for those metrics. This separates single-target effectiveness from total multi-target damage. It also clearly identifies which build has the higher average damage per round, or reports a tie.

Build comparisons are implemented in Streamlit-independent simulation code. For repeatable and fair comparisons, the comparison runner creates separate random-number-generator instances for the two builds and initializes both with the same seed.

## Dice notation

The dice foundation supports simple notation in the form `XdY`, where `X` is the number of dice to roll and `Y` is the number of sides on each die. An optional flat modifier may be added with `+N` or `-N`.

Supported examples include:

- `1d4`
- `1d6`
- `1d8`
- `1d10+4`
- `1d12`
- `2d6-1`
- `3d8`

Invalid notation is rejected with a clear error.

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

The app opens a browser interface for simulating one named build by default, with optional side-by-side comparison. Configure the shared target Armor Class, Enemy Save Bonus, number of rounds, number of simulations, and random seed once, then enter Build A's name plus one required primary attack profile. Leave **Compare with another build** off to give Build A the full input width and run a single-build simulation with **Run Simulation**. Turn **Compare with another build** on to restore the two-column Build A / Build B layout and use **Compare Builds** for side-by-side results. Each build also has an independent **Additional Distinct Attacks** number input with Streamlit plus/minus controls. It defaults to `0`, accepts whole-step values from `0` through `10`, and immediately adds or removes attack profile sections as the value changes because the dynamic build controls are rendered outside a Streamlit form. A value of `0` shows only **Primary Attack**; `1` adds **Additional Attack 1**; `2` adds **Additional Attack 2**; and so on through the selected count. Remaining visible profiles keep stable, build-specific Streamlit keys so reruns preserve current input values without renumbering. Every displayed profile includes an attack name, **Resolution Type**, damage dice, damage modifier, attacks per round, **Affected Targets**, and **Active Rounds** field. Attack-roll profiles show Attack Bonus and Attack Roll Mode while hiding Save DC and Successful Save Damage. Saving-throw profiles show Save DC and Successful Save Damage while hiding Attack Bonus and Attack Roll Mode. Automatic-damage profiles hide Attack Bonus, Attack Roll Mode, Save DC, and Successful Save Damage while continuing to show damage dice, damage modifier, attacks per active round, Affected Targets, and Active Rounds. Every displayed profile is passed into the active simulation mode. In single-build mode, only Build A is rendered, validated, and simulated; Build B's Streamlit keys and entered values are preserved while hidden so they return if comparison is re-enabled. Single-build results include aggregate damage metrics, total attack uses, target resolutions, per-round breakdowns, per-profile breakdowns, and resolution-specific statistics for attack rolls, saving throws, and automatic damage. Select **Compare Builds** in comparison mode to view side-by-side aggregate damage, per-target damage, per-round damage, burst/sustained/total winners, hit-rate, and critical-hit-rate results with differences and per-profile breakdowns.

The Streamlit interface uses rounded, bordered containers for the shared scenario, visible build configuration, and simulation results while preserving the wide centered layout and dark-mode compatibility. Attack profiles are separated with clear dividers and headings such as **Primary Attack** and **Additional Attack 1**. Results now keep compact headline cards above responsive charts: single-build runs show damage by round, damage by attack profile, and damage contribution, while comparison runs show side-by-side round trends, grouped key damage metrics, and separate attack-profile charts for each build. Detailed aggregate, per-round, and per-profile tables remain available below the charts in a **Detailed Results** expander.

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
