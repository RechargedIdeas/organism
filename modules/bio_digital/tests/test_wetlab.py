"""v1.4 wet-lab HAL + SafetyPolicy."""
from __future__ import annotations

import pytest

from bio_digital.limits import PHYSARUM_LIMITS
from bio_digital.wetlab import ActuationDenied, SafetyPolicy, WetLabHAL, gpio_env_enabled


def test_default_policy_denies_actuation(monkeypatch):
    monkeypatch.delenv("ORGANISM_WETLAB_GPIO", raising=False)
    hal = WetLabHAL(PHYSARUM_LIMITS)
    assert hal.may_actuate_declared is False
    assert gpio_env_enabled() is False
    with pytest.raises(ActuationDenied, match="policy_not_certified"):
        hal.apply_potential("A0", 0.1)


def test_voltage_clamp_rejects_over_limit(monkeypatch):
    monkeypatch.setenv("ORGANISM_WETLAB_GPIO", "1")
    policy = SafetyPolicy.certified(
        certifier="test-op",
        certificate_id="T-1",
        max_voltage=PHYSARUM_LIMITS.max_voltage,
    )
    hal = WetLabHAL(PHYSARUM_LIMITS, policy=policy)
    with pytest.raises(ValueError, match="voltage clamp"):
        hal.apply_potential("A0", PHYSARUM_LIMITS.max_voltage + 1.0)


def test_certified_without_env_still_denied(monkeypatch):
    monkeypatch.delenv("ORGANISM_WETLAB_GPIO", raising=False)
    policy = SafetyPolicy.certified(
        certifier="test-op",
        certificate_id="T-2",
        max_voltage=PHYSARUM_LIMITS.max_voltage,
    )
    hal = WetLabHAL(PHYSARUM_LIMITS, policy=policy)
    with pytest.raises(ActuationDenied, match="ORGANISM_WETLAB_GPIO"):
        hal.apply_potential("A0", 0.2)


def test_certified_with_env_allows_sim_actuation(monkeypatch):
    monkeypatch.setenv("ORGANISM_WETLAB_GPIO", "1")
    policy = SafetyPolicy.certified(
        certifier="test-op",
        certificate_id="T-3",
        max_voltage=PHYSARUM_LIMITS.max_voltage,
    )
    # No device path → device_missing, but in-memory actuation allowed
    hal = WetLabHAL(PHYSARUM_LIMITS, policy=policy, device_path="/nonexistent/gpio")
    assert hal.try_open_device() == "device_missing"
    hal.apply_potential("A0", 0.25)
    assert hal.read_sensors()["electrodes"]["A0"] == 0.25


def test_unhealthy_blocks_actuation(monkeypatch):
    monkeypatch.setenv("ORGANISM_WETLAB_GPIO", "1")
    policy = SafetyPolicy.certified(
        certifier="test-op",
        certificate_id="T-4",
        max_voltage=PHYSARUM_LIMITS.max_voltage,
    )
    hal = WetLabHAL(PHYSARUM_LIMITS, policy=policy)
    hal.set_environment(temp_c=PHYSARUM_LIMITS.max_temp_c + 10.0)
    assert not hal.is_healthy()
    with pytest.raises(ActuationDenied, match="substrate_unhealthy"):
        hal.apply_potential("A0", 0.1)


def test_sim_loop_denies_under_default_policy(monkeypatch):
    monkeypatch.delenv("ORGANISM_WETLAB_GPIO", raising=False)
    hal = WetLabHAL(PHYSARUM_LIMITS)
    result = hal.run_sim_loop(steps=5, attempt_actuate=True)
    assert result.steps == 5
    assert result.actuations_denied == 5
    assert result.actuations_applied == 0
    assert result.exploration_only is True
    assert result.affects_control is False
    assert len(result.readings) == 5


def test_sim_loop_applies_when_certified(monkeypatch):
    monkeypatch.setenv("ORGANISM_WETLAB_GPIO", "1")
    policy = SafetyPolicy.certified(
        certifier="test-op",
        certificate_id="T-5",
        max_voltage=PHYSARUM_LIMITS.max_voltage,
    )
    hal = WetLabHAL(PHYSARUM_LIMITS, policy=policy, device_path="")
    result = hal.run_sim_loop(steps=4, voltage=0.15)
    assert result.actuations_applied == 4
    assert result.actuations_denied == 0
    assert result.device_status == "device_missing"


def test_bio_modules_still_may_actuate_false():
    from bio_digital.slime_mold import SlimeMoldModule
    from bio_digital.mycelium import MyceliumModule

    for mod in (SlimeMoldModule(), MyceliumModule()):
        assert mod.declare_contract().safety.may_actuate is False


def test_certified_factory_requires_fields():
    with pytest.raises(ValueError):
        SafetyPolicy.certified(certifier="unset", certificate_id="x", max_voltage=1.0)
    with pytest.raises(ValueError):
        SafetyPolicy.certified(certifier="op", certificate_id="", max_voltage=1.0)
