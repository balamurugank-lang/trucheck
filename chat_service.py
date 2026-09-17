"""
chat_service.py
Ties retrieval + navigation map + conversation history together into a
single OpenAI chat completion call, grounded in the FAQ content. Asks the
model for structured JSON (answer + follow-up suggestions) rather than
plain text, so the widget can render clickable next-question chips.
"""
import json
import os
from typing import List

from openai import OpenAI

from retrieval import retrieve, RetrievedChunk
from nav_map import format_nav_map_for_prompt
from schemas import ChatTurn, SourceRef
from audit_log import log_interaction

CHAT_MODEL = "gpt-4o-mini"

SYSTEM_PROMPT_TEMPLATE = """You are the TruCheck help assistant, embedded in the Trucheck portal.

You help VDart recruiters and staff with two things:
1. Answering questions about TruCheck using ONLY the FAQ context provided below.
2. Guiding users to the right page/feature in the portal using the navigation map below.

Rules:
- If the user's message is a greeting, thanks, goodbye, or general small talk (not
  an actual question about TruCheck), respond naturally and briefly - a simple
  "Hi! How can I help with TruCheck today?" is fine. Don't apply the FAQ-only
  rule below to small talk, since it doesn't need grounding.
- For actual questions about TruCheck: answer only from the FAQ CONTEXT given
  below. If the context doesn't cover the question, say you don't have that
  information and suggest contacting VerifiedID support (support@verifiedid.co
  or 888-718-2597) or a lead - do not guess. NEVER state a fact, policy, document
  requirement, or dashboard behavior that isn't explicitly present in the
  context below, even if it seems like a reasonable inference.
- Never invent policy, document requirements, or dashboard behavior not stated
  in the context.
- This is internal-use content. Do not suggest forwarding FAQ content to
  candidates or clients.
- When a question is about navigation ("how do I...", "where is..."), use the
  NAVIGATION MAP to point to the exact page/button.

Answer quality:
- Give a complete, helpful answer - don't just restate the bare fact in one
  clipped sentence if the context has more to offer. Use everything relevant
  from the retrieved context below, not just the single closest-matching chunk.
- If multiple retrieved chunks are related (e.g. a status and its document
  requirement, or a stage and what happens after it), connect them into one
  coherent answer instead of answering as if only one chunk existed.
- If the context includes a reason, consequence, or "what happens if..." detail
  connected to the fact being asked about, include it - this is what makes an
  answer useful instead of a flat lookup. Only include such detail if it is
  explicitly present in the context; do not infer or extrapolate consequences
  that aren't stated.
- Still keep answers focused and skimmable for busy staff - complete does not
  mean padded. Avoid filler, avoid repeating the question back, avoid generic
  throat-clearing like "Great question!". Every sentence should carry
  information from the context.
- When you genuinely don't have enough context to give a fuller answer, it's
  fine to be brief - don't manufacture length. Brevity is correct when the
  context itself is brief; dryness is wrong when the context has more to give
  and you're not using it.
- When the answer contains a list of distinct items - multiple steps, multiple
  document types, multiple checks/things confirmed, multiple examples - put
  each one on its own line using "- " at the start, instead of running them
  together in one paragraph. This is purely a formatting choice for
  readability; it does not change what content you can include. A one or
  two-item answer with no real enumeration can stay as normal prose - only
  break into lines when there are genuinely 3+ distinct items a busy reader
  would want to scan individually rather than parse out of a sentence.
- Never use em dashes (—) or en dashes (–) anywhere in the answer text. Use a
  comma, a period starting a new sentence, or a colon instead of a dash to
  connect two clauses. A plain hyphen (-) is still fine for the list-line
  formatting above and for genuinely hyphenated words (e.g. "pre-adverse").
- Never use markdown formatting like **bold**, *italics*, or # headers
  anywhere in the answer. The chat widget displays plain text only - markdown
  symbols would show up as literal asterisks/hashes on screen, not actual
  formatting. If a word or step name needs emphasis, rely on plain wording and
  the "- " line-per-item structure above instead of bold/italic markup.

After answering, suggest 2-3 short follow-up questions the user might
realistically want to ask next. For an actual TruCheck question, base these on
related lookups (e.g. a different status's document requirements), the natural
next step in the workflow, or a common related concern - grounded only in
topics the FAQ context below can actually answer. For a greeting or small talk
with no prior FAQ topic in play, suggest 2-3 good example starter questions
instead (e.g. "What document does a green card holder need?"), so the user
has something concrete to click. Keep each suggestion under 12 words, phrased
the way a recruiter would actually type it.

Respond with ONLY a JSON object, no other text, in exactly this shape:
{{"answer": "...", "suggested_questions": ["...", "..."]}}
If there's truly nothing sensible to suggest, use an empty array.

NAVIGATION MAP:
{nav_map}

FAQ CONTEXT (most relevant entries for this question):
{context}
"""

