"""Pydantic models for User Service."""
from typing import Optional
from pydantic import BaseModel


class RegisterRequest(BaseModel):
    username: str = ""
    email: str = ""
    password: str = ""


class LoginRequest(BaseModel):
    username: str = ""
    password: str = ""


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    email: str
    otp_code: str
    new_password: str


class AdminCreateUserRequest(BaseModel):
    username: str = ""
    email: str = ""
    password: str = ""
    initial_balance: float = 1000000


class AdminUpdateUserRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
