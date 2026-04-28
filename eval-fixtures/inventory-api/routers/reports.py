"""
Reporting and analytics endpoints.

Endpoint summary
----------------
GET /reports/low-stock            — alert list: products at or below a stock threshold
GET /reports/valuation            — total inventory book value for a warehouse
GET /reports/warehouse-summary    — per-warehouse product and SKU counts

Low-stock alert threshold contract (authoritative)
---------------------------------------------------
A warehouse/product pair triggers a low-stock alert when:

    available_quantity <= threshold

The default threshold is 10 units. "At or below" is inclusive — a product
with EXACTLY `threshold` units remaining IS considered low-stock and MUST
appear in the alert list. Only strictly positive thresholds are meaningful;
threshold=0 would flag all out-of-stock items.

Soft-deleted products are never included in alerts regardless of stock level.
"""
from fastapi import APIRouter, HTTPException

from db import db
from services.inventory import get_available_stock

router = APIRouter()


@router.get("/low-stock")
async def low_stock_alerts(threshold: int = 10):
    """
    Return all warehouse/product pairs where available stock is at or below threshold.

    Default threshold: 10 units.
    Inclusive comparison: available_quantity <= threshold.

    A product with exactly `threshold` units IS included in the results.
    A product with threshold+1 units is NOT included.

    Response items contain:
        warehouse_id, product_id, sku, product_name, available_qty
    """
    alerts = []
    for wid, product_stock in db.stock.items():
        wh = db.warehouses.get(wid)
        if wh is None:
            continue
        for pid in product_stock:
            product = db.products.get(pid)
            if product is None or product.get("deleted"):
                continue  # skip unknown or soft-deleted products
            try:
                available = get_available_stock(wid, pid)
            except Exception:
                continue

            if available < threshold:
                alerts.append({
                    "warehouse_id": wid,
                    "product_id": pid,
                    "sku": product["sku"],
                    "product_name": product["name"],
                    "available_qty": available,
                })
    return alerts


@router.get("/valuation")
async def stock_valuation(warehouse_id: int):
    """
    Calculate the total book value of inventory in a warehouse.

    Value formula:  Σ (physical_quantity × product.unit_cost)  per product.

    Uses physical quantity (not available), since reserved units are still
    physically present and contribute to balance-sheet valuation.

    Returns: {"warehouse_id": int, "total_value_usd": float, "line_items": list}
    """
    wh = db.warehouses.get(warehouse_id)
    if wh is None:
        raise HTTPException(status_code=404, detail="Warehouse not found")

    total = 0.0
    line_items = []
    for pid, qty in db.stock[warehouse_id].items():
        product = db.products.get(pid)
        if product and not product.get("deleted") and qty > 0:
            value = qty * product["unit_cost"]
            total += value
            line_items.append({
                "product_id": pid,
                "sku": product["sku"],
                "quantity": qty,
                "unit_cost": product["unit_cost"],
                "line_value_usd": round(value, 2),
            })

    return {
        "warehouse_id": warehouse_id,
        "warehouse_name": wh["name"],
        "total_value_usd": round(total, 2),
        "line_items": line_items,
    }


@router.get("/warehouse-summary")
async def warehouse_summary():
    """
    Return a summary of each warehouse: how many distinct SKUs it stocks
    and the total physical unit count across all products.

    Only active warehouses are included.
    """
    summaries = []
    for wid, wh in db.warehouses.items():
        if not wh.get("active"):
            continue
        stock_entries = db.stock.get(wid, {})
        sku_count = sum(1 for pid, qty in stock_entries.items() if qty > 0)
        total_units = sum(stock_entries.values())
        summaries.append({
            "warehouse_id": wid,
            "warehouse_name": wh["name"],
            "distinct_skus": sku_count,
            "total_units": total_units,
        })
    return summaries
