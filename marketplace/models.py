"""Marketplace models for Sharrowkin."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class Category(BaseModel):
    """Product category."""
    id: str
    name: str
    description: Optional[str] = None
    parent_id: Optional[str] = None


class Product(BaseModel):
    """Marketplace product."""
    id: str
    name: str
    description: str
    price: float = Field(gt=0, description="Price must be positive")
    category_id: str
    seller_id: str
    image_url: Optional[str] = None
    stock: int = Field(ge=0, description="Stock cannot be negative")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ProductCreate(BaseModel):
    """Create product request."""
    name: str
    description: str
    price: float = Field(gt=0)
    category_id: str
    image_url: Optional[str] = None
    stock: int = Field(ge=0, default=0)


class ProductUpdate(BaseModel):
    """Update product request."""
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = Field(None, gt=0)
    category_id: Optional[str] = None
    image_url: Optional[str] = None
    stock: Optional[int] = Field(None, ge=0)
