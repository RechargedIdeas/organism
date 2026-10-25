# Organism Desktop

First-party **PySide6** control plane for Organism (v1.5).

```bash
pip install -e '.[desktop]'
organism-desktop
# or
python -m organism_desktop
```

Headless / CI:

```bash
QT_QPA_PLATFORM=offscreen python -m organism_desktop --smoke
PYTHONPATH=sdk/python:modules:desktop:. pytest desktop/tests -q
```

See [docs/v1.5/DESKTOP.md](../docs/v1.5/DESKTOP.md).
