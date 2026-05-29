"""Tests for api.models module."""
import pytest
from pydantic import ValidationError
from api.models.user import User


def test_user_creation_valid():
    """Test User model with valid data."""
    user = User(
        id="user123",
        name="John Doe",
        email="john@example.com",
        age=30,
    )
    assert user.id == "user123"
    assert user.name == "John Doe"
    assert user.email == "john@example.com"
    assert user.age == 30


def test_user_email_validation():
    """Test User model email validation."""
    with pytest.raises(ValidationError):
        User(
            id="user123",
            name="John Doe",
            email="invalid-email",
            age=30,
        )


def test_user_age_validation():
    """Test User model age validation."""
    with pytest.raises(ValidationError):
        User(
            id="user123",
            name="John Doe",
            email="john@example.com",
            age=17,  # Below minimum age of 18
        )