"""
main.py

Standalone FastAPI app for the TruCheck help chatbot backend.

Run standalone for testing:
    uvicorn main:app --reload --port 8001

Once verified, this can either run as its own small service, or the
`/api/chat` route below can be copied into a router and mounted inside
Trucheck's existing FastAPI app - the logic doesn't change either way.
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

load_dotenv()  # reads .env in this folder and sets OPENAI_API_KEY etc.

import os
from schemas import ChatRequest, ChatResponse
from chat_service import answer_question

app = FastAPI(title="TruCheck Help Chatbot")

# --- Rate limiting ---
# 20 requests/minute per client IP is a starting point for internal staff
# usage - generous enough for normal back-and-forth chat, tight enough to
# stop a runaway frontend bug or someone scripting abuse from quietly
# racking up OpenAI charges. Adjust based on real usage patterns once this
# is live.
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- CORS ---
# CHANGE THIS to your actual TruCheck portal origin(s) before deploying -
# e.g. "https://trucheck.vdart.internal". Reading from an env var so this
# isn't hardcoded and can differ between staging/prod without a code change.
# Falls back to localhost dev ports if unset, NOT to "*" - fail closed, not open.
_allowed_origins = os.environ.get(
    "ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
@limiter.limit("20/minute")
def chat(request: Request, chat_request: ChatRequest):
    try:
        answer, sources, suggested_questions = answer_question(
            chat_request.message, chat_request.history, caller_id="dev-local"
        )
    except RuntimeError as e:
        # e.g. missing OPENAI_API_KEY
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

    return ChatResponse(answer=answer, sources=sources, suggested_questions=suggested_questions)