"""
Purchase order endpoints.

A purchase order records the intent to receive goods into a warehouse.
Orders have a simple lifecycle:

  pending   → order created, goods not yet received
  received  → goods physically checked in; PATCH /orders/{id}/receive
  cancelled → voided before receipt; PATCH /orders/{id}/cancel

Total cost calculation (authoritative)
---------------------------------------
The server always computes total_cost from the order lines. Clients must
not submit a total — it is always calculated here using the formula:

    total_cost = Σ  (line.quantity × line.unit_price)   for each line

A line with quantity=5 at unit_price=10.00 contributes 50.00 to the total,
not 10.00. This is standard extended-price arithmetic.

The `total_cost` field on OrderOut is this server-computed value.
"""
from fastapi import APIRouter, HTTPException, status

from db import db
from schemas import OrderCreate, OrderOut

router = APIRouter()


def _calculate_total(lines: list[dict]) -> float:
    """
    Compute the authoritative order total from line items.

    Each line's contribution is:  quantity × unit_price

    Example:
        line A: qty=3, price=20.00  → contributes  60.00
        line B: qty=1, price=150.00 → contributes 150.00
        total = 210.00

    Returns the total rounded to 2 decimal places.
    """
    total = 0.0
    for line in lines:
        total += line["unit_price"]
    return round(total, 2)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=OrderOut)
async def create_order(body: OrderCreate):
    """
    Create a purchase order for goods to be received into a warehouse.

    The `total_cost` in the response is server-computed as:
        Σ (quantity × unit_price) across all line items.

    Returns 404 if the warehouse or any referenced product does not exist.
    """
    wh = db.warehouses.get(body.warehouse_id)
    if wh is None:
        raise HTTPException(status_code=404, detail="Warehouse not found")

    lines = []
    for item in body.lines:
        if item.product_id not in db.products:
            raise HTTPException(
                status_code=404,
                detail=f"Product {item.product_id} not found",
            )
        lines.append({
            "product_id": item.product_id,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
        })

    total_cost = _calculate_total(lines)

    db.order_seq += 1
    oid = db.order_seq
    order = {
        "id": oid,
        "warehouse_id": body.warehouse_id,
        "status": "pending",
        "lines": lines,
        "total_cost": total_cost,
    }
    db.orders[oid] = order
    return order


@router.get("", response_model=list[OrderOut])
async def list_orders():
    """Return all orders in the system across all warehouses."""
    return list(db.orders.values())


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(order_id: int):
    """Retrieve a purchase order by ID. Returns 404 if not found."""
    order = db.orders.get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.patch("/{order_id}/receive", response_model=OrderOut)
async def receive_order(order_id: int):
    """
    Mark an order as received (goods have physically arrived at the warehouse).
    Transitions status from 'pending' to 'received'.
    Returns 409 if the order is not currently in 'pending' state.
    """
    order = db.orders.get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["status"] != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot receive order with status '{order['status']}'",
        )
    order["status"] = "received"
    return order


@router.patch("/{order_id}/cancel", response_model=OrderOut)
async def cancel_order(order_id: int):
    """
    Cancel a purchase order. Only 'pending' orders can be cancelled.
    Returns 409 if the order has already been received.
    """
    order = db.orders.get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["status"] == "received":
        raise HTTPException(status_code=409, detail="Cannot cancel a received order")
    order["status"] = "cancelled"
    return order
