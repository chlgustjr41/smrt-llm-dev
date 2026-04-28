"""
inventory-api in-memory database.

Simulates a multi-warehouse inventory persistence layer. All endpoints
operate on the shared `db` singleton. A real system would use PostgreSQL
or a distributed store; this uses Python dicts for evaluation portability.

Data model
----------
warehouses : {warehouse_id: {id, name, location, active}}
products   : {product_id: {id, sku, name, unit_cost, deleted}}
stock      : {warehouse_id: {product_id: physical_quantity}}
reserved   : {warehouse_id: {product_id: reserved_quantity}}
orders     : {order_id: {id, warehouse_id, status, lines: [...], total_cost}}

Stock accounting
----------------
For any warehouse/product pair, two counters are maintained:

  physical_quantity — total units actually on the shelf
  reserved_quantity — units soft-held by pending reservations

  available_quantity = physical_quantity - reserved_quantity

The `reserved` counter prevents over-selling: units reserved for one
order are not visible to subsequent availability checks.
"""
from typing import Any


class DB:
    def __init__(self) -> None:
        self.warehouses:    dict[int, dict[str, Any]] = {}
        self.products:      dict[int, dict[str, Any]] = {}
        self.stock:         dict[int, dict[int, int]] = {}  # [wh_id][prod_id] = qty
        self.reserved:      dict[int, dict[int, int]] = {}  # [wh_id][prod_id] = reserved
        self.orders:        dict[int, dict[str, Any]] = {}
        self.warehouse_seq: int = 0
        self.product_seq:   int = 0
        self.order_seq:     int = 0

    def reset(self) -> None:
        """Clear all state. Called by test fixtures to guarantee isolation."""
        self.__init__()


# Module-level singleton shared by all routers and services.
db = DB()
