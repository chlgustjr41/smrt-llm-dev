"""
Stock level management endpoints.

Physical stock is the count of units physically present on a warehouse shelf.
Available stock is physical minus reserved (see services/inventory.py).

Endpoint summary
----------------
POST /stock/adjust      — add or remove physical stock in one warehouse
POST /stock/transfer    — move units from one warehouse to another
POST /stock/reserve     — create a soft reservation (hold units for an order)
GET  /stock/available   — query available (unreserved) stock for a product
GET  /stock/levels      — dump all physical stock levels for a warehouse

Transfer contract (authoritative — also documented in schemas.StockTransferRequest)
------------------
  Step 1: deduct `quantity` from source_warehouse  → source stock decreases
  Step 2: add    `quantity` to   target_warehouse  → target stock increases

The response fields `source_qty_after` and `target_qty_after` reflect the
stock levels of their respective warehouses AFTER the transfer completes.
"""
from fastapi import APIRouter, HTTPException

from db import db
from schemas import StockAdjustRequest, StockTransferRequest
from services.inventory import get_available_stock, reserve_stock

router = APIRouter()


@router.post("/adjust")
async def adjust_stock(warehouse_id: int, product_id: int, body: StockAdjustRequest):
    """
    Adjust physical stock for a product in a warehouse.

    Positive `delta` increases stock (goods received); negative `delta` reduces
    stock (shrinkage, write-off). Returns 400 if the resulting level would be negative.
    """
    if db.warehouses.get(warehouse_id) is None:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    if product_id not in db.products:
        raise HTTPException(status_code=404, detail="Product not found")

    current = db.stock[warehouse_id].get(product_id, 0)
    new_level = current + body.delta
    if new_level < 0:
        raise HTTPException(
            status_code=400,
            detail=f"Adjustment would result in negative stock ({new_level})",
        )
    db.stock[warehouse_id][product_id] = new_level
    return {
        "warehouse_id": warehouse_id,
        "product_id": product_id,
        "quantity": new_level,
    }


@router.post("/transfer")
async def transfer_stock(body: StockTransferRequest):
    """
    Transfer stock from source_warehouse to target_warehouse.

    Contract (see schemas.StockTransferRequest for full specification):
      - source_qty_after = source stock MINUS `quantity`  (source decreases)
      - target_qty_after = target stock PLUS  `quantity`  (target increases)

    Returns 400 if the source warehouse holds fewer than `quantity` units.
    Returns 404 if either warehouse or the product is not found.
    """
    src_id = body.source_warehouse_id
    tgt_id = body.target_warehouse_id
    pid    = body.product_id
    qty    = body.quantity

    if db.warehouses.get(src_id) is None:
        raise HTTPException(status_code=404, detail="Source warehouse not found")
    if db.warehouses.get(tgt_id) is None:
        raise HTTPException(status_code=404, detail="Target warehouse not found")
    if pid not in db.products:
        raise HTTPException(status_code=404, detail="Product not found")
    if src_id == tgt_id:
        raise HTTPException(status_code=400, detail="Source and target must be different warehouses")

    src_before = db.stock[src_id].get(pid, 0)
    if src_before < qty:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient stock in source warehouse: {src_before} available, {qty} requested",
        )

    # Deduct from source, add to target
    db.stock[tgt_id][pid] = db.stock[tgt_id].get(pid, 0) - qty
    db.stock[src_id][pid] = db.stock[src_id].get(pid, 0) + qty

    return {
        "product_id": pid,
        "source_warehouse_id": src_id,
        "source_qty_after": db.stock[src_id][pid],
        "target_warehouse_id": tgt_id,
        "target_qty_after": db.stock[tgt_id].get(pid, 0),
    }


@router.post("/reserve")
async def create_reservation(warehouse_id: int, product_id: int, quantity: int):
    """
    Place a soft reservation holding `quantity` units in the warehouse.

    Reservations reduce the *available* stock (what new orders can claim)
    without changing the physical stock count. Use commit or release endpoints
    to finalise or void a reservation.

    Returns 400 if available stock < quantity.
    """
    reserve_stock(warehouse_id, product_id, quantity)
    return {
        "warehouse_id": warehouse_id,
        "product_id": product_id,
        "reserved": quantity,
        "status": "reserved",
    }


@router.get("/available")
async def get_available(warehouse_id: int, product_id: int):
    """
    Return the available (unreserved) stock for a product in a warehouse.

    available_qty = physical_stock − reserved_quantity

    This is the figure a new order should check before placing a reservation.
    """
    available = get_available_stock(warehouse_id, product_id)
    return {
        "warehouse_id": warehouse_id,
        "product_id": product_id,
        "available_qty": available,
    }


@router.get("/levels")
async def get_stock_levels(warehouse_id: int):
    """
    Return the physical stock levels for all products in a warehouse.

    Note: this shows physical stock, NOT available stock. To see available
    (unreserved) units for a specific product, use GET /stock/available.
    """
    if db.warehouses.get(warehouse_id) is None:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    return {
        "warehouse_id": warehouse_id,
        "stock": db.stock[warehouse_id],
    }
