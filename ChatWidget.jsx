import React, { useState, useRef, useEffect } from "react";
import { DotLottieReact } from "@lottiefiles/dotlottie-react";
import "./ChatWidget.css";

// Path to the .lottie file, served from /public - e.g. if the file is at
// public/animations/loading.lottie, this stays "/animations/loading.lottie".
const LOADING_ANIMATION_PATH = "/animations/loading.lottie";

// Point this at wherever the FastAPI backend actually runs. In dev it's the
// standalone server on :8001; in production this should be a relative path
// (e.g. "/api/chat") once the chatbot backend is deployed alongside Trucheck,
// or an absolute URL if it stays a separate service.
const CHAT_API_URL =
  import.meta.env.VITE_CHAT_API_URL || "http://127.0.0.1:8001/api/chat";

// Matches VDART_INTERNAL_API_TOKEN in the backend's .env - this is the
// placeholder shared-token auth, not real per-user auth. Set this in
// frontend/.env as VITE_CHAT_API_TOKEN=<same value as the backend>.
const CHAT_API_TOKEN = import.meta.env.VITE_CHAT_API_TOKEN || "";

const WELCOME_MESSAGE = {
  role: "assistant",
  content:
    "Hi, I'm the TruCheck help assistant. Ask me anything about TruCheck, statuses, required documents, or how to use the portal.",
};

// Matches http(s) URLs so plain-text answers containing a link (e.g. the
// TruCheck website, or a support/dispute page) render as an actual clickable
// link instead of a raw string. Backend intentionally returns plain text -
// this is purely a display-layer concern, not something to push onto the
// backend/prompt.
const URL_REGEX = /(https?:\/\/[^\s]+)/g;

function renderMessageContent(text) {
  const parts = text.split(URL_REGEX);
  return parts.map((part, i) => {
    // Strip common trailing punctuation (period, comma, closing paren) that
    // often follows a URL in a sentence, so the link doesn't swallow it.
    const isUrl = /^https?:\/\//.test(part);
    if (!isUrl) return <React.Fragment key={i}>{part}</React.Fragment>;

    const trailingPunctMatch = part.match(/[.,)]+$/);
    const trailing = trailingPunctMatch ? trailingPunctMatch[0] : "";
    const cleanUrl = trailing ? part.slice(0, -trailing.length) : part;

    return (
      <React.Fragment key={i}>
        <a
          href={cleanUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="tc-chat-link"
        >
          {cleanUrl}
        </a>
        {trailing}
      </React.Fragment>
    );
  });
}

function SendIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M3 12L21 3L14 21L11 13L3 12Z" fill="currentColor" />
    </svg>
  );
}

// Shield-check mark - reinforces the identity-verification subject matter
// rather than a generic bot/robot glyph.
function ShieldIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 3L4 6V11C4 16 7.5 19.5 12 21C16.5 19.5 20 16 20 11V6L12 3Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path
        d="M9 12L11.2 14.2L15.5 9.5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function AssistantAvatar() {
  return (
    <div className="tc-chat-avatar" aria-hidden="true">
      <ShieldIcon />
    </div>
  );
}

export default function ChatWidget() {
  const [messages, setMessages] = useState([WELCOME_MESSAGE]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [messages, isLoading]);

  // Full-page chat is always "open" - focus the input as soon as it mounts,
  // instead of waiting for a launcher click that no longer exists.
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.focus();
    }
  }, []);

  // Auto-grow the textarea as the user types, up to a capped height (see
  // max-height in CSS) rather than staying locked at a single row.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [input]);

  async function sendMessage(overrideText) {
    const trimmed = (overrideText ?? input).trim();
    if (!trimmed || isLoading) return;

    const userMessage = { role: "user", content: trimmed };
    // Only real prior turns count as "history" for the API - the welcome
    // message is UI-only and shouldn't be sent as if the assistant said it
    // unprompted.
    const historyForApi = messages
      .filter((m) => m !== WELCOME_MESSAGE)
      .map((m) => ({ role: m.role, content: m.content }));

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(CHAT_API_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${CHAT_API_TOKEN}`,
        },
        body: JSON.stringify({
          message: trimmed,
          history: historyForApi,
        }),
      });

      if (!response.ok) {
        throw new Error(`Request failed (${response.status})`);
      }

      const data = await response.json();
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.answer,
          suggestedQuestions: data.suggested_questions || [],
        },
      ]);
    } catch (err) {
      setError(
        "Couldn't reach the help assistant. Please try again, or contact VerifiedID support at support@verifiedid.co."
      );
    } finally {
      setIsLoading(false);
    }
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  return (
    <div className="tc-chat-page">
      <div className="tc-chat-page-panel" role="main" aria-label="TruCheck help chat">
        <div className="tc-chat-header">
          <div className="tc-chat-header-text">
            <div className="tc-chat-header-top">
              <img src="/trucheck.png" alt="TruCheck" className="tc-chat-header-logo" />
              <span className="tc-chat-header-title">TruCheck Help</span>
            </div>
            <span className="tc-chat-header-subtitle">
              <span className="tc-chat-status-dot" aria-hidden="true" />
              Answers grounded in the TruCheck FAQ
            </span>
          </div>
        </div>

        <div className="tc-chat-messages" ref={scrollRef}>
          <div className="tc-chat-messages-inner">
            {messages.map((m, i) => {
              const isLastMessage = i === messages.length - 1;
              const showSuggestions =
                m.role === "assistant" &&
                isLastMessage &&
                !isLoading &&
                m.suggestedQuestions &&
                m.suggestedQuestions.length > 0;

              return (
                <div
                  key={i}
                  className={`tc-chat-row ${m.role === "user" ? "tc-chat-row-user" : "tc-chat-row-assistant"}`}
                >
                  {m.role === "assistant" && <AssistantAvatar />}
                  <div className="tc-chat-bubble-col">
                    <div
                      className={
                        m.role === "user" ? "tc-chat-msg tc-chat-msg-user" : "tc-chat-msg tc-chat-msg-assistant"
                      }
                    >
                      {renderMessageContent(m.content)}
                    </div>

                    {showSuggestions && (
                      <div className="tc-chat-suggestions">
                        {m.suggestedQuestions.map((q, qi) => (
                          <button
                            key={qi}
                            type="button"
                            className="tc-chat-suggestion-chip"
                            onClick={() => sendMessage(q)}
                          >
                            {q}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {isLoading && (
              <div className="tc-chat-row tc-chat-row-assistant">
                <AssistantAvatar />
                <div className="tc-chat-msg tc-chat-msg-assistant tc-chat-loading">
                  <DotLottieReact src={LOADING_ANIMATION_PATH} loop autoplay style={{ width: 40, height: 24 }} />
                </div>
              </div>
            )}

            {error && (
              <div className="tc-chat-row tc-chat-row-assistant">
                <div className="tc-chat-error">{error}</div>
              </div>
            )}
          </div>
        </div>

        <div className="tc-chat-input-row">
          <div className="tc-chat-input-inner">
            <textarea
              ref={(el) => {
                inputRef.current = el;
                textareaRef.current = el;
              }}
              className="tc-chat-input"
              placeholder="Ask about TruCheck..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={1}
            />
            <button
              className="tc-chat-send-btn"
              onClick={sendMessage}
              disabled={!input.trim() || isLoading}
              aria-label="Send message"
            >
              <SendIcon />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}