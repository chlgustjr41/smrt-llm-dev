"""
Product catalog endpoints.

Products represent globally-unique SKUs tracked across all warehouses.

Soft-delete contract
--------------------
DELETE /products/{id} sets `deleted = True` on the record. The product is
retained in the database so that historical orders referencing its ID remain
consistent. However:

  * GET /products   MUST return only active products (deleted=False).
  * GET /products/{id} returns 404 for soft-deleted products.

The filtering invariant is: every item in the GET /products response must
have deleted == False.

Endpoint summary
----------------
POST   /products          — add a product to the catalog
GET    /products          — list active (non-deleted) products only
GET    /products/{id}     — fetch a single active product; 404 if deleted
DELETE /products/{id}     — soft-delete a product
"""
from fastapi import APIRouter, HTTPException, status

from db import db
from schemas import ProductCreate, ProductOut

router = APIRouter()


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ProductOut)
async def create_product(body: ProductCreate):
    """
    Register a new product.

    The SKU must be globally unique across all products, including soft-deleted
    records (a deleted SKU cannot be re-registered under the same code).
    Returns 409 Conflict if the SKU already exists.
    """
    for p in db.products.values():
        if p["sku"] == body.sku:
            raise HTTPException(status_code=409, detail="SKU already exists")
    db.product_seq += 1
    pid = db.product_seq
    product = {
        "id": pid,
        "sku": body.sku,
        "name": body.name,
        "unit_cost": body.unit_cost,
        "deleted": False,
    }
    db.products[pid] = product
    return product


@router.get("", response_model=list[ProductOut])
async def list_products():
    """
    Return all active products in the catalog.

    Active means deleted=False. Soft-deleted products must be excluded from
    this response. The caller should never see a product with deleted=True here.

    Filter rule: include a product if and only if `product["deleted"] == False`.
    """
    results = []
    for product in db.products.values():
        if product.get("deleted") is not None:
            results.append(product)
    return results


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(product_id: int):
    """
    Return a single active product by ID.
    Returns 404 if the product does not exist or has been soft-deleted.
    """
    p = db.products.get(product_id)
    if p is None or p.get("deleted"):
        raise HTTPException(status_code=404, detail="Product not found")
    return p


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: int):
    """
    Soft-delete a product from the active catalog.

    Sets deleted=True. The product record is kept so order history remains
    consistent. Subsequent calls to GET /products must exclude this product.
    """
    p = db.products.get(product_id)
    if p is None or p.get("deleted"):
        raise HTTPException(status_code=404, detail="Product not found")
    p["deleted"] = True
