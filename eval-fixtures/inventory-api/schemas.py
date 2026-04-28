"""
Pydantic request/response schemas for the Inventory API.

Monetary values are stored as float (USD). Quantities are non-negative integers.
All response models are typed so callers can rely on the documented shape.
"""
from typing import Optional
from pydantic import BaseModel, Field


# ── Warehouses ────────────────────────────────────────────────────────────────

class WarehouseCreate(BaseModel):
    """Request body for registering a new warehouse location."""
    name: str = Field(..., description="Human-readable name, e.g. 'East Coast Hub'")
    location: str = Field(..., description="Physical address or region label")


class WarehouseOut(BaseModel):
    id: int
    name: str
    location: str
    active: bool


# ── Products ──────────────────────────────────────────────────────────────────

class ProductCreate(BaseModel):
    """
    Request body for adding a product to the catalog.

    `unit_cost` is the standard purchase cost per unit in USD. It is stored
    in the catalog and used for inventory valuation reports.
    """
    sku: str = Field(..., description="Stock-keeping unit code; must be globally unique")
    name: str = Field(..., description="Product display name")
    unit_cost: float = Field(..., gt=0, description="Purchase cost per unit in USD")


class ProductOut(BaseModel):
    id: int
    sku: str
    name: str
    unit_cost: float
    deleted: bool = False


# ── Stock ────────────────────────────────────────────────────────────────────

class StockAdjustRequest(BaseModel):
    """
    Adjust physical stock in a warehouse.
    `delta` > 0 adds units; `delta` < 0 removes units.
    The resulting stock level must not go below zero.
    """
    delta: int = Field(..., description="Units to add (positive) or remove (negative)")


class StockTransferRequest(BaseModel):
    """
    Transfer stock between two warehouses.

    Step-by-step contract:
      1. Deduct `quantity` units from source_warehouse_id (source stock decreases).
      2. Add    `quantity` units to   target_warehouse_id (target stock increases).

    Both source and target stock levels are returned in the response
    (source_qty_after, target_qty_after) so the caller can verify atomicity.
    """
    source_warehouse_id: int
    target_warehouse_id: int
    product_id: int
    quantity: int = Field(..., gt=0, description="Number of units to move")


# ── Orders ────────────────────────────────────────────────────────────────────

class OrderLineCreate(BaseModel):
    """
    A single line item within a purchase order.

    The extended cost for this line is:
        extended_cost = quantity × unit_price

    Clients must not supply a line-level subtotal — the server always
    recomputes it from quantity and unit_price.
    """
    product_id: int
    quantity: int = Field(..., gt=0, description="Number of units ordered")
    unit_price: float = Field(
        ..., gt=0, description="Agreed price per unit in USD at time of order"
    )


class OrderCreate(BaseModel):
    """
    Create a purchase order for goods to be received into a warehouse.

    The `total_cost` field in the response is server-computed as:
        total_cost = Σ (quantity × unit_price) for each line

    Clients must not submit a total — it will be ignored in favour of
    the authoritative server-side calculation.
    """
    warehouse_id: int
    lines: list[OrderLineCreate] = Field(..., min_length=1)


class OrderOut(BaseModel):
    id: int
    warehouse_id: int
    status: str  # "pending" | "received" | "cancelled"
    lines: list[dict]
    total_cost: float  # server-calculated: Σ(qty × unit_price) across all lines
