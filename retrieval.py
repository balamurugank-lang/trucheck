"""
retrieval.py
Embeds an incoming question and pulls the closest matching chunks out of
the ChromaDB collection built by ingestion/embed_and_store.py.

Runs against a Chroma SERVER (not an embedded local file) - see
CHROMA_HOST/CHROMA_PORT below. Start the server separately with:
    chroma run --path ../chroma_store_server --port 8000
This must be running before the backend starts, or you'll get
"Could not connect to a Chroma server."
"""
import os
from dataclasses import dataclass
from typing import List

import chromadb
from openai import OpenAI

EMBEDDING_MODEL = "text-embedding-3-small"
CHROMA_HOST = os.environ.get("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.environ.get("CHROMA_PORT", "8000"))
COLLECTION_NAME = os.environ.get("CHROMA_COLLECTION", "trucheck_faq")
# Raised from 4 -> 6: gives the LLM more retrieved context to synthesize a
# fuller answer from (e.g. a status + its related stage/document entries),
# rather than being limited to whichever single chunk matched most closely.
TOP_K = 6

# Chroma's default distance metric here is cosine distance (0 = identical,
# higher = less similar). Calibrated against real test data (see
# ingestion/calibrate_threshold.py): genuinely relevant questions scored
# 0.469-0.819, genuinely irrelevant/off-topic questions scored 1.308-1.898 -
# a wide, clean gap. 1.05 sits safely in that gap. Re-run the calibration
# script periodically as more FAQ content is added, since the real-match
# range may shift with more/different topics in the knowledge base.
MAX_RELEVANT_DISTANCE = 1.05

_chroma_client = None
_collection = None
_openai_client = None


@dataclass
class RetrievedChunk:
    text: str
    section: str
    question: str
    distance: float


def _get_collection():
    global _chroma_client, _collection
    if _collection is None:
        _chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        _collection = _chroma_client.get_collection(COLLECTION_NAME)
    return _collection


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY environment variable is not set.")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


def retrieve(
    question: str, top_k: int = TOP_K, max_distance: float = MAX_RELEVANT_DISTANCE
) -> List[RetrievedChunk]:
    """Embed the question and return the top_k closest FAQ chunks, filtered to
    ones actually within max_distance. Can return an empty list if nothing
    retrieved is close enough - callers should treat that as "no relevant FAQ
    content found" rather than feeding weak matches to the LLM."""
    client = _get_openai_client()
    collection = _get_collection()

    embedding = client.embeddings.create(
        model=EMBEDDING_MODEL, input=[question]
    ).data[0].embedding

    results = collection.query(query_embeddings=[embedding], n_results=top_k)

    chunks = []
    for doc, meta, dist in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        if dist > max_distance:
            continue  # too far to be a genuine match - drop rather than pass along as noise
        chunks.append(
            RetrievedChunk(
                text=doc,
                section=meta.get("section", ""),
                question=meta.get("question", ""),
                distance=dist,
            )
        )
    return chunks