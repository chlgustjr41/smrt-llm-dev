# inventory-api — Planted Bugs Answer Key

> **EVALUATOR ONLY.** This file is listed in `.agentignore` so all SMRT agents
> (Reviewer, QA, Coder) are denied read access during evaluation. Bugs must be
> discovered dynamically through code inspection, test execution, and the clues
> embedded in comments and docstrings — not by reading this file.

---

## Bug #1 — Variable Swap: stock transfer modifies wrong warehouses

**File:** `routers/stock.py`, function `transfer_stock` (~line 75)

**Expected behavior:**
`POST /stock/transfer` must deduct `quantity` from the **source** warehouse and
add `quantity` to the **target** warehouse. Both the module docstring and
`schemas.StockTransferRequest` document this in two places.

**Actual behavior (with bug):**
The warehouse IDs are swapped in the two assignment lines:
```python
db.stock[tgt_id][pid] = db.stock[tgt_id].get(pid, 0) - qty   # Line A: deducts from TARGET
db.stock[src_id][pid] = db.stock[src_id].get(pid, 0) + qty   # Line B: adds to SOURCE
```
After a transfer, the source warehouse *gains* stock and the target *loses* stock —
the exact opposite of the contract.

**Fix:**
```python
db.stock[src_id][pid] = db.stock[src_id].get(pid, 0) - qty   # deduct from source
db.stock[tgt_id][pid] = db.stock[tgt_id].get(pid, 0) + qty   # add to target
```

**Failing tests:** `test_stock_transfer.py::test_transfer_deducts_from_source`,
`test_transfer_adds_to_target`, `test_transfer_persisted_correctly`

---

## Bug #2 — Missing subtraction: available stock ignores reservations

**File:** `services/inventory.py`, function `get_available_stock` (~line 48)

**Expected behavior:**
`available = physical_stock − reserved_quantity`
The function's own docstring and the module-level docstring state this formula
explicitly. Reservations must reduce the visible available count.

**Actual behavior (with bug):**
The reserved count is read into a local variable but never subtracted:
```python
reserved = db.reserved[warehouse_id].get(product_id, 0)  # computed but unused
return physical  # always returns raw physical count
```
Reservations have no effect on availability. Concurrent orders can book the
same reserved units, causing over-selling.

**Fix:**
```python
reserved = db.reserved[warehouse_id].get(product_id, 0)
return physical - reserved
```

**Failing tests:** `test_available_stock.py::test_available_decreases_after_reservation`,
`test_second_reservation_blocked_when_available_exhausted`

---

## Bug #3 — Missing multiplier: order total ignores quantity

**File:** `routers/orders.py`, function `_calculate_total` (~line 55)

**Expected behavior:**
`total_cost = Σ (line.quantity × line.unit_price)` across all lines.
This is stated in the `_calculate_total` docstring with a worked example,
in the `OrderCreate` schema docstring, and in the module-level docstring.

**Actual behavior (with bug):**
```python
total += line["unit_price"]   # quantity never multiplied in
```
A line for 5 units at $10.00 contributes $10.00 instead of $50.00.
Any order with quantity > 1 is systematically under-charged.

**Fix:**
```python
total += line["quantity"] * line["unit_price"]
```

**Failing tests:** `test_order_total.py::test_single_line_order_total_includes_quantity`,
`test_multi_line_order_total`

---

## Bug #4 — Off-by-one: low-stock threshold is exclusive instead of inclusive

**File:** `routers/reports.py`, function `low_stock_alerts` (~line 62)

**Expected behavior:**
Alert when `available_quantity <= threshold` (at or below — inclusive).
The module docstring, the endpoint docstring, and an inline comment all
state the inclusive rule explicitly.

**Actual behavior (with bug):**
```python
if available < threshold:   # strict less-than, exclusive
```
A product at exactly `threshold` units is NOT flagged. The buyer is not
notified until stock drops one unit below the threshold — too late.

**Fix:**
```python
if available <= threshold:
```

**Failing tests:** `test_low_stock_alerts.py::test_product_at_exact_threshold_is_alerted`,
`test_custom_threshold_respected`

---

## Bug #5 — Wrong predicate: soft-delete filter always evaluates True

**File:** `routers/products.py`, function `list_products` (~line 57)

**Expected behavior:**
`GET /products` returns only active (non-deleted) products. The module docstring
states the invariant: "every item in the GET /products response must have
deleted == False."

**Actual behavior (with bug):**
```python
if product.get("deleted") is not None:   # always True
```
Every product record is created with an explicit `deleted=False` key, so
`product.get("deleted")` is never `None` — it returns `False` for active
products and `True` for deleted ones. The `is not None` check therefore
passes for *both* states, and soft-deleted products appear in the listing.

**Fix:**
```python
if not product.get("deleted", False):
```

**Failing tests:** `test_product_soft_delete.py::test_deleted_product_not_in_list`,
`test_list_contains_no_deleted_products`

---

## Evaluation scoring

| Bug | File | Nature | Difficulty |
|-----|------|--------|------------|
| #1 — Transfer swap | `routers/stock.py` | Variable swap | Medium |
| #2 — Reservations ignored | `services/inventory.py` | Unused variable | Medium |
| #3 — Quantity not multiplied | `routers/orders.py` | Missing factor | Easy |
| #4 — Off-by-one threshold | `routers/reports.py` | Wrong operator | Easy |
| #5 — Always-true filter | `routers/products.py` | Wrong predicate | Medium |
