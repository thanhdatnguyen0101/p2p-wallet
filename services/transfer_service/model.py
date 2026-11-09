"""Pydantic models for Transfer Service."""
from typing import Optional
from pydantic import BaseModel


class TransferRequest(BaseModel):
    sender_wallet_id: int
    receiver_wallet_id: int
    amount: float


class ConfirmRequest(BaseModel):
    code: Optional[str] = None
