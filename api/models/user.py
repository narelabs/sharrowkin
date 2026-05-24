from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict


class User(BaseModel):
    """User model with validation for email and age."""
    
    model_config = ConfigDict(str_strip_whitespace=True)
    
    id: Optional[int] = Field(default=None, description="User ID")
    name: str = Field(..., min_length=1, description="User name")
    email: EmailStr = Field(..., description="User email address")
    age: int = Field(..., ge=18, description="User age (must be 18 or older)")
    
    @field_validator('age')
    @classmethod
    def validate_age(cls, v: int) -> int:
        """Validate that age is at least 18."""
        if v < 18:
            raise ValueError('Age must be 18 or older')
        return v
