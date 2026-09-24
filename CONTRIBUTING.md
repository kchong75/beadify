# Contributing

Issues and pull requests are welcome.

## Development setup

```bash
git clone https://github.com/kchong75/beadify.git
cd beadify
pip install -e ".[dev]"
pytest
```

The `ai` extra (`pip install -e ".[ai]"`, adds the `anthropic` package) is only needed to actually call
Claude; the test suite mocks the API client, so `pytest` passes without it and without an API key.

## Scope

- `src/beadify/` (`palette.py`, `prep.py`, `quantize.py`, `pattern.py`, `render.py`, `cli.py`) is the core
  pipeline: image → bead grid → chart. Changes here affect every user, so please open an issue first for
  anything beyond a bug fix, and add a test in `tests/test_beadify.py`.
- `src/beadify/ai/` is the optional AI-assisted preparation step. It never touches the core pipeline; it
  only produces an edited photo that is then fed into it unchanged. Tests live in `tests/test_ai.py` and
  use a fake Anthropic client (see `FakeMessages` there) — no network access or API key required.

## Guidelines

- Keep the core pipeline dependency-light (numpy, Pillow, scipy, scikit-image only).
- Every new CLI option needs a line in the relevant `--help` text and the README's option table.
- Run `pytest -q` before opening a PR; CI runs it on Python 3.9, 3.11 and 3.12.
