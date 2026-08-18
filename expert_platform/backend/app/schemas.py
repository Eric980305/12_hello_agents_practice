from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


class Credentials(ApiModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=256)


class ExpertCreate(ApiModel):
    name: str = Field(min_length=1, max_length=80)


class ConfirmedDelete(ApiModel):
    confirmed: bool


class ChatRequest(ApiModel):
    expert_id: str = Field(alias="expertId", min_length=1, max_length=128)
    question: str = Field(min_length=1, max_length=4_000)
    advanced: bool = False


class AdminDeleteTarget(ApiModel):
    action: Literal["user", "expert", "document"]
    user_id: str = Field(alias="userId", min_length=1, max_length=128)
    expert_id: str | None = Field(default=None, alias="expertId", max_length=128)
    document_id: str | None = Field(default=None, alias="documentId", max_length=128)


class AdminDeleteExecute(AdminDeleteTarget):
    confirmation: str = Field(min_length=1, max_length=128)
