import re
import os
import time
import json
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

def extract_and_classify_pdf(pdf_path: str, api_key: str = None) -> dict:
    """
    Ingests PDF. If a Gemini API Key is available, uses the Gemini Multimodal File API 
    for visual/OCR parsing and logical classification (Option C). Otherwise, falls back 
    to local heuristic-based parsing.
    """
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        print("No Gemini API key supplied for ingestion. Falling back to local PDF parsing.")
        return _extract_and_classify_pdf_local(pdf_path)
        
    try:
        genai.configure(api_key=key)
        print(f"Uploading {os.path.basename(pdf_path)} to Gemini File API...")
        uploaded_file = genai.upload_file(pdf_path)
        
        # Poll for processing status
        while uploaded_file.state.name == "PROCESSING":
            time.sleep(1)
            uploaded_file = genai.get_file(uploaded_file.name)
            
        if uploaded_file.state.name == "FAILED":
            raise ValueError("Gemini File API processing failed.")
            
        print("Document uploaded successfully. Parsing logical DOM schema...")
        prompt = """
        You are an expert mortgage document auditor. Analyze the uploaded PDF file page-by-page.
        For each page in the PDF, perform the following:
        1. Extract the full text content of the page (performing OCR if it is a scanned image or photo).
        2. Classify the page into exactly one of these document types:
           - "Bank Statement"
           - "W-2"
           - "Paystub"
           - "Form 1040 (Tax Return)"
           - "Closing Disclosure"
           - "Loan Estimate"
           - "Unknown"
        3. Generate a 2-sentence summary of the page content.
        4. Extract a list of high-value keywords (e.g. proper names, dollar amounts, transaction dates, account numbers).
        
        Response format:
        You MUST return a JSON object matching this schema:
        {
          "pages": [
            {
              "page_number": 1,
              "classification": "Bank Statement",
              "summary": "Summary of page content.",
              "text": "Full extracted page text here.",
              "keywords": ["Chase", "$1,234.00", "Checking"]
            }
          ]
        }
        """
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(
            [uploaded_file, prompt],
            generation_config={"response_mime_type": "application/json"}
        )
        
        # Clean up the file from Gemini File API
        try:
            genai.delete_file(uploaded_file.name)
        except Exception as e:
            print(f"Failed to delete uploaded file: {str(e)}")
            
        # Parse JSON output
        resp_text = response.text.strip()
        if resp_text.startswith("```json"):
            resp_text = resp_text[7:]
        if resp_text.endswith("```"):
            resp_text = resp_text[:-3]
        parsed_data = json.loads(resp_text.strip())
        
        # Assemble standard list format expected by main.py
        pages_list = []
        for p in parsed_data.get("pages", []):
            pages_list.append({
                "page_number": int(p["page_number"]),
                "text": p["text"],
                "classification": p["classification"],
                "summary": p["summary"],
                "keywords": ",".join(p.get("keywords", []))
            })
            
        # Sort pages numerically
        pages_list.sort(key=lambda x: x["page_number"])
        
        # Group pages into logical documents
        documents = []
        current_doc = None
        
        for page in pages_list:
            doc_type = page["classification"]
            page_num = page["page_number"]
            confidence = 0.96 if doc_type != "Unknown" else 0.5
            visual = DOC_TYPE_META.get(doc_type, DOC_TYPE_META["Unknown"])
            
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
                    "metadata": {"summary": page["summary"]},
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
            
        return {
            "pages": pages_list,
            "documents": documents,
            "source": "gemini"
        }
        
    except Exception as e:
        print(f"Gemini Multimodal parsing encountered an error: {str(e)}. Falling back to local parser.")
        return _extract_and_classify_pdf_local(pdf_path)

def _extract_and_classify_pdf_local(pdf_path: str) -> dict:
    """
    Extracts text page-by-page locally using PyPDF and groups pages
    into logical document boundaries using heuristics (fallback).
    """
    reader = pypdf.PdfReader(pdf_path)
    pages = []
    
    for idx, page in enumerate(reader.pages):
        page_num = idx + 1
        text = page.extract_text() or ""
        normalized_text = " ".join(text.split()).lower()
        pages.append({
            "page_number": page_num,
            "text": text,
            "normalized_text": normalized_text,
            "classification": "Unknown",
            "summary": "Page content extracted locally.",
            "keywords": ""
        })
        
    documents = []
    current_doc = None
    
    for page in pages:
        text = page["normalized_text"]
        page_num = page["page_number"]
        
        doc_type = "Unknown"
        metadata = {}
        confidence = 0.5
        
        if "closing disclosure" in text:
            doc_type = "Closing Disclosure"
            confidence = 0.95
        elif "form 1040" in text or "u.s. individual income tax return" in text:
            doc_type = "Form 1040 (Tax Return)"
            confidence = 0.92
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
            for bank in ["chase", "bank of america", "wells fargo", "citi", "capital one"]:
                if bank in text:
                    metadata["bank_name"] = bank.title()
                    confidence = 0.94
                    break
        elif "loan estimate" in text:
            doc_type = "Loan Estimate"
            confidence = 0.91
            
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
            current_doc["metadata"].update(metadata)
            
    if current_doc:
        documents.append(current_doc)
        
    return {
        "pages": pages,
        "documents": documents,
        "source": "local"
    }

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
