"""Quick test of the created API without pytest."""

from fastapi.testclient import TestClient
from fastapi import FastAPI
from api.routes.users import router

# Create test app
app = FastAPI()
app.include_router(router)
client = TestClient(app)

print("=" * 60)
print("TESTING CREATED API")
print("=" * 60)

# Test 1: Create valid user
print("\n1. Creating valid user (age=25)...")
response = client.post("/users/", json={
    "name": "John Doe",
    "email": "john@example.com",
    "age": 25
})
print(f"   Status: {response.status_code}")
print(f"   Response: {response.json()}")
assert response.status_code == 201, "Should create user"
user_id = response.json()["id"]

# Test 2: Get user
print(f"\n2. Getting user {user_id}...")
response = client.get(f"/users/{user_id}")
print(f"   Status: {response.status_code}")
print(f"   Response: {response.json()}")
assert response.status_code == 200, "Should get user"

# Test 3: Invalid email
print("\n3. Creating user with invalid email...")
response = client.post("/users/", json={
    "name": "Jane Doe",
    "email": "invalid-email",
    "age": 30
})
print(f"   Status: {response.status_code}")
print(f"   Response: {response.json()}")
assert response.status_code == 422, "Should reject invalid email"

# Test 4: Age under 18
print("\n4. Creating user with age=17...")
response = client.post("/users/", json={
    "name": "Young User",
    "email": "young@example.com",
    "age": 17
})
print(f"   Status: {response.status_code}")
print(f"   Response: {response.json()}")
assert response.status_code == 422, "Should reject age < 18"

# Test 5: Age exactly 18
print("\n5. Creating user with age=18 (boundary)...")
response = client.post("/users/", json={
    "name": "Boundary User",
    "email": "boundary@example.com",
    "age": 18
})
print(f"   Status: {response.status_code}")
print(f"   Response: {response.json()}")
assert response.status_code == 201, "Should accept age = 18"

# Test 6: User not found
print("\n6. Getting non-existent user...")
response = client.get("/users/99999")
print(f"   Status: {response.status_code}")
print(f"   Response: {response.json()}")
assert response.status_code == 404, "Should return 404"

print("\n" + "=" * 60)
print("ALL TESTS PASSED!")
print("=" * 60)
