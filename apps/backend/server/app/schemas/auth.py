from uuid import UUID

from pydantic import EmailStr, Field, field_validator

from app.schemas.base import CamelModel


class LoginRequest(CamelModel):
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.casefold()


class RegisterRequest(LoginRequest):
    password: str = Field(min_length=15, max_length=128)


class UserResponse(CamelModel):
    id: UUID
    email: str
