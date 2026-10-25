# Organism Desktop — Packaging notes (v1.9)

## Install (developer)

```bash
pip install -e '.[desktop]'
organism-desktop
# or: python -m organism_desktop
```

Console entry point: `organism-desktop` → `organism_desktop.app:main`
(declared in `pyproject.toml` `[project.scripts]`).

Optional extra: `[desktop]` pulls **PySide6≥6.6**. Core SDK runs without it;
Desktop tests set `QT_QPA_PLATFORM=offscreen`.

## CPU / CI smoke

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=sdk/python:modules:desktop:. \
  python -m organism_desktop --smoke
```

## PyInstaller (committed `.spec`)

```bash
pip install pyinstaller
# from repo root:
pyinstaller desktop/organism-desktop.spec
# artifact: dist/organism-desktop/
```

CI does **not** require a frozen binary artifact by default; the committed
`desktop/organism-desktop.spec` is the supported recipe. Prefer the editable
install + `--smoke` gate for PR checks.

## NiceGUI / remote status UI

Explicitly **out of scope** for Desktop packaging (see CHANGELOG / AUDIT).
Use `organism serve` health/status HTTP or Desktop Ops panel instead.
