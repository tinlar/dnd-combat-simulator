# UI Architecture (Stage 3)

## Module ownership

- `app.py`: Streamlit entry point, page setup, high-level orchestration, validation/execution coordination, and result hand-off.
- `ui/widget_keys.py`: widget-key construction, build-scoped prefixes, and stable widget identity helpers. It intentionally has no Streamlit import.
- `ui/state.py`: session-state helpers, stable attack/resource identity, migration, duplication/deletion transforms, and reconstruction from session state.
- `ui/validation.py`: structured validation data and field-to-widget validation mapping. Rendering remains outside the validation model.
- `ui/inputs.py`: configuration widgets, attack cards, resource cards, and converting widget values into domain input objects.
- `ui/results.py`: simulation/comparison result rendering plus result table and metric formatting.
- `ui/run_control.py`: Run Simulation button state, execution coordination, canonical simulation requests, bounded Streamlit result caching, duration feedback.
- `ui/sharing.py`: share button rendering, share-link creation, shared configuration loading and hydration.
- `ui/components.py`: reusable visual components and scoped styling.
- `ui/constants.py`: immutable labels, help text, limits, and UI/session constants.

## Attack IDs versus widget prefixes

Stable attack IDs are domain identity and survive reordering. Widget prefixes are build-scoped identity (`first-...`, `second-...`) so Build A and Build B can hold independent widget state even when they contain the same domain attack IDs.

## Validation flow

1. Migrate legacy session/share state.
2. Construct `ScenarioConfig` and `BuildConfig` values from state/widgets.
3. Validate domain configuration.
4. Map validation issues to canonical widget keys.
5. Render issues near editable fields.
6. Disable simulation and sharing while errors remain.

## Simulation cache key

`CanonicalSimulationRequest` includes the scenario, Build A, Build B only when comparison is enabled, comparison mode, simulation count, random seed, and `SIMULATION_CACHE_VERSION`. UI-only values, share URLs/IDs, expander state, button state, and validation messages are excluded.

Increment `SIMULATION_CACHE_VERSION` in `ui/run_control.py` whenever simulation semantics change and old cached results must be invalidated.

## Commands

```bash
ruff check .
ruff format --check .
mypy src/dnd_combat_simulator
pytest -q
pytest --cov=src/dnd_combat_simulator --cov-branch --cov-report=term-missing
python scripts/benchmark_simulation.py --repeats 3
```

## Stage 3.1 architecture notes

`dnd_combat_simulator.app` is now an entry-point module. Its intentional public
compatibility surface is the explicit `__all__` tuple containing only `main` and
`configure_page`; detailed rendering is orchestrated from `ui.page` and owned by
focused UI modules.

Validation uses the canonical `ValidationIssue` structure for scenario, build,
attack, resource, and sharing-facing checks. Streamlit rendering is separated
from pure validation: `ui.validation` constructs issues, while
`ui.validation_rendering` displays field-level messages from those structured
issues.

Canonical simulation requests are validated in `ui.run_control` before the
Streamlit cache boundary is invoked, so invalid requests raise a concise
`ValueError` and are not cached. Cache tests instrument the execution boundary to
verify invalid requests and failures do not become successful cache entries.

Stage 3.1 tests add bounded Hypothesis coverage for attack identity/order, dice
seed determinism, and deterministic canonical request generation. Streamlit
AppTest coverage remains focused on real app loading and duplicate-button state
behavior in this environment.
