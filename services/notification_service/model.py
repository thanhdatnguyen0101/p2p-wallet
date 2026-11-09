"""Pydantic models for Notification Service."""
from typing import Optional
from pydantic import BaseModel


class OtpGenerateRequest(BaseModel):
    transaction_id: Optional[int] = None
    recipient_email: Optional[str] = None
    purpose: Optional[str] = "TRANSACTION"


class OtpVerifyRequest(BaseModel):
    transaction_id: Optional[int] = None
    code: Optional[str] = None


class OtpVerifyForgotRequest(BaseModel):
    email: str
    code: str
