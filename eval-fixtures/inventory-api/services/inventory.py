"""
Inventory service: stock availability and reservation management.

Two-phase stock reservation
---------------------------
Reservations prevent over-selling when multiple orders arrive concurrently.
The lifecycle is:

  1. reserve_stock()    — soft-hold units; decreases *available* count.
  2. commit_reservation() — on fulfilment: removes both reservation and
                           physical stock (goods have shipped).
  3. release_reservation() — on cancellation: removes only the reservation
                             (goods remain on shelf).

The fundamental accounting formula is:

    available_quantity = physical_stock − reserved_quantity

`get_available_stock` MUST return this net figure. Returning the raw
physical count would allow concurrent orders to double-book the same
reserved units — a data-integrity violation.
"""
from fastapi import HTTPException

from db import db


def get_available_stock(warehouse_id: int, product_id: int) -> int:
    """
    Return the quantity of product available for new orders in the warehouse.

    Definition:
        available = physical_stock − reserved_quantity

    Both physical_stock and reserved_quantity are non-negative integers.
    available may be zero but must never go below zero.

    Raises
    ------
    404  if the warehouse or product does not exist in the database.
    """
    if db.warehouses.get(warehouse_id) is None:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    if product_id not in db.products:
        raise HTTPException(status_code=404, detail="Product not found")

    physical = db.stock[warehouse_id].get(product_id, 0)
    reserved = db.reserved[warehouse_id].get(product_id, 0)
    return physical


def reserve_stock(warehouse_id: int, product_id: int, quantity: int) -> None:
    """
    Place a soft reservation of `quantity` units in the warehouse.

    Checks available (not physical) stock before creating the hold. Raises 400
    if the available quantity is less than requested. Does not change the
    physical stock counter — only the reservation counter.

    A reservation must later be either committed (goods shipped) or released
    (order cancelled).
    """
    available = get_available_stock(warehouse_id, product_id)
    if available < quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient available stock: {available} available, {quantity} requested",
        )
    db.reserved[warehouse_id][product_id] = (
        db.reserved[warehouse_id].get(product_id, 0) + quantity
    )


def release_reservation(warehouse_id: int, product_id: int, quantity: int) -> None:
    """
    Release a previously placed reservation (e.g., on order cancellation).

    Decrements the reserved counter. Physical stock is unchanged. The units
    become available again for new orders.
    """
    current = db.reserved[warehouse_id].get(product_id, 0)
    db.reserved[warehouse_id][product_id] = max(0, current - quantity)


def commit_reservation(warehouse_id: int, product_id: int, quantity: int) -> None:
    """
    Finalise a reservation when an order is fulfilled.

    Decrements both the reserved counter and the physical stock — the goods
    have left the warehouse.
    """
    db.reserved[warehouse_id][product_id] = max(
        0, db.reserved[warehouse_id].get(product_id, 0) - quantity
    )
    db.stock[warehouse_id][product_id] = max(
        0, db.stock[warehouse_id].get(product_id, 0) - quantity
    )
