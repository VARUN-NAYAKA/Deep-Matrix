import os
import shutil
import time
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import db_cache
import pdf_processor
from pdf_processor import extract_and_classify_pdf, enrich_mock_documents
from qa_engine import query_document
from mock_data import MOCK_LOAN_FILE

app = FastAPI(title="InfrX Mortgage QA Agent v2", version="2.0.0")

# Enable CORS for local testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory document storage fallback & initial state
_mock = MOCK_LOAN_FILE.copy()
_mock["documents"] = enrich_mock_documents(_mock["documents"])
_mock["id"] = "mock_doc"  # Identify mock data uniquely
CURRENT_DOC_DATA = _mock
CURRENT_DOC_NAME = "Mock_Mortgage_File_Sample.pdf (Preloaded)"

class QueryRequest(BaseModel):
    query: str
    api_key: str = None

def populate_db_with_doc(doc_id: str, doc_name: str, doc_data: dict):
    """Helper to split pages and populate the parent/child chunks cache in SQLite."""
    # 1. Save document index record
    db_cache.save_document(doc_id, doc_name, len(doc_data["pages"]))
    
    # 2. Map page numbers to logical classifications
    page_to_class = {}
    for doc in doc_data["documents"]:
        classification = doc["doc_type"]
        for p_num in doc["pages"]:
            page_to_class[p_num] = classification
            
    # 3. Store Parent and Child chunks
    for page in doc_data["pages"]:
        page_num = page["page_number"]
        text = page["text"]
        classification = page_to_class.get(page_num, "Unknown")
        
        # Save page as a parent chunk
        parent_id = f"{doc_id}_p_{page_num}"
        db_cache.save_parent_chunk(parent_id, doc_id, page_num, text, classification)
        
        # Split text into child chunks and store
        child_segments = pdf_processor.split_page_into_child_chunks(page_num, text)
        for idx, child in enumerate(child_segments):
            child_id = f"{doc_id}_c_{page_num}_{idx}"
            db_cache.save_child_chunk(
                child_id, 
                parent_id, 
                page_num, 
                child["text_segment"], 
                child.get("keywords")
            )

@app.on_event("startup")
def startup_event():
    """Initializes the database schema and preloads the mock mortgage file into SQLite cache."""
    db_cache.init_db()
    # Cache the mock data so routing works on first run
    populate_db_with_doc("mock_doc", CURRENT_DOC_NAME, CURRENT_DOC_DATA)
    print("Database initialized and mock document cached successfully.")

@app.get("/api/status")
def get_status():
    return {
        "loaded": CURRENT_DOC_DATA is not None,
        "document_name": CURRENT_DOC_NAME,
        "page_count": len(CURRENT_DOC_DATA["pages"]) if CURRENT_DOC_DATA else 0,
        "document_count": len(CURRENT_DOC_DATA["documents"]) if CURRENT_DOC_DATA else 0,
        "env_key_available": bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    }

@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    global CURRENT_DOC_DATA, CURRENT_DOC_NAME
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        
    temp_dir = "temp"
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, file.filename)
    
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Process and classify the PDF
        result = extract_and_classify_pdf(temp_path)
        
        # Generate clean unique ID for this upload
        doc_id = f"upload_{int(time.time())}"
        
        # Set state
        CURRENT_DOC_DATA = {
            "id": doc_id,
            "pages": result["pages"],
            "documents": result["documents"]
        }
        CURRENT_DOC_NAME = file.filename
        
        # Write to SQLite Cache (Parent-Child chunk structures)
        populate_db_with_doc(doc_id, CURRENT_DOC_NAME, CURRENT_DOC_DATA)
        
        return {
            "message": "File uploaded, classified, and cached successfully",
            "document_name": CURRENT_DOC_NAME,
            "page_count": len(result["pages"]),
            "documents": result["documents"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process PDF: {str(e)}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@app.post("/api/query")
def query_doc(req: QueryRequest):
    global CURRENT_DOC_DATA
    if not CURRENT_DOC_DATA:
        raise HTTPException(status_code=400, detail="No document loaded. Please upload a PDF first.")
        
    try:
        answer_data = query_document(req.query, CURRENT_DOC_DATA, req.api_key)
        return answer_data
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/pages")
def get_pages():
    global CURRENT_DOC_DATA
    if not CURRENT_DOC_DATA:
        return []
    # Return pages without full text to save bandwidth
    return [{"page_number": p["page_number"], "preview": p["text"][:300] + "..."} for p in CURRENT_DOC_DATA["pages"]]

@app.get("/api/page/{page_num}")
def get_page_content(page_num: int):
    global CURRENT_DOC_DATA
    if not CURRENT_DOC_DATA:
        raise HTTPException(status_code=404, detail="No document loaded")
    for p in CURRENT_DOC_DATA["pages"]:
        if p["page_number"] == page_num:
            return {
                "page_number": page_num,
                "text": p["text"]
            }
    raise HTTPException(status_code=404, detail="Page not found")

@app.get("/api/documents")
def get_documents_list():
    global CURRENT_DOC_DATA
    if not CURRENT_DOC_DATA:
        return []
    return CURRENT_DOC_DATA["documents"]

# Mount static folder
os.makedirs("static", exist_ok=True)
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
