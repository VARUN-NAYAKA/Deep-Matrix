import time
import re
from rank_bm25 import BM25Okapi
import db_cache

def tokenize(text: str) -> list:
    """Cleans and tokenizes text into small word tokens."""
    text = text.lower()
    # Replace non-alphanumeric with spaces, split by whitespace
    words = re.findall(r'\b\w+\b', text)
    return words

def route_query(query: str, doc_id: str, default_top_k: int = 2) -> tuple:
    """
    Ranks page segments (child chunks) for the given document and query using BM25.
    Returns:
        tuple: (list of unique page numbers to retrieve, dict of routing metadata)
    """
    start_time = time.time()
    
    # 1. Fetch child chunks from SQLite cache
    child_chunks = db_cache.get_child_chunks(doc_id)
    if not child_chunks:
        return [], {
            "strategy": "fallback-all",
            "pages_matched": [],
            "scores": [],
            "latency_ms": round((time.time() - start_time) * 1000, 2),
            "status": "No cached document chunks found. Falling back to default."
        }
        
    # 2. Prepare corpus and tokenize
    corpus = []
    chunk_mapping = [] # Map index in corpus back to page number and segment text
    
    for chunk in child_chunks:
        segment_text = chunk["text_segment"]
        # Add keywords context if available to boost search matching
        if chunk.get("keywords"):
            segment_text += " " + chunk["keywords"].replace(",", " ")
            
        tokens = tokenize(segment_text)
        corpus.append(tokens)
        chunk_mapping.append({
            "page_number": chunk["page_number"],
            "text": chunk["text_segment"]
        })
        
    # 3. Compute BM25 scores
    bm25 = BM25Okapi(corpus)
    query_tokens = tokenize(query)
    scores = bm25.get_scores(query_tokens)
    
    # 4. Sort and retrieve top matches
    # Pair indices with scores
    indexed_scores = list(enumerate(scores))
    # Sort by score descending
    sorted_scores = sorted(indexed_scores, key=lambda x: x[1], reverse=True)
    
    # Select top matches
    matched_pages_with_scores = []
    seen_pages = set()
    
    for idx, score in sorted_scores:
        if score > 0.1:  # Check score threshold to ensure relevance
            page = chunk_mapping[idx]["page_number"]
            if page not in seen_pages:
                seen_pages.add(page)
                matched_pages_with_scores.append({
                    "page_number": page,
                    "score": round(float(score), 4)
                })
            # Limit page selection to target K pages
            if len(seen_pages) >= default_top_k:
                break
                
    # If no pages pass the relevance threshold, default to the top scoring pages anyway,
    # or fallback to pages 1 and 2 if all scores are zero
    if not matched_pages_with_scores:
        for idx, score in sorted_scores[:default_top_k]:
            page = chunk_mapping[idx]["page_number"]
            if page not in seen_pages:
                seen_pages.add(page)
                matched_pages_with_scores.append({
                    "page_number": page,
                    "score": round(float(score), 4)
                })
                
    page_numbers = [item["page_number"] for item in matched_pages_with_scores]
    # Sort matched pages numerically
    page_numbers.sort()
    
    latency_ms = round((time.time() - start_time) * 1000, 2)
    
    metadata = {
        "strategy": "BM25 Local Keyword Routing",
        "pages_matched": page_numbers,
        "scores": [item["score"] for item in matched_pages_with_scores],
        "latency_ms": latency_ms,
        "status": "Success"
    }
    
    return page_numbers, metadata
