"""Work agent layer on Organism (v1.12). Design record: docs/v1.12/WORK_AGENT.md.

The pure domain: triggers, mandates, tickets, the admission gate, the stage table and the
versioned Policy. The store, the Sources and the executors arrive in later phases.
"""

from organism_sdk.work.domain import (
    Addressed,
    Assignment,
    AssignmentState,
    Decision,
    Mandate,
    Outcome,
    Report,
    Strength,
    Thread,
    Ticket,
    Trigger,
    Via,
    thread_key,
)
from organism_sdk.work.gate import Admission, Reason, ScopeFacts, admit
from organism_sdk.work.policy import (
    AcceptMode,
    AdmissionRow,
    Cell,
    Policy,
    Rule,
    SourcePolicy,
    may_accept_inferred,
    policy_version,
)
from organism_sdk.work.stage import Stage, stage_of, waits_for_person

__all__ = [
    "AcceptMode",
    "Addressed",
    "Admission",
    "AdmissionRow",
    "Assignment",
    "AssignmentState",
    "Cell",
    "Decision",
    "Mandate",
    "Outcome",
    "Policy",
    "Reason",
    "Report",
    "Rule",
    "ScopeFacts",
    "SourcePolicy",
    "Stage",
    "Strength",
    "Thread",
    "Ticket",
    "Trigger",
    "Via",
    "admit",
    "may_accept_inferred",
    "policy_version",
    "stage_of",
    "thread_key",
    "waits_for_person",
]
