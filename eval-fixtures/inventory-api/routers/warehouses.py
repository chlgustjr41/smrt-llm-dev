"""
Warehouse management endpoints.

A warehouse represents a physical storage location. Each warehouse maintains
its own stock ledger (see /stock endpoints). Warehouses are never hard-deleted
to preserve historical order references; use DELETE to deactivate instead.

Endpoint summary
----------------
POST   /warehouses              — register a new warehouse
GET    /warehouses              — list all warehouses (active and inactive)
GET    /warehouses/{id}         — fetch a single warehouse
DELETE /warehouses/{id}         — deactivate a warehouse (soft delete, active=False)
"""
from fastapi import APIRouter, HTTPException, status

from db import db
from schemas import WarehouseCreate, WarehouseOut

router = APIRouter()


@router.post("", status_code=status.HTTP_201_CREATED, response_model=WarehouseOut)
async def create_warehouse(body: WarehouseCreate):
    """
    Register a new warehouse.

    Initialises empty stock and reservation ledgers for the new warehouse so
    that /stock/adjust and /stock/transfer can operate on it immediately.
    Returns the created warehouse with its server-assigned integer ID.
    """
    db.warehouse_seq += 1
    wid = db.warehouse_seq
    warehouse = {
        "id": wid,
        "name": body.name,
        "location": body.location,
        "active": True,
    }
    db.warehouses[wid] = warehouse
    # Initialise empty stock and reservation ledgers for this warehouse
    db.stock[wid] = {}
    db.reserved[wid] = {}
    return warehouse


@router.get("", response_model=list[WarehouseOut])
async def list_warehouses():
    """Return all warehouses. Both active (active=True) and deactivated (active=False) are included."""
    return list(db.warehouses.values())


@router.get("/{warehouse_id}", response_model=WarehouseOut)
async def get_warehouse(warehouse_id: int):
    """Return a single warehouse by its ID. Returns 404 if not found."""
    wh = db.warehouses.get(warehouse_id)
    if wh is None:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    return wh


@router.delete("/{warehouse_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_warehouse(warehouse_id: int):
    """
    Deactivate a warehouse (soft delete).

    Sets active=False. Physical stock records are retained so that historical
    orders referencing this warehouse remain valid. Stock transfers from an
    inactive warehouse are still allowed — check active status in your client
    if you wish to prevent this.
    """
    wh = db.warehouses.get(warehouse_id)
    if wh is None:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    wh["active"] = False
