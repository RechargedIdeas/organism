# Organism Desktop — Packaging notes (v1.6)

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

## Optional PyInstaller (not shipped as a binary in-tree)

A frozen one-folder build is optional. Example sketch (adjust paths):

```bash
pip install pyinstaller
pyinstaller \
  --name organism-desktop \
  --noconfirm \
  --collect-all PySide6 \
  --hidden-import organism_sdk \
  --hidden-import organism_desktop \
  desktop/organism_desktop/__main__.py
```

Notes:

- Prefer **onedir** over onefile for Qt plugins.
- Bundle `deploy/config/*.yaml` and `docs/` if operators need offline Ops/Docs.
- **Do not** embed wet-lab credentials; actuation stays refused (`may_actuate=False`).
- Hybrid PySide6 Studio / OpenGL twin UIs are **out of scope** (see `VENDOR.md`).

This repo does not require a committed `.spec` for CI; the entry point above is
the supported packaging surface.
