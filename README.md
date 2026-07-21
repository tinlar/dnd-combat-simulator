# DnD Combat Simulator

Initial project setup for a browser-based DnD combat simulator built with Python 3.12 and Streamlit.

> Combat rules are intentionally not implemented yet.


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
