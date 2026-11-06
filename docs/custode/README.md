# Custode in Organism: design package

This folder holds the design for running Custode, an on-device browser agent, as an Organism application. The plan and
its phases are in [../CUSTODE_UPGRADE_PLAN.md](../CUSTODE_UPGRADE_PLAN.md). The documents here carry the detail.

- **Status:** Proposed. Docs only. No code, proto, or CI change is made by this package.
- **Companion repository:** `custode` (a separate folder, not a git repository). Its `docs/organism/` folder holds the
  proposal this package is checked against. Its `docs/14-decisions.md` holds the open decisions O-11 and O-12. Its
  `STATUS.md` holds the measured results for the Custode side.

## Reading order

1. [../CUSTODE_UPGRADE_PLAN.md](../CUSTODE_UPGRADE_PLAN.md): summary, corrections, phases, and the decisions CD1 to CD6.
2. [CONTRACT_EXTENSIONS.md](CONTRACT_EXTENSIONS.md): the proposed additive proto and Python changes, with their numbers.
3. [BROWSER_RUNTIME.md](BROWSER_RUNTIME.md): how the browser fits as a Source, and which tiers its experts use.
4. [BRIDGE_CHANNEL.md](BRIDGE_CHANNEL.md): the loopback bridge, its controls, and the open question on `Channel` (O-12).
5. [LEARNING_AND_EVAL.md](LEARNING_AND_EVAL.md): feedback, adapters as artifacts, the promotion path, and rollback.
6. [GOVERNANCE.md](GOVERNANCE.md): the browser's own rules, and the Organism mechanisms they would map onto.

## Ground rules for this package

- Existing names and numbers were read from the Organism repository when this package was written. A name marked
  **new** does not exist yet.
- Field numbers and enum values are proposals until decision O-11 is taken. They follow the API freeze: additive only,
  numbered after the current maximum.
- Thresholds marked **provisional** need measured data before they become gates.
- The Custode repository is not part of Organism. Links to it name its file, and are not relative links.
