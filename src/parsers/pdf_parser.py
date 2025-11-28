# src/parsers/pdf_parser.py
import fitz  # PyMuPDF

def extract_text_from_pdf_bytes(pdf_bytes, page_number=None):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    if page_number is None:
        return "\n".join(p.get_text() for p in doc)
    idx = max(0, page_number-1)
    if idx >= len(doc):
        return ""
    return doc[idx].get_text("text")

