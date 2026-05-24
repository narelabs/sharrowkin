from typing import Dict
from fastapi import APIRouter, HTTPException, status
from pydantic import ValidationError
from api.models.user import User

router = APIRouter(prefix="/users", tags=["users"])

# In-memory storage for demo purposes
users_db: Dict[int, User] = {}
next_id = 1


@router.post("/", response_model=User, status_code=status.HTTP_201_CREATED)
async def create_user(user: User) -> User:
    """Create a new user.
    
    Args:
        user: User data with name, email, and age
        
    Returns:
        Created user with assigned ID
        
    Raises:
        HTTPException: If validation fails (invalid email or age < 18)
    """
    global next_id
    
    # Assign ID
    user.id = next_id
    next_id += 1
    
    # Store user
    users_db[user.id] = user
    
    return user


@router.get("/{user_id}", response_model=User)
async def get_user(user_id: int) -> User:
    """Get a user by ID.
    
    Args:
        user_id: The ID of the user to retrieve
        
    Returns:
        User data
        
    Raises:
        HTTPException: If user not found
    """
    if user_id not in users_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {user_id} not found"
        )
    
    return users_db[user_id]
