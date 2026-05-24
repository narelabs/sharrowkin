import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from api.routes.users import router

# Create test app
app = FastAPI()
app.include_router(router)

client = TestClient(app)


def test_create_user_success():
    """Test successful user creation."""
    user_data = {
        "name": "John Doe",
        "email": "john@example.com",
        "age": 25
    }
    
    response = client.post("/users/", json=user_data)
    
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["name"] == "John Doe"
    assert data["email"] == "john@example.com"
    assert data["age"] == 25


def test_create_user_invalid_email():
    """Test user creation with invalid email."""
    user_data = {
        "name": "Jane Doe",
        "email": "invalid-email",
        "age": 30
    }
    
    response = client.post("/users/", json=user_data)
    
    assert response.status_code == 422
    assert "email" in response.text.lower() or "value_error" in response.text.lower()


def test_create_user_age_under_18():
    """Test user creation with age under 18."""
    user_data = {
        "name": "Young User",
        "email": "young@example.com",
        "age": 17
    }
    
    response = client.post("/users/", json=user_data)
    
    assert response.status_code == 422
    error_detail = response.json()["detail"]
    # Check that age validation error is present
    assert any(
        "age" in str(err).lower() and ("18" in str(err) or "greater" in str(err).lower())
        for err in error_detail
    )


def test_get_user_success():
    """Test successful user retrieval."""
    # First create a user
    user_data = {
        "name": "Alice Smith",
        "email": "alice@example.com",
        "age": 28
    }
    
    create_response = client.post("/users/", json=user_data)
    assert create_response.status_code == 201
    user_id = create_response.json()["id"]
    
    # Now retrieve the user
    get_response = client.get(f"/users/{user_id}")
    
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["id"] == user_id
    assert data["name"] == "Alice Smith"
    assert data["email"] == "alice@example.com"
    assert data["age"] == 28


def test_get_user_not_found():
    """Test retrieving non-existent user."""
    response = client.get("/users/99999")
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_create_user_age_exactly_18():
    """Test user creation with age exactly 18 (boundary test)."""
    user_data = {
        "name": "Boundary User",
        "email": "boundary@example.com",
        "age": 18
    }
    
    response = client.post("/users/", json=user_data)
    
    assert response.status_code == 201
    data = response.json()
    assert data["age"] == 18
