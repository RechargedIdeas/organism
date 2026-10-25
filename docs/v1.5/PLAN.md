# Organism v1.5 Plan — Desktop GUI

| Phase | Deliverable | Gate |
|---|---|---|
| D0 | Design (`DESKTOP.md`) | docs present |
| D1 | `DesktopService` (headless SDK façade) | unit tests |
| D2 | PySide6 shell + nav + all 10 panels | smoke + nav registry |
| D3 | Pipeline decide round-trip + bio refuse | `v15:desktop` |
| D4 | pyproject `[desktop]`, README, STATUS/CHANGELOG | package import |
| D5 | Tag **v1.5.0** | release |

**OOS:** Hybrid Studio import, OpenGL node editor, wet-lab GPIO from UI,
WAN BFT console, production auth SSO.

**Stack choice:** PySide6 6.12 installed cleanly on the build box → primary.
NiceGUI kept as documented fallback only.
