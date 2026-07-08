from datetime import datetime
from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CreateUserRequest(BaseModel):
    username: str
    display_name: str


class CreateUserResponse(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    password: str  # returned once
