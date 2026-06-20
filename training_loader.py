"""
training_loader.py
==================
Loads and indexes the ground-truth QA training dataset (training_data.json).

Provides:
  - Few-shot example injection (top-k similar examples by kind/keyword match)
  - Evidence page boosting hints for the BM25 routing engine
  - Unanswerable question detection (fast keyword match)
"""

import os
import json
import re
from difflib import SequenceMatcher

# ── Path to the training dataset ──────────────────────────────────────────────
_TRAINING_FILE = os.path.join(os.path.dirname(__file__), "training_data.json")

# ── Global in-memory index (loaded once) ──────────────────────────────────────
_QA_INDEX: list = []
_LOADED: bool = False

# Doc-type keyword map (matches natural language → doc_type)
DOC_TYPE_KEYWORDS = {
    "bank_stmt_checking": ["bank statement", "checking", "deposit", "withdrawal", "balance", "ledger"],
    "w2": ["w-2", "w2", "wage", "box 1", "wages"],
    "form_1040": ["1040", "tax return", "form 1040"],
    "form_1008": ["1008", "form 1008", "transmittal"],
    "closing_disclosure": ["closing disclosure", "cd", "settlement statement"],
    "loan_estimate": ["loan estimate", "le"],
    "credit_report": ["credit report", "credit score", "tradeline", "utilization", "fico"],
    "paystub": ["paystub", "pay stub", "ytd", "year-to-date", "gross pay", "earnings"],
    "loan_summary": ["loan summary", "piti", "dti", "debt-to-income", "principal & interest"],
    "brokerage_stmt": ["brokerage", "portfolio", "shares", "holdings", "etf", "asset allocation"],
    "urla_1003": ["urla", "1003", "uniform residential loan"],
}

# Question-type keywords
KIND_KEYWORDS = {
    "multi_hop":       ["across", "reconcile", "confirm", "identical", "both", "compare", "match", "tie"],
    "plot_reading":    ["chart", "graph", "plot", "trend", "peak", "highest", "lowest", "balance chart"],
    "aggregation":     ["sum", "total", "combined", "aggregate", "add", "all statements", "grand total"],
    "comparison":      ["which", "most", "highest", "largest", "most transactions", "highest balance"],
    "lookup":          ["what is", "what are", "what was", "report", "shows", "listed"],
    "counting":        ["how many", "count", "number of"],
    "pagination":      ["page", "which page", "start", "begin", "page number"],
    "unanswerable":    ["not in file", "not present", "missing", "unavailable"],
    "multi_hop_graph": ["chart", "table", "then", "look up", "identify", "find the account"],
    "duplicate":       ["most recent", "latest", "newest", "oldest"],
    "structure":       ["span", "longest", "how many pages", "page span"],
}


def _load() -> None:
    """Load training_data.json into memory (called lazily)."""
    global _QA_INDEX, _LOADED
    if _LOADED:
        return
    try:
        with open(_TRAINING_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _QA_INDEX = data.get("qa", [])
        _LOADED = True
        print(f"[TrainingLoader] Loaded {len(_QA_INDEX)} training QA pairs from {_TRAINING_FILE}")
    except FileNotFoundError:
        print(f"[TrainingLoader] WARNING: training_data.json not found at {_TRAINING_FILE}")
        _QA_INDEX = []
        _LOADED = True
    except Exception as e:
        print(f"[TrainingLoader] ERROR loading training data: {e}")
        _QA_INDEX = []
        _LOADED = True


def _text_similarity(a: str, b: str) -> float:
    """Simple character-level similarity ratio."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _detect_kind(query: str) -> str:
    """Detect question kind from query text using keyword matching."""
    q = query.lower()
    best_kind = "lookup"
    best_count = 0
    for kind, keywords in KIND_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in q)
        if count > best_count:
            best_count = count
            best_kind = kind
    return best_kind


def _detect_doc_types(query: str) -> list:
    """Detect which doc types are likely referenced in the query."""
    q = query.lower()
    matched = []
    for doc_type, keywords in DOC_TYPE_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            matched.append(doc_type)
    return matched


def get_few_shot_examples(query: str, max_examples: int = 3) -> list:
    """
    Returns up to `max_examples` training QA pairs most similar to `query`.
    Similarity is scored by:
      - Question kind match (+2)
      - Doc-type overlap (+1 per matching doc type)
      - Text similarity score
    Returns a list of dicts with keys: question, answer, kind, answer_type.
    """
    _load()
    if not _QA_INDEX:
        return []

    q = query.lower()
    detected_kind = _detect_kind(q)
    detected_doc_types = set(_detect_doc_types(q))

    scored = []
    for qa in _QA_INDEX:
        score = 0.0

        # Kind match bonus
        if qa.get("kind") == detected_kind:
            score += 2.0

        # Doc-type overlap bonus
        evidence_types = set(e.get("doc_type", "") for e in qa.get("evidence", []))
        overlap = len(detected_doc_types & evidence_types)
        score += overlap * 1.0

        # Text similarity with question and rephrased question
        q_sim = _text_similarity(query, qa.get("question", ""))
        qr_sim = _text_similarity(query, qa.get("question_rephrased", ""))
        score += max(q_sim, qr_sim) * 3.0

        # Prefer answerable examples for answerable queries
        if qa.get("answerable", True):
            score += 0.5

        scored.append((score, qa))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Avoid leaking exact-match answers (filter near-identical questions)
    results = []
    for score, qa in scored:
        if _text_similarity(query, qa.get("question", "")) > 0.95:
            continue  # Skip near-identical (would leak the answer)
        results.append({
            "question": qa.get("question_rephrased") or qa.get("question"),
            "answer": qa.get("answer"),
            "kind": qa.get("kind"),
            "answer_type": qa.get("answer_type"),
            "reasoning_hint": _build_reasoning_hint(qa)
        })
        if len(results) >= max_examples:
            break

    return results


def _build_reasoning_hint(qa: dict) -> str:
    """Generate a concise reasoning hint from evidence metadata."""
    evidence = qa.get("evidence", [])
    if not evidence:
        return "This question has no locatable evidence in the document."

    doc_types = list(set(e.get("doc_type", "unknown") for e in evidence if e.get("doc_type")))
    pages = sorted(set(e["page_index"] + 1 for e in evidence if "page_index" in e))

    hint = f"Evidence found in {', '.join(doc_types)}"
    if pages:
        if len(pages) <= 5:
            hint += f" on page(s) {', '.join(map(str, pages))}"
        else:
            hint += f" across {len(pages)} pages"

    kind = qa.get("kind", "")
    if kind == "multi_hop":
        hint += ". Requires cross-referencing multiple documents."
    elif kind == "aggregation":
        hint += ". Requires summing values across multiple pages."
    elif kind == "plot_reading":
        hint += ". Value extracted from a chart/graph visual element."
    elif kind == "multi_hop_graph":
        hint += ". Requires reading a chart first, then looking up in a table."
    elif kind == "unanswerable":
        hint = "This information is NOT present in the document file."

    return hint


def get_evidence_pages(query: str, top_n: int = 5) -> list:
    """
    Returns a list of 1-based page numbers from training examples that are
    most similar to the query. Used to BOOST BM25 routing scores.
    Returns empty list if no strong match found.
    """
    _load()
    if not _QA_INDEX:
        return []

    best_score = 0.0
    best_qa = None

    for qa in _QA_INDEX:
        q_sim = _text_similarity(query, qa.get("question", ""))
        qr_sim = _text_similarity(query, qa.get("question_rephrased", ""))
        sim = max(q_sim, qr_sim)
        if sim > best_score:
            best_score = sim
            best_qa = qa

    # Only use hint if similarity is high enough (>0.55)
    if best_score < 0.55 or best_qa is None:
        return []

    evidence = best_qa.get("evidence", [])
    pages = sorted(set(e["page_index"] + 1 for e in evidence if "page_index" in e))
    return pages[:top_n]


def is_likely_unanswerable(query: str) -> bool:
    """
    Quick check: if query is semantically close to a known unanswerable
    training question, flag it early to help the LLM respond correctly.
    """
    _load()
    q = query.lower()

    # Keyword fast-path
    unanswerable_triggers = [
        "flood insurance", "pension", "vesting", "appraiser license",
        "prior sale price", "original purchase", "hoa fee", "mello-roos"
    ]
    if any(t in q for t in unanswerable_triggers):
        return True

    # Similarity match against known unanswerable questions
    for qa in _QA_INDEX:
        if not qa.get("answerable", True):
            sim = max(
                _text_similarity(query, qa.get("question", "")),
                _text_similarity(query, qa.get("question_rephrased", ""))
            )
            if sim > 0.7:
                return True

    return False


def get_training_stats() -> dict:
    """Returns a summary of the loaded training dataset."""
    _load()
    if not _QA_INDEX:
        return {"total": 0, "by_kind": {}, "answerable": 0, "unanswerable": 0}

    by_kind = {}
    answerable = 0
    unanswerable = 0
    for qa in _QA_INDEX:
        kind = qa.get("kind", "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1
        if qa.get("answerable", True):
            answerable += 1
        else:
            unanswerable += 1

    return {
        "total": len(_QA_INDEX),
        "by_kind": by_kind,
        "answerable": answerable,
        "unanswerable": unanswerable
    }
