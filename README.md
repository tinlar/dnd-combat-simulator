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

- One or more attack profiles, each with:
  - Attack name
  - Attack bonus
  - Damage dice, without an embedded modifier
  - Damage modifier
  - Attacks per round, defaulting to 1
  - Attack roll mode, defaulting to normal
- Target Armor Class
- Number of rounds
- Number of simulations

Simulation results summarize aggregate outcomes without retaining every individual attack result. The returned summary includes simulations run, rounds per simulation, combined attacks per round across all attack profiles, total attacks made, average total damage per simulation, average damage per round, hit rate, critical hit rate, and the minimum and maximum total damage observed in a simulation. Results also include a per-attack-profile breakdown with each profile's total attacks, average damage, hit rate, and critical hit rate. Overall hit and critical-hit statistics are preserved across all attacks from all profiles.

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

The app opens a browser interface for comparing two named builds. Configure the shared target Armor Class, number of rounds, number of simulations, and random seed once, then enter each build's name plus one required attack profile. Enable the optional second attack profile checkbox for a build to add another distinct attack routine with its own attack name, attack bonus, damage dice, damage modifier, attacks per round, and attack roll mode. Select **Compare Builds** to view side-by-side aggregate damage, hit-rate, and critical-hit-rate results with differences and the higher-damage build called out.

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
