from pydantic import BaseModel, Field


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class ExpertCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)


class ChatRequest(BaseModel):
    expert_id: str
    question: str = Field(min_length=1, max_length=4000)
    advanced: bool = False


class NoteCreate(BaseModel):
    expert_id: str
    content: str = Field(min_length=1, max_length=10000)
