import sqlite3
import os

DB_PATH = "loan_audit_cache.db"

def get_connection():
    """Returns a connection to the SQLite cache database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database schema if tables do not exist."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Documents Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        total_pages INTEGER NOT NULL,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 2. Parent Chunks Table (Page-level text and classifications)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS parent_chunks (
        id TEXT PRIMARY KEY,
        doc_id TEXT NOT NULL,
        page_number INTEGER NOT NULL,
        text_content TEXT NOT NULL,
        doc_classification TEXT NOT NULL,
        summary TEXT,
        FOREIGN KEY(doc_id) REFERENCES documents(id) ON DELETE CASCADE
    )
    """)
    
    # 3. Child Chunks Table (Sub-page segments/sentences for search indexing)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS child_chunks (
        id TEXT PRIMARY KEY,
        parent_id TEXT NOT NULL,
        page_number INTEGER NOT NULL,
        text_segment TEXT NOT NULL,
        keywords TEXT,
        FOREIGN KEY(parent_id) REFERENCES parent_chunks(id) ON DELETE CASCADE
    )
    """)
    
    conn.commit()
    conn.close()

def save_document(doc_id: str, name: str, total_pages: int):
    """Saves or replaces a document in the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO documents (id, name, total_pages) VALUES (?, ?, ?)",
        (doc_id, name, total_pages)
    )
    conn.commit()
    conn.close()

def save_parent_chunk(chunk_id: str, doc_id: str, page_number: int, text_content: str, doc_classification: str, summary: str = None):
    """Saves a parent page chunk to the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO parent_chunks (id, doc_id, page_number, text_content, doc_classification, summary) VALUES (?, ?, ?, ?, ?, ?)",
        (chunk_id, doc_id, page_number, text_content, doc_classification, summary)
    )
    conn.commit()
    conn.close()

def save_child_chunk(chunk_id: str, parent_id: str, page_number: int, text_segment: str, keywords: str = None):
    """Saves a child segment chunk to the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO child_chunks (id, parent_id, page_number, text_segment, keywords) VALUES (?, ?, ?, ?, ?)",
        (chunk_id, parent_id, page_number, text_segment, keywords)
    )
    conn.commit()
    conn.close()

def get_child_chunks(doc_id: str) -> list:
    """Retrieves all child chunks associated with a specific document ID for search indexing."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.id, c.page_number, c.text_segment, c.keywords 
        FROM child_chunks c
        JOIN parent_chunks p ON c.parent_id = p.id
        WHERE p.doc_id = ?
    """, (doc_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_parent_pages_text(doc_id: str, page_numbers: list) -> list:
    """Retrieves raw page texts for specified page numbers."""
    if not page_numbers:
        return []
    conn = get_connection()
    cursor = conn.cursor()
    # Safely generate query placeholders
    placeholders = ",".join("?" for _ in page_numbers)
    query = f"""
        SELECT page_number, text_content, doc_classification 
        FROM parent_chunks 
        WHERE doc_id = ? AND page_number IN ({placeholders})
        ORDER BY page_number ASC
    """
    params = [doc_id] + list(page_numbers)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def clear_document(doc_id: str):
    """Deletes all chunks and records associated with a document ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()
