# DnD Combat Simulator

Initial project setup for a browser-based DnD combat simulator built with Python 3.12 and Streamlit.

## Combat rules

The simulator now includes Streamlit-independent logic for resolving one weapon attack. A single attack uses an attack bonus, target Armor Class, damage dice such as `1d8`, and a separate damage modifier.

Attack resolution follows these rules:

- Choose an attack roll mode: normal, advantage, or disadvantage. Normal rolls `1d20`; advantage rolls `2d20` and selects the higher die; disadvantage rolls `2d20` and selects the lower die. The selected die is added to the attack bonus to produce the modified attack total.
- A selected natural 1 automatically misses, even if the modified total would meet the target Armor Class.
- A selected natural 20 automatically hits and is a critical hit.
- Any other attack hits when the modified attack total equals or exceeds the target Armor Class.
- A normal hit rolls the listed damage dice once and adds the damage modifier once.
- A critical hit doubles only the number of damage dice, then adds the damage modifier once. For example, `1d8 + 3` becomes `2d8 + 3` on a critical hit.
- A miss deals zero damage.
- Final damage cannot be below zero.

Single-attack resolution returns the attack roll mode, all natural d20 rolls, the selected natural d20 roll, modified attack total, whether the attack hit, whether it was a critical hit, and damage dealt. Random number generation can be injected for deterministic tests.


## Damage simulations

The project also includes Streamlit-independent simulation logic for repeated damage estimates. A simulation uses the existing single-attack combat resolver and runs one or more distinct attack profiles per round for a requested number of rounds. Each attack profile has its own attack name, attack bonus, damage dice, damage modifier, attacks per round, and attack roll mode. That full combat is repeated for the requested number of simulations.

Simulation inputs are:

- One or more reusable attack profiles, each with:
  - Attack name, used as the stable schedule reference
  - Attack bonus
  - Damage dice, without an embedded modifier
  - Damage modifier
  - Legacy attacks per round, defaulting to 1
  - Attack roll mode, defaulting to normal
- An optional round schedule made from ordered round plans. Each round plan has a round number and zero or more attack uses. Each attack use references one of the build's attack profiles and sets how many times to resolve it during that round.
- Undefined-round behavior for rounds beyond the explicit schedule: `repeat_final_round` (default), `repeat_entire_schedule`, or `no_attacks`.
- Target Armor Class
- Number of rounds
- Number of simulations

For example, a build can define reusable Longbow, Scimitar, Shortsword, and Greatsword profiles, then schedule them as: Round 1 Longbow ×1; Round 2 Scimitar ×1 and Shortsword ×1; Round 3 Scimitar ×1 and Shortsword ×1; Round 4 Greatsword ×1. During each simulated round, only the listed attack uses are resolved, preserving each selected profile's own attack bonus, damage dice, damage modifier, and roll mode. A scheduled round may intentionally contain zero attacks. Existing builds without a round schedule remain valid; the simulator automatically creates a compatibility schedule that repeats every profile according to its legacy attacks-per-round value.

Simulation results summarize aggregate outcomes without retaining every individual attack result. The returned summary includes simulations run, rounds per simulation, average attacks per round across the schedule, total attacks made, average total damage per simulation, average damage per round, hit rate, critical hit rate, and the minimum and maximum total damage observed in a simulation. Results also include a per-attack-profile breakdown with each profile's total attacks, average damage, hit rate, and critical hit rate. A per-round breakdown reports each round number, average damage, average attacks, hit percentage, and critical hit percentage. Summary metrics include first-round burst damage, average damage after round 1, highest-damage round, highest-round average damage, average damage per round, and average total damage. Overall hit and critical-hit statistics are preserved across all attacks from all profiles.

Random number generation can be injected so simulations are deterministic in tests. Rounds, attacks per round, and simulation counts must all be at least 1; lower values are rejected with clear errors.

## Build comparisons

The simulator can compare two named builds side by side while running both builds against the same shared scenario inputs:

- Target Armor Class
- Number of rounds
- Number of simulations

Each compared build has its own build name and one or more attack profiles. Existing single-profile build configurations remain supported by treating the legacy attack fields as one default attack profile. The comparison output shows each build's average damage per round, average total damage, hit percentage, and critical hit percentage side by side, plus first-build-minus-second-build differences for those metrics. It also clearly identifies which build has the higher average damage per round, or reports a tie.

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

The app opens a browser interface for comparing two named builds. Configure the shared target Armor Class, number of rounds, number of simulations, and random seed once, then enter each build's name plus one required primary attack profile. Each build also has an independent **Additional Distinct Attacks** number input with Streamlit plus/minus controls. It defaults to `0`, accepts whole-step values from `0` through `10`, and immediately adds or removes attack profile sections as the value changes because the dynamic build controls are rendered outside a Streamlit form. A value of `0` shows only **Primary Attack**; `1` adds **Additional Attack 1**; `2` adds **Additional Attack 2**; and so on through the selected count. Remaining visible profiles keep stable, build-specific Streamlit keys so reruns preserve current input values without renumbering. Every displayed profile includes an attack name, attack bonus, damage dice, damage modifier, attacks per round, and attack roll mode, and every displayed profile is passed into the comparison simulation.

Below each build's attack profile library, the **Round Schedule** section defaults its scheduled round count to the shared scenario's number of rounds. Each build has independent controls to select one or more profiles per round, set the number of uses for each selected profile, remove attacks, copy the previous round, clear a round, add a scheduled round, remove the final scheduled round, and choose undefined-round behavior. Select **Compare Builds** to view side-by-side aggregate damage, per-round damage, burst/sustained/total winners, hit-rate, and critical-hit-rate results with differences and per-profile breakdowns.

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
