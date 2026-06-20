import re
import pypdf

# Document type visual metadata for the UI
DOC_TYPE_META = {
    "Bank Statement":           {"icon": "fa-building-columns", "color": "#3b82f6", "gradient": "linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)"},
    "W-2":                      {"icon": "fa-file-invoice-dollar", "color": "#f59e0b", "gradient": "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)"},
    "Closing Disclosure":       {"icon": "fa-file-signature", "color": "#10b981", "gradient": "linear-gradient(135deg, #10b981 0%, #059669 100%)"},
    "Form 1040 (Tax Return)":   {"icon": "fa-landmark", "color": "#8b5cf6", "gradient": "linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)"},
    "Paystub":                  {"icon": "fa-money-check-dollar", "color": "#ec4899", "gradient": "linear-gradient(135deg, #ec4899 0%, #db2777 100%)"},
    "Loan Estimate":            {"icon": "fa-calculator", "color": "#06b6d4", "gradient": "linear-gradient(135deg, #06b6d4 0%, #0891b2 100%)"},
    "Unknown":                  {"icon": "fa-file-circle-question", "color": "#6b7280", "gradient": "linear-gradient(135deg, #6b7280 0%, #4b5563 100%)"},
}

def extract_and_classify_pdf(pdf_path: str):
    """
    Extracts text page-by-page from the given PDF path and groups pages
    into logical document boundaries (logical pagination).
    Returns enriched data with doc-type visual metadata.
    """
    reader = pypdf.PdfReader(pdf_path)
    pages = []
    
    # First pass: Extract text and find keywords per page
    for idx, page in enumerate(reader.pages):
        page_num = idx + 1
        text = page.extract_text() or ""
        
        # Clean up text a bit for search
        normalized_text = " ".join(text.split()).lower()
        pages.append({
            "page_number": page_num,
            "text": text,
            "normalized_text": normalized_text
        })
        
    # Second pass: Heuristic-based logical pagination
    documents = []
    current_doc = None
    
    for page in pages:
        text = page["normalized_text"]
        page_num = page["page_number"]
        
        # Heuristics for document type matching
        doc_type = "Unknown"
        metadata = {}
        confidence = 0.5  # base confidence for unknown
        
        if "closing disclosure" in text:
            doc_type = "Closing Disclosure"
            confidence = 0.95
        elif "form 1040" in text or "u.s. individual income tax return" in text:
            doc_type = "Form 1040 (Tax Return)"
            confidence = 0.92
            # Try to extract Tax Year
            year_match = re.search(r"\b(202[0-9]|201[0-9])\b", text)
            if year_match:
                metadata["tax_year"] = year_match.group(1)
        elif "w-2" in text or "wage and tax statement" in text:
            doc_type = "W-2"
            confidence = 0.93
            year_match = re.search(r"\b(202[0-9]|201[0-9])\b", text)
            if year_match:
                metadata["tax_year"] = year_match.group(1)
        elif "pay stub" in text or "paystub" in text or "earnings statement" in text:
            doc_type = "Paystub"
            confidence = 0.88
        elif "bank statement" in text or "checking account" in text or "statement of account" in text:
            doc_type = "Bank Statement"
            confidence = 0.90
            # Try to identify bank name
            for bank in ["chase", "bank of america", "wells fargo", "citi", "capital one"]:
                if bank in text:
                    metadata["bank_name"] = bank.title()
                    confidence = 0.94
                    break
        elif "loan estimate" in text:
            doc_type = "Loan Estimate"
            confidence = 0.91
            
        # Detect new document start or continuation
        is_new_doc = False
        
        if current_doc is None:
            is_new_doc = True
        elif doc_type != "Unknown":
            if doc_type != current_doc["doc_type"]:
                is_new_doc = True
            elif doc_type in ["W-2", "Form 1040 (Tax Return)"] and "tax_year" in metadata:
                if metadata.get("tax_year") != current_doc["metadata"].get("tax_year"):
                    is_new_doc = True
            elif doc_type == "Bank Statement" and "bank_name" in metadata:
                if metadata.get("bank_name") != current_doc["metadata"].get("bank_name"):
                    is_new_doc = True
                    
        if is_new_doc:
            if current_doc:
                documents.append(current_doc)
            
            # Get visual metadata for this doc type
            visual = DOC_TYPE_META.get(doc_type, DOC_TYPE_META["Unknown"])
            
            current_doc = {
                "id": f"doc_{len(documents) + 1}",
                "doc_type": doc_type,
                "start_page": page_num,
                "end_page": page_num,
                "pages": [page_num],
                "metadata": metadata,
                "confidence": confidence,
                "icon": visual["icon"],
                "color": visual["color"],
                "gradient": visual["gradient"],
            }
        else:
            current_doc["end_page"] = page_num
            current_doc["pages"].append(page_num)
            # Propagate metadata if found in later pages
            current_doc["metadata"].update(metadata)
            
    if current_doc:
        documents.append(current_doc)
        
    return {
        "pages": pages,
        "documents": documents
    }


def enrich_mock_documents(documents: list) -> list:
    """
    Adds visual metadata (icon, color, gradient) to mock document entries
    that don't already have them.
    """
    enriched = []
    for doc in documents:
        if "icon" not in doc:
            visual = DOC_TYPE_META.get(doc["doc_type"], DOC_TYPE_META["Unknown"])
            doc["icon"] = visual["icon"]
            doc["color"] = visual["color"]
            doc["gradient"] = visual["gradient"]
            doc["confidence"] = 0.95  # mock data is high confidence
        enriched.append(doc)
    return enriched


def split_page_into_child_chunks(page_num: int, text: str) -> list:
    """
    Splits page text into smaller child chunks (~100 tokens / 350 chars each) for indexing.
    Returns list of dicts: {"page_number": int, "text_segment": str, "keywords": str}
    """
    # Simple sentence splitter using punctuation boundaries
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current_chunk = []
    current_length = 0
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        current_chunk.append(sentence)
        current_length += len(sentence)
        
        # When chunk size is roughly 300-350 characters, save it
        if current_length >= 350:
            segment_text = " ".join(current_chunk)
            chunks.append({
                "page_number": page_num,
                "text_segment": segment_text,
                "keywords": _extract_simple_keywords(segment_text)
            })
            current_chunk = []
            current_length = 0
            
    if current_chunk:
        segment_text = " ".join(current_chunk)
        chunks.append({
            "page_number": page_num,
            "text_segment": segment_text,
            "keywords": _extract_simple_keywords(segment_text)
        })
        
    # If the page was empty or had no chunks, return a default single chunk
    if not chunks:
        chunks.append({
            "page_number": page_num,
            "text_segment": text or f"[Page {page_num} Empty Content]",
            "keywords": ""
        })
        
    return chunks


def _extract_simple_keywords(text: str) -> str:
    """Extracts high-value terms (capitalized words, numbers, and key symbols) as keywords."""
    # Find all numbers, dates, capitalized words, or financial figures
    items = re.findall(r'\b(?:[A-Z][a-zA-Z0-9]+|\$[0-9,]+(?:\.[0-9]+)?|[0-9]{4})\b', text)
    # Filter unique items and join as a comma-separated string
    unique_items = list(set(items))
    return ",".join(unique_items)
