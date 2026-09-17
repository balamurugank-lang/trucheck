# TruCheck Portal Chatbot — Ingestion Pipeline

## What's here
- `ingestion/extract.py` — pulls text out of Word (.docx) or PDF FAQ docs
- `ingestion/chunk.py` — splits extracted text into Q&A chunks, section-tagged.
  Handles tables specially (pdfplumber often jumbles wrapped table cells when
  flattening to plain text — this rebuilds them as clean per-row Q&A pairs
  instead of dropping or mangling them).
- `ingestion/embed_and_store.py` — embeds chunks with OpenAI's
  `text-embedding-3-small` and stores them in a local ChromaDB collection.
  **Needs network access to api.openai.com and your `OPENAI_API_KEY`.**
- `ingestion/query_test.py` — quick CLI to test retrieval once the collection
  is built.
- `data/TruCheck_Internal_FAQ.pdf` — the FAQ doc used to build and test this
  pipeline. Drop any additional .pdf/.docx FAQ docs into this folder too.

## Tested against your actual FAQ doc
Ran extraction + chunking end-to-end against `TruCheck_Internal_FAQ.pdf`:
36 clean Q&A chunks, including two tables (dashboard stages, and
required-documents-by-status) that pdfplumber would otherwise have jumbled —
those are now split into individual per-row chunks so a question like
"what document does a green card holder need" retrieves precisely that row,
not the whole garbled table.

The embedding + ChromaDB step (`embed_and_store.py`) is written and ready but
**not yet run** — it needs your OpenAI API key and network access to
api.openai.com, neither of which this environment has. Run it on your own
machine/server.

## Setup

```bash
cd ingestion
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...
```

## Run

```bash
# 1. Build the knowledge base (embeds + stores in ./chroma_store)
python embed_and_store.py --docs-dir ../data --collection trucheck_faq

# 2. Sanity-check retrieval
python query_test.py "What document does a green card holder need?"
python query_test.py "What does Review Required mean?"
python query_test.py "Can I tell a candidate this is a client requirement?"
```

If `query_test.py` returns the right chunk as the top match for each of
those, the knowledge base is good and we move on to the FastAPI
`/api/chat` endpoint next.

## Re-running after doc updates
`embed_and_store.py` does a full rebuild each time (drops and recreates the
collection) — simplest correct behavior at this doc volume. Just re-run it
whenever a FAQ doc is added or edited in `data/`.
