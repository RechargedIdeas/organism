"""E.5 contract:validate gate entrypoint."""
from deterministic_engine.engine import DeterministicEngine
from organism_sdk.contract import Severity


def test_contract_validate_gate():
    eng = DeterministicEngine()
    errors = [i for i in eng.declare_contract().validate() if i.severity == Severity.ERROR]
    assert errors == [], errors
