"""Held-out acceptance tests for inventory-lib. The agent never sees these."""

import pytest


def _make():
    from inventory import Inventory

    return Inventory()


def test_add_and_query():
    inv = _make()
    inv.add_item("apple", 10, 0.5)
    assert inv.get_quantity("apple") == 10
    assert inv.get_quantity("unknown") == 0


def test_add_existing_accumulates_and_updates_price():
    inv = _make()
    inv.add_item("apple", 10, 0.5)
    inv.add_item("apple", 5, 0.6)
    assert inv.get_quantity("apple") == 15
    assert inv.total_value() == pytest.approx(15 * 0.6)


def test_add_validation():
    inv = _make()
    with pytest.raises(ValueError):
        inv.add_item("apple", 0, 0.5)
    with pytest.raises(ValueError):
        inv.add_item("apple", 1, -0.01)


def test_remove_and_depletion():
    inv = _make()
    inv.add_item("banana", 3, 1.0)
    inv.remove_item("banana", 2)
    assert inv.get_quantity("banana") == 1
    inv.remove_item("banana", 1)
    assert inv.get_quantity("banana") == 0


def test_remove_validation():
    inv = _make()
    inv.add_item("cherry", 2, 2.0)
    with pytest.raises(ValueError):
        inv.remove_item("cherry", 3)
    with pytest.raises(ValueError):
        inv.remove_item("unknown", 1)


def test_total_value():
    inv = _make()
    inv.add_item("apple", 10, 0.5)
    inv.add_item("banana", 4, 1.25)
    assert inv.total_value() == pytest.approx(10.0)


def test_save_load_round_trip(tmp_path):
    from inventory import Inventory

    inv = _make()
    inv.add_item("apple", 10, 0.5)
    inv.add_item("banana", 4, 1.25)
    path = str(tmp_path / "inventory.json")
    inv.save(path)
    restored = Inventory.load(path)
    assert restored.get_quantity("apple") == 10
    assert restored.get_quantity("banana") == 4
    assert restored.total_value() == pytest.approx(inv.total_value())
