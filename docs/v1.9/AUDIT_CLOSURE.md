# Organism v1.9 — Audit closure (AUDIT_v1.8)

Software-fixable items from `docs/AUDIT_v1.8.md` closed in **v1.9.0**.

## Closed

| ID | Item |
|---|---|
| P0-1 | `.github/workflows/ci.yml` runs pytest + rust + optional docker |
| P1-1 | README synced to v1.9.0 |
| P1-2 | `ci/gates.yaml` v18 + v19 entries |
| P1-3 | `HostedLLMBackend` (env-gated) |
| P1-4 | Sandbox process isolation (timeout + RSS) |
| P1-5 | Physiology Immune/Autonomic Desktop controls |
| P1-6 | Generative CLI |
| P1-7 | Apoptosis/Circadian/Morphogenesis/ISE Desktop demos |
| P1-8 | v02 sink attached in Desktop; snapshot exposes flag |
| P2-1 | `ImageBackend` + procedural_v1.9 packs |
| P2-2 | Promote EXPLORATION product limit documented |
| P2-3 | Federation / multiprocess labeled `not_production_bft` |
| P2-4 | Rust `control_loop` minimal tick + tests |
| P2-5 | Committed `desktop/organism-desktop.spec` + PACKAGING |
| P2-6 | Dockerfile generative env defaults |
| P2-7 | Generative evolution doc header |
| P2-8 | README modules table |
| P2-9 | Thicker generative module tests |
| P2-10 | Physiology apoptosis/circadian |
| P2-11 | Learned-ISE Desktop UX |
| P2-12 | Multiprocess Ops button |
| P2-13 | Soak cadence noted in STATUS |
| P3-1 | NiceGUI demoted / out of scope |
| P3-2 | `modules/README_RUST_HELPERS.md` for hdc/kernel crates |
| P3-3 | Template library expanded (10) |
| P3-4 | Draft Replay Desktop tab |
| P3-5 | Docs panel AUDIT + v1.8/v1.9 links |
| P3-6 | Hypervector sparkline preview |
| P3-7 | Category I 480s remains opt-in (documented) |

## Deferred (hardware / external)

- Real neuromorphic silicon
- Real bioreactor GPIO / wet-lab HW
- Production WAN BFT + TPM
- Hybrid PySide6 Studio / OpenGL twin UI
- Hosted LLM provider account/network (client exists; provider external)

## Verification

- Suite: **356** passed · 2 slow deselected (`pytest -m 'not slow'`)
- Tag **v1.9.0**
- Bio actuation: `may_actuate=False` preserved; promote hot-register capped at EXPLORATION
- Sandbox: spawn process jail + wall-clock timeout + RSS cap; AST whitelist first line
- Hosted LLM/image: env-gated; refuse until configured (never default-on)

