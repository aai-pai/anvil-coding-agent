"""Held-out acceptance tests for usd-cents. The agent never sees these."""

import pytest


def test_basic_conversion():
    import currency

    assert currency.usd_to_cents(1.00) == 100
    assert currency.usd_to_cents(0) == 0
    assert currency.usd_to_cents(19.99) == 1999


def test_half_up_rounding_avoids_float_artifacts():
    import currency

    assert currency.usd_to_cents(1.005) == 101
    assert currency.usd_to_cents(2.675) == 268


def test_negative_raises():
    import currency

    with pytest.raises(ValueError):
        currency.usd_to_cents(-0.01)


def test_cents_to_usd_formatting():
    import currency

    assert currency.cents_to_usd(101) == "$1.01"
    assert currency.cents_to_usd(0) == "$0.00"
    assert currency.cents_to_usd(123456) == "$1234.56"
