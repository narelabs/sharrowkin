"""Marketplace API router."""

from fastapi import APIRouter, HTTPException
from typing import List
import uuid
from datetime import datetime

from .models import Product, ProductCreate, ProductUpdate, Category

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])

# In-memory storage (replace with database in production)
products_db: dict[str, Product] = {}
categories_db: dict[str, Category] = {
    "cat1": Category(id="cat1", name="Electronics", description="Electronic devices"),
    "cat2": Category(id="cat2", name="Books", description="Books and publications"),
    "cat3": Category(id="cat3", name="Clothing", description="Apparel and accessories"),
}


@router.get("/categories", response_model=List[Category])
async def list_categories():
    """Get all categories."""
    return list(categories_db.values())


@router.get("/products", response_model=List[Product])
async def list_products(category_id: str | None = None):
    """Get all products, optionally filtered by category."""
    products = list(products_db.values())

    if category_id:
        products = [p for p in products if p.category_id == category_id]

    return products


@router.get("/products/{product_id}", response_model=Product)
async def get_product(product_id: str):
    """Get product by ID."""
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail="Product not found")

    return products_db[product_id]


@router.post("/products", response_model=Product)
async def create_product(product: ProductCreate, seller_id: str = "default_seller"):
    """Create a new product."""
    # Validate category exists
    if product.category_id not in categories_db:
        raise HTTPException(status_code=400, detail="Category not found")

    product_id = str(uuid.uuid4())

    new_product = Product(
        id=product_id,
        name=product.name,
        description=product.description,
        price=product.price,
        category_id=product.category_id,
        seller_id=seller_id,
        image_url=product.image_url,
        stock=product.stock,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    products_db[product_id] = new_product
    return new_product


@router.put("/products/{product_id}", response_model=Product)
async def update_product(product_id: str, product_update: ProductUpdate):
    """Update a product."""
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail="Product not found")

    product = products_db[product_id]

    # Update fields if provided
    if product_update.name is not None:
        product.name = product_update.name
    if product_update.description is not None:
        product.description = product_update.description
    if product_update.price is not None:
        product.price = product_update.price
    if product_update.category_id is not None:
        if product_update.category_id not in categories_db:
            raise HTTPException(status_code=400, detail="Category not found")
        product.category_id = product_update.category_id
    if product_update.image_url is not None:
        product.image_url = product_update.image_url
    if product_update.stock is not None:
        product.stock = product_update.stock

    product.updated_at = datetime.utcnow()
    products_db[product_id] = product

    return product


@router.delete("/products/{product_id}")
async def delete_product(product_id: str):
    """Delete a product."""
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail="Product not found")

    del products_db[product_id]
    return {"success": True, "message": "Product deleted"}


@router.get("/stats")
async def get_marketplace_stats():
    """Get marketplace statistics."""
    return {
        "total_products": len(products_db),
        "total_categories": len(categories_db),
        "products_by_category": {
            cat_id: len([p for p in products_db.values() if p.category_id == cat_id])
            for cat_id in categories_db.keys()
        }
    }
