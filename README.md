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

The project also includes Streamlit-independent simulation logic for repeated damage estimates. A simulation uses the existing single-attack combat resolver and runs a requested number of weapon attacks per round for a requested number of rounds. That full combat is repeated for the requested number of simulations.

Simulation inputs are:

- Attack bonus
- Target Armor Class
- Damage dice, without an embedded modifier
- Damage modifier
- Number of rounds
- Attacks per round, defaulting to 1
- Number of simulations
- Attack roll mode, defaulting to normal

Simulation results summarize aggregate outcomes without retaining every individual attack result. The returned summary includes simulations run, rounds per simulation, attacks per round, attack roll mode, total attacks made, average total damage per simulation, average damage per round, hit rate, critical hit rate, and the minimum and maximum total damage observed in a simulation.

Random number generation can be injected so simulations are deterministic in tests. Rounds, attacks per round, and simulation counts must all be at least 1; lower values are rejected with clear errors.

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

The app opens a simple browser interface for configuring and running damage simulations. Use the input controls for attack bonus, target Armor Class, damage dice, damage modifier, attack roll mode, number of rounds, attacks per round, and number of simulations, then select **Run Simulation** to view aggregate damage, hit-rate, critical-hit-rate, and total-attack results. Total attacks equal number of simulations × number of rounds × attacks per round, and average damage per round includes every attack made during each round.

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
