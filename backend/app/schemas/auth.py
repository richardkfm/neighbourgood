"""Pydantic schemas for authentication."""

import re
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, StringConstraints, field_validator


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    display_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    neighbourhood: str | None = Field(None, max_length=100)
    language_code: str = Field("en", max_length=10)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., max_length=128)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
