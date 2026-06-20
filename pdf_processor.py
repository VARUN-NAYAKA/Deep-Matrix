import re
import os
import io
import time
import json
import base64
import pypdf
import google.generativeai as genai

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

# Threshold: if extracted text is shorter than this, the page is treated as scanned/image
SCANNED_PAGE_TEXT_THRESHOLD = 50


def extract_and_classify_pdf(pdf_path: str, api_key: str = None) -> dict:
    """
    Hybrid Multimodal Ingestion Pipeline (Option C):
    
    Pass 1 (Local): Extract text from all pages using pypdf (instant, free).
    Pass 2 (Vision): For pages where text is empty/too short (scanned/image pages),
                     render the page to a PNG via PyMuPDF and send it as inline
                     base64 image data to Gemini for OCR + classification.
    
    This bypasses the Gemini File API entirely, using inline image parts instead.
    """
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    
    # ==========================================
    # PASS 1: Local text extraction with PyPDF
    # ==========================================
    print(f"[PASS 1] Extracting text from {os.path.basename(pdf_path)} using pypdf...")
    reader = pypdf.PdfReader(pdf_path)
    total_pages = len(reader.pages)
    
    native_pages = []   # Pages with good text (native digital)
    scanned_page_nums = []  # Page numbers that need OCR
    
    for idx, page in enumerate(reader.pages):
        page_num = idx + 1
        text = page.extract_text() or ""
        clean_text = text.strip()
        
        if len(clean_text) >= SCANNED_PAGE_TEXT_THRESHOLD:
            # This page has enough text — it's a native digital page
            native_pages.append({
                "page_number": page_num,
                "text": clean_text,
                "source": "pypdf"
            })
        else:
            # This page is likely scanned / image-based
            scanned_page_nums.append(page_num)
    
    print(f"[PASS 1] Complete: {len(native_pages)} native text pages, {len(scanned_page_nums)} scanned pages detected.")
    
    # ==========================================
    # CLASSIFY NATIVE PAGES (Local Heuristics)
    # ==========================================
    all_pages = []
    for page in native_pages:
        classification = _classify_page_local(page["text"])
        keywords = _extract_simple_keywords(page["text"])
        summary = _generate_local_summary(page["text"], classification)
        all_pages.append({
            "page_number": page["page_number"],
            "text": page["text"],
            "classification": classification,
            "summary": summary,
            "keywords": keywords,
            "source": "pypdf"
        })
    
    # ==========================================
    # PASS 2: Gemini Vision OCR for Scanned Pages
    # ==========================================
    if scanned_page_nums and key:
        print(f"[PASS 2] Processing {len(scanned_page_nums)} scanned pages via Gemini Vision OCR...")
        vision_pages = _ocr_scanned_pages_with_gemini(pdf_path, scanned_page_nums, key)
        all_pages.extend(vision_pages)
        print(f"[PASS 2] Complete: {len(vision_pages)} pages processed via Gemini Vision.")
    elif scanned_page_nums and not key:
        print(f"[PASS 2] WARNING: {len(scanned_page_nums)} scanned pages found but no API key provided. These pages will have empty text.")
        for pn in scanned_page_nums:
            all_pages.append({
                "page_number": pn,
                "text": f"[Scanned page {pn} — OCR not available (no API key)]",
                "classification": "Unknown",
                "summary": f"Scanned page {pn}. OCR extraction skipped due to missing API key.",
                "keywords": "",
                "source": "skipped"
            })
    
    # Sort all pages by page number
    all_pages.sort(key=lambda x: x["page_number"])
    
    # ==========================================
    # GROUP INTO LOGICAL DOCUMENTS
    # ==========================================
    documents = _group_pages_into_documents(all_pages)
    
    source_label = "hybrid_multimodal" if scanned_page_nums and key else "local"
    return {
        "pages": all_pages,
        "documents": documents,
        "source": source_label,
        "stats": {
            "total_pages": total_pages,
            "native_pages": len(native_pages),
            "scanned_pages": len(scanned_page_nums),
        }
    }


def _ocr_scanned_pages_with_gemini(pdf_path: str, page_numbers: list, api_key: str) -> list:
    """
    Renders scanned pages to PNG images using PyMuPDF, then sends them 
    as inline base64 image data to Gemini for OCR + classification.
    
    Processes pages in batches of 5 to balance API calls vs. token limits.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("ERROR: PyMuPDF not installed. Run: pip install PyMuPDF")
        return [{
            "page_number": pn,
            "text": f"[Scanned page {pn} — PyMuPDF not installed]",
            "classification": "Unknown",
            "summary": f"Scanned page {pn}. PyMuPDF required for image rendering.",
            "keywords": "",
            "source": "error"
        } for pn in page_numbers]
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    # Open the PDF with PyMuPDF for image rendering
    doc = fitz.open(pdf_path)
    
    BATCH_SIZE = 5
    all_vision_pages = []
    
    # Process in batches
    for batch_start in range(0, len(page_numbers), BATCH_SIZE):
        batch_pages = page_numbers[batch_start:batch_start + BATCH_SIZE]
        batch_label = f"Batch {batch_start // BATCH_SIZE + 1}/{(len(page_numbers) + BATCH_SIZE - 1) // BATCH_SIZE}"
        print(f"  [Vision OCR] {batch_label}: Pages {batch_pages}")
        
        # Build the multimodal content parts
        content_parts = []
        
        for pn in batch_pages:
            page_idx = pn - 1  # PyMuPDF uses 0-indexed pages
            if page_idx < 0 or page_idx >= len(doc):
                continue
            
            page = doc[page_idx]
            # Render page to a PNG image at 150 DPI (good balance of quality vs size)
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")
            
            # Add an image part with inline data
            content_parts.append(f"--- PAGE {pn} IMAGE ---")
            content_parts.append({
                "inline_data": {
                    "mime_type": "image/png",
                    "data": img_b64
                }
            })
        
        # Add the OCR + classification prompt
        prompt = f"""You are an expert mortgage document auditor performing OCR on scanned document pages.

For EACH page image provided (labeled with its page number), perform the following:
1. Extract the COMPLETE text content visible on the page (performing full OCR).
2. Classify the page into exactly one of these document types:
   - "Bank Statement"
   - "W-2"
   - "Paystub"
   - "Form 1040 (Tax Return)"
   - "Closing Disclosure"
   - "Loan Estimate"
   - "Unknown"
3. Generate a 2-sentence summary of the page content.
4. Extract a list of high-value keywords (e.g. proper names, dollar amounts, dates, account numbers).

You MUST respond with a JSON object matching this exact schema:
{{
  "pages": [
    {{
      "page_number": {batch_pages[0]},
      "classification": "Bank Statement",
      "summary": "Summary of page content.",
      "text": "Full extracted page text here.",
      "keywords": ["Chase", "$1,234.00", "Checking"]
    }}
  ]
}}

