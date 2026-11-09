"""Pydantic models for Wallet Service."""
from pydantic import BaseModel


class TransferExecuteRequest(BaseModel):
    sender_wallet_id: int
    receiver_wallet_id: int
    amount: float
    transaction_id: int
    timestamp: str