# Shown to the model in place of real context when retrieval found nothing
# within the relevance threshold - this is a stronger, more explicit signal
# than just handing it an empty string, so it's not tempted to fill the gap
# from its own general knowledge.
NO_RELEVANT_CONTEXT_MARKER = (
    "(No FAQ entry was found that is closely related to this question. "
    "Do not guess or use outside knowledge - tell the user this isn't covered "
    "and point them to VerifiedID support.)"
)


def _build_context_block(chunks: List[RetrievedChunk]) -> str:
    if not chunks:
        return NO_RELEVANT_CONTEXT_MARKER
    blocks = []
    for c in chunks:
        blocks.append(f"[{c.section}]\n{c.text}")
    return "\n\n".join(blocks)


def _get_openai_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")
    return OpenAI(api_key=api_key)


REWRITE_MODEL = "gpt-4o-mini"

REWRITE_PROMPT = """Rewrite the LATEST user message below into a standalone
question that makes sense with no other context - resolving pronouns,
"it"/"that"/"they", and implied topics using the recent conversation.

Rules:
- Only rewrite if the latest message is actually ambiguous or context-dependent
  on its own. If it already stands alone fine, return it unchanged.
- Never add facts, assumptions, or details that aren't implied by the
  conversation itself - you are clarifying phrasing, not answering the question
  or introducing new information.
- Keep it short - one sentence, phrased naturally like a recruiter would type it.
- Output ONLY the rewritten question text, nothing else - no quotes, no preamble.

RECENT CONVERSATION (oldest to newest):
{recent_turns}

LATEST USER MESSAGE:
{message}
"""


def _rewrite_query_for_retrieval(message: str, history: List[ChatTurn]) -> str:
    """Uses the last 3 turns to resolve context-dependent follow-ups (e.g.
    "what if they still don't respond?") into a standalone question before
    embedding/retrieval - retrieval only ever sees the raw latest message
    otherwise, which can miss on vague follow-ups even though the LLM's final
    answer has the full history. Falls back to the original message untouched
    on any failure, so a rewrite hiccup never breaks the actual response."""
    if not history:
        return message  # nothing to resolve against on the first message

    recent = history[-3:]
    if not recent:
        return message

    recent_turns_text = "\n".join(f"{t.role}: {t.content}" for t in recent)

    try:
        client = _get_openai_client()
        response = client.chat.completions.create(
            model=REWRITE_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": REWRITE_PROMPT.format(
                        recent_turns=recent_turns_text, message=message
                    ),
                }
            ],
            temperature=0,
            max_tokens=80,
        )
        rewritten = response.choices[0].message.content.strip()
        return rewritten if rewritten else message
    except Exception:
        # Any failure (network, API, malformed response) - just use the
        # original message. Degrades to today's exact behavior, never breaks.
        return message


def answer_question(
    message: str, history: List[ChatTurn], caller_id: str = "unknown"
) -> tuple[str, List[SourceRef], List[str]]:
    """Retrieve relevant FAQ chunks, call the LLM, and return
    (answer, sources, suggested_questions). caller_id is only used for the
    audit log, not for retrieval/generation."""
    # Rewrite only feeds retrieval - the LLM generation call below still uses
    # the user's original wording in `messages`/history/logging, so the
    # conversation itself is never altered, only what we search FAQ chunks with.
    retrieval_query = _rewrite_query_for_retrieval(message, history)
    chunks = retrieve(retrieval_query)

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        nav_map=format_nav_map_for_prompt(),
        context=_build_context_block(chunks),
    )

    messages = [{"role": "system", "content": system_prompt}]
    for turn in history[-10:]:  # cap history length defensively even if the widget doesn't
        messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": message})

    client = _get_openai_client()
    response = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        # 0.4 - up from 0.2. Still low enough to stay grounded and consistent,
        # but gives the model room to phrase fuller answers naturally instead
        # of defaulting to the flattest, most clipped possible sentence.
        temperature=0.4,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content

    try:
        parsed = json.loads(raw)
        answer = parsed.get("answer", "").strip()
        suggested_questions = [
            q.strip() for q in parsed.get("suggested_questions", []) if q.strip()
        ][:3]
        if not answer:
            raise ValueError("empty answer field")
    except (json.JSONDecodeError, ValueError, AttributeError):
        # Model didn't return valid JSON for some reason - fall back to
        # showing the raw text as the answer rather than failing the request.
        answer = raw
        suggested_questions = []

    # Belt-and-suspenders: the prompt already tells the model not to use em/en
    # dashes or markdown, but catch any that slip through anyway rather than
    # relying on the prompt alone.
    answer = answer.replace(" — ", ", ").replace(" – ", ", ").replace("—", ",").replace("–", ",")
    answer = answer.replace("**", "").replace("__", "")

    sources = [SourceRef(section=c.section, question=c.question) for c in chunks]

    # Best-effort audit logging - never let a logging failure break the
    # actual chat response the user is waiting on.
    try:
        log_interaction(
            caller_id=caller_id,
            question=message,
            answer=answer,
            sources=[{"section": s.section, "question": s.question} for s in sources],
            suggested_questions=suggested_questions,
        )
    except Exception:
        pass

    return answer, sources, suggested_questions