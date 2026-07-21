# DnD Combat Simulator

Initial project setup for a browser-based DnD combat simulator built with Python 3.12 and Streamlit.

## Combat rules

The simulator now includes Streamlit-independent logic for resolving one weapon attack. A single attack uses an attack bonus, target Armor Class, damage dice such as `1d8`, and a separate damage modifier.

Attack resolution follows these rules:

- Roll `1d20` and add the attack bonus to produce the modified attack total.
- A natural 1 automatically misses, even if the modified total would meet the target Armor Class.
- A natural 20 automatically hits and is a critical hit.
- Any other attack hits when the modified attack total equals or exceeds the target Armor Class.
- A normal hit rolls the listed damage dice once and adds the damage modifier once.
- A critical hit doubles only the number of damage dice, then adds the damage modifier once. For example, `1d8 + 3` becomes `2d8 + 3` on a critical hit.
- A miss deals zero damage.
- Final damage cannot be below zero.

Single-attack resolution returns the natural d20 roll, modified attack total, whether the attack hit, whether it was a critical hit, and damage dealt. Random number generation can be injected for deterministic tests.

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

The app displays the initial page title: **DnD Combat Simulator**.

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
