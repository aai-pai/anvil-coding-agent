# Inventory management library

Build a Python library for tracking a small shop's inventory, with JSON
persistence, input validation, and a pytest suite covering the edge cases.

## Interface contract (must be followed exactly)

- The source file must be `src/inventory.py`, defining a class `Inventory`.
- `Inventory()` starts empty. Methods:
  - `add_item(name: str, quantity: int, unit_price: float) -> None` — adds
    stock. Adding an existing item name increases its quantity; the unit
    price is updated to the latest value. `quantity <= 0` or
    `unit_price < 0` must raise `ValueError`.
  - `remove_item(name: str, quantity: int) -> None` — removes stock. Removing
    more than is available, or an unknown item, must raise `ValueError`.
    When an item's quantity reaches 0 it is deleted entirely.
  - `get_quantity(name: str) -> int` — current stock, `0` for unknown items.
  - `total_value() -> float` — sum of `quantity * unit_price` over all items.
  - `save(path: str) -> None` — write the inventory to a JSON file.
  - `Inventory.load(path: str) -> Inventory` — classmethod restoring exactly
    what `save` wrote (round-trip must preserve quantities, prices, and
    `total_value()`).

Standard library only.
