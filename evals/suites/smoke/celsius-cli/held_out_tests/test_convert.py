"""Held-out acceptance tests for celsius-cli. The agent never sees these."""

import os
import subprocess
import sys

import pytest


def test_function_exists_and_converts():
    import convert

    assert convert.celsius_to_fahrenheit(0) == pytest.approx(32.0)
    assert convert.celsius_to_fahrenheit(100) == pytest.approx(212.0)
    assert convert.celsius_to_fahrenheit(-40) == pytest.approx(-40.0)
    assert convert.celsius_to_fahrenheit(37.0) == pytest.approx(98.6)


def test_rejects_below_absolute_zero():
    import convert

    with pytest.raises(ValueError):
        convert.celsius_to_fahrenheit(-300)


def test_cli_prints_fahrenheit():
    script = os.path.join(os.environ["ANVIL_GENERATED_SRC"], "convert.py")
    proc = subprocess.run(
        [sys.executable, script, "100"],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert float(proc.stdout.strip()) == pytest.approx(212.0)