The page numbers in this batch are: {batch_pages}
Return exactly {len(batch_pages)} page entries, one per image, in the same order."""

        content_parts.append(prompt)
        
        try:
            response = model.generate_content(
                content_parts,
                generation_config={"response_mime_type": "application/json"}
            )
            
            # Parse response
            resp_text = response.text.strip()
            if resp_text.startswith("```json"):
                resp_text = resp_text[7:]
            if resp_text.endswith("```"):
                resp_text = resp_text[:-3]
            
            parsed = json.loads(resp_text.strip())
            
            for p in parsed.get("pages", []):
                page_num = int(p.get("page_number", 0))
                if page_num not in batch_pages:
                    continue
                all_vision_pages.append({
                    "page_number": page_num,
                    "text": p.get("text", ""),
                    "classification": p.get("classification", "Unknown"),
                    "summary": p.get("summary", f"Scanned page {page_num} processed via Gemini Vision OCR."),
                    "keywords": ",".join(p.get("keywords", [])) if isinstance(p.get("keywords"), list) else str(p.get("keywords", "")),
                    "source": "gemini_vision"
                })
            
            # Small delay between batches to respect rate limits
            if batch_start + BATCH_SIZE < len(page_numbers):
                time.sleep(1)
                
        except Exception as e:
            print(f"  [Vision OCR] ERROR on {batch_label}: {str(e)}")
            # Add placeholder pages for this batch
            for pn in batch_pages:
                if not any(vp["page_number"] == pn for vp in all_vision_pages):
                    all_vision_pages.append({
                        "page_number": pn,
                        "text": f"[OCR failed for page {pn}: {str(e)}]",
                        "classification": "Unknown",
                        "summary": f"OCR extraction failed for scanned page {pn}.",
                        "keywords": "",
                        "source": "error"
                    })
    
    doc.close()
    return all_vision_pages


def _classify_page_local(text: str) -> str:
    """Classifies a page into a document type using keyword heuristics."""
    normalized = " ".join(text.split()).lower()
    
    if "closing disclosure" in normalized:
        return "Closing Disclosure"
    elif "form 1040" in normalized or "u.s. individual income tax return" in normalized:
        return "Form 1040 (Tax Return)"
    elif "w-2" in normalized or "wage and tax statement" in normalized:
        return "W-2"
    elif "pay stub" in normalized or "paystub" in normalized or "earnings statement" in normalized:
        return "Paystub"
    elif "bank statement" in normalized or "checking account" in normalized or "statement of account" in normalized:
        return "Bank Statement"
    elif "loan estimate" in normalized:
        return "Loan Estimate"
    return "Unknown"


def _generate_local_summary(text: str, classification: str) -> str:
    """Generates a brief summary from page text locally (no LLM)."""
    snippet = text[:200].replace("\n", " ").strip()
    if classification != "Unknown":
        return f"This page is classified as '{classification}'. Content preview: {snippet}..."
    return f"Page content extracted locally. Preview: {snippet}..."


def _group_pages_into_documents(pages: list) -> list:
    """Groups sequential pages into logical document boundaries."""
    documents = []
    current_doc = None
    
    for page in pages:
        doc_type = page["classification"]
        page_num = page["page_number"]
        confidence = 0.96 if doc_type != "Unknown" else 0.5
        visual = DOC_TYPE_META.get(doc_type, DOC_TYPE_META["Unknown"])
        
        # Determine if this is the start of a new document
        is_new_doc = False
        if current_doc is None:
            is_new_doc = True
        elif doc_type != "Unknown" and doc_type != current_doc["doc_type"]:
            is_new_doc = True
        
        if is_new_doc:
            if current_doc:
                documents.append(current_doc)
            current_doc = {
                "id": f"doc_{len(documents) + 1}",
                "doc_type": doc_type,
                "start_page": page_num,
                "end_page": page_num,
                "pages": [page_num],
                "metadata": {"summary": page.get("summary", "")},
                "confidence": confidence,
                "icon": visual["icon"],
                "color": visual["color"],
                "gradient": visual["gradient"]
            }
        else:
            current_doc["end_page"] = page_num
            current_doc["pages"].append(page_num)
    
    if current_doc:
        documents.append(current_doc)
    
    return documents


def enrich_mock_documents(documents: list) -> list:
    """Adds visual metadata to mock document entries."""
    enriched = []
    for doc in documents:
        if "icon" not in doc:
            visual = DOC_TYPE_META.get(doc["doc_type"], DOC_TYPE_META["Unknown"])
            doc["icon"] = visual["icon"]
            doc["color"] = visual["color"]
            doc["gradient"] = visual["gradient"]
            doc["confidence"] = 0.95
        enriched.append(doc)
    return enriched


def split_page_into_child_chunks(page_num: int, text: str) -> list:
    """Splits page text into child chunks (~100 tokens / 350 chars each) for indexing."""
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
        
    if not chunks:
        chunks.append({
            "page_number": page_num,
            "text_segment": text or f"[Page {page_num} Empty Content]",
            "keywords": ""
        })
        
    return chunks


def _extract_simple_keywords(text: str) -> str:
    """Extracts high-value terms (capitalized words, numbers, and key symbols) as keywords."""
    items = re.findall(r'\b(?:[A-Z][a-zA-Z0-9]+|\$[0-9,]+(?:\.[0-9]+)?|[0-9]{4})\b', text)
    unique_items = list(set(items))
    return ",".join(unique_items)
