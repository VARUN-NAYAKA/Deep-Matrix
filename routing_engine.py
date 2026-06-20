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

def check_for_category_fallback(query: str, doc_id: str) -> tuple:
    """
    Checks if the query is an aggregate/compare query over a specific doc category.
    Returns:
        tuple: (list of page numbers, matched_category_name or None)
    """
    query_lower = query.lower()
    
    # 1. Keywords indicating aggregate/cross-page queries
    aggregate_indicators = [
        "all", "compare", "summary", "total", "trends", "across", "correlation", 
        "reconcile", "list of", "every", "each", "history", "aggregate", "full",
        "deposits", "wages", "income", "withdrawals"
    ]
    
    is_aggregate = any(indicator in query_lower for indicator in aggregate_indicators)
    if not is_aggregate:
        return [], None
        
    # 2. Document category keyword triggers
    category_triggers = {
        "Bank Statement": ["bank", "statement", "checking", "deposit", "withdrawal", "balance", "ledger", "chase"],
        "W-2": ["w2", "w-2", "wage", "tax statement"],
        "Form 1040 (Tax Return)": ["1040", "tax return", "schedule", "1040s"],
        "Paystub": ["paystub", "pay stub", "paystubs", "earnings statement", "stub"],
        "Closing Disclosure": ["closing", "disclosure", "cd", "settlement"]
    }
    
    matched_category = None
    for category, triggers in category_triggers.items():
        if any(trigger in query_lower for trigger in triggers):
            matched_category = category
            break
            
    if not matched_category:
        return [], None
        
    # 3. Retrieve all page numbers for this category from database
    conn = db_cache.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT page_number 
        FROM parent_chunks 
        WHERE doc_id = ? AND doc_classification = ?
        ORDER BY page_number ASC
    """, (doc_id, matched_category))
    rows = cursor.fetchall()
    conn.close()
    
    page_numbers = [row["page_number"] for row in rows]
    return page_numbers, matched_category

def route_query(query: str, doc_id: str, default_top_k: int = 2) -> tuple:
    """
    Ranks page segments (child chunks) for the given document and query using BM25.
    If an aggregate query is detected, falls back to retrieving all pages under that category.
    Returns:
        tuple: (list of unique page numbers to retrieve, dict of routing metadata)
    """
    start_time = time.time()
    
    # 1. Check for Category Aggregate Fallback first
    fallback_pages, matched_category = check_for_category_fallback(query, doc_id)
    if fallback_pages:
        latency_ms = round((time.time() - start_time) * 1000, 2)
        metadata = {
            "strategy": f"Category Aggregate Fallback ({matched_category})",
            "pages_matched": fallback_pages,
            "scores": [1.0] * len(fallback_pages),
            "latency_ms": latency_ms,
            "status": f"Detected aggregate query for category: {matched_category}. Retrieved all corresponding pages."
        }
        return fallback_pages, metadata
    
    # 2. Fetch child chunks from SQLite cache
    child_chunks = db_cache.get_child_chunks(doc_id)
    if not child_chunks:
        return [], {
            "strategy": "fallback-all",
            "pages_matched": [],
            "scores": [],
            "latency_ms": round((time.time() - start_time) * 1000, 2),
            "status": "No cached document chunks found. Falling back to default."
        }
        
    # 3. Prepare corpus and tokenize
    corpus = []
    chunk_mapping = [] # Map index in corpus back to page number and segment text
    
    for chunk in child_chunks:
        segment_text = chunk["text_segment"]
        if chunk.get("keywords"):
            segment_text += " " + chunk["keywords"].replace(",", " ")
            
        tokens = tokenize(segment_text)
        corpus.append(tokens)
        chunk_mapping.append({
            "page_number": chunk["page_number"],
            "text": chunk["text_segment"]
        })
        
    # 4. Compute BM25 scores
    bm25 = BM25Okapi(corpus)
    query_tokens = tokenize(query)
    scores = bm25.get_scores(query_tokens)
    
    # 5. Sort and retrieve top matches
    indexed_scores = list(enumerate(scores))
    sorted_scores = sorted(indexed_scores, key=lambda x: x[1], reverse=True)
    
    matched_pages_with_scores = []
    seen_pages = set()
    
    for idx, score in sorted_scores:
        if score > 0.1:
            page = chunk_mapping[idx]["page_number"]
            if page not in seen_pages:
                seen_pages.add(page)
                matched_pages_with_scores.append({
                    "page_number": page,
                    "score": round(float(score), 4)
                })
            if len(seen_pages) >= default_top_k:
                break
                
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
