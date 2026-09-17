"""
schemas.py
Request/response shapes for the /api/chat endpoint.
"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="The user's question")
    history: List[ChatTurn] = Field(
        default_factory=list,
        description="Prior turns in this conversation, oldest first. Keep this "
        "short (last ~6-10 turns) - the widget is responsible for trimming it.",
    )


class SourceRef(BaseModel):
    section: str
    question: str


class ChatResponse(BaseModel):
    answer: str
    sources: List[SourceRef] = Field(
        default_factory=list,
        description="Which FAQ entries the answer was grounded in, for transparency/debugging.",
    )
    suggested_questions: List[str] = Field(
        default_factory=list,
        description="2-3 relevant follow-up questions the user might want to ask next.",
    )