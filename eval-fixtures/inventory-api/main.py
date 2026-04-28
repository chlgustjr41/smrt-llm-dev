"""
inventory-api — multi-warehouse inventory management service.

A FastAPI application for tracking product stock levels across multiple
warehouse locations, managing purchase orders, and reporting inventory health.

Architecture
------------
Routes are split across four domain routers:

  /warehouses  — warehouse CRUD (routers/warehouses.py)
  /products    — product catalog with soft-delete (routers/products.py)
  /stock       — stock adjustments, transfers, and reservations (routers/stock.py)
  /orders      — purchase order lifecycle (routers/orders.py)
  /reports     — analytics: low-stock alerts, valuation (routers/reports.py)

Business logic is in services/:

  services/inventory.py — stock availability and reservation engine

All state is in-memory (db.py) and is reset on process restart.
This is intentional — the service is designed for evaluation and testing.

Running locally
---------------
    pip install -r requirements.txt
    uvicorn main:app --reload

Interactive docs available at http://localhost:8000/docs
"""
from fastapi import FastAPI

from routers import warehouses, products, stock, orders, reports

app = FastAPI(
    title="Inventory API",
    version="1.0.0",
    description=__doc__,
)

app.include_router(warehouses.router, prefix="/warehouses", tags=["warehouses"])
app.include_router(products.router,   prefix="/products",   tags=["products"])
app.include_router(stock.router,      prefix="/stock",      tags=["stock"])
app.include_router(orders.router,     prefix="/orders",     tags=["orders"])
app.include_router(reports.router,    prefix="/reports",    tags=["reports"])


@app.get("/health", tags=["meta"])
async def health():
    """Liveness probe. Returns {"status": "ok"} when the server is running."""
    return {"status": "ok"}
