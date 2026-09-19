from datetime import datetime
from typing import Any

from sqlmodel import Field, SQLModel


class CaseCreate(SQLModel):
    funding_need_id: str
    company_org_id: str
    objective: str
    amount: float = Field(gt=0)
    term_months: int = Field(gt=0, le=120)
    product_types: list[str]


class AuthorizationCreate(SQLModel):
    scope: dict[str, Any]
    expires_at: datetime


class CapabilityUpsert(SQLModel):
    product_type: str
    eligibility: dict[str, Any] = Field(default_factory=dict)
    terms: dict[str, Any] = Field(default_factory=dict)
    active: bool = True


class OfferCreate(SQLModel):
    amount: float = Field(gt=0)
    annual_rate: float = Field(ge=0, le=1)
    term_months: int = Field(gt=0, le=120)
    opening_fee: float = Field(ge=0, le=1)
    guarantee: str
    terms: dict[str, Any] = Field(default_factory=dict)
    valid_until: datetime


class ShortlistCreate(SQLModel):
    provider_org_ids: list[str]
    scope: dict[str, Any]
    expires_at: datetime


class AcceptOffer(SQLModel):
    offer_id: str


class CloseCase(SQLModel):
    reason: str = Field(min_length=2, max_length=240)
