"""
Answer derivation helpers for LLM Analysis Quiz project.

Main export:
    derive_answer_from_page(page_text: str, downloads: dict) -> dict
The return dict format:
    {"answer": <str|number|object>, "method": "<short_method_name>", "meta": {...}}
"""

import re
from typing import Optional

# try importing parsers; fall back to no-op functions if unavailable
try:
    from src.parsers.pdf_parser import extract_text_from_pdf_bytes
except Exception:
    def extract_text_from_pdf_bytes(pdf_bytes: bytes, page_number: Optional[int] = None):
        return ""

try:
    from src.parsers.csv_parser import sum_column_from_csv_bytes
except Exception:
    def sum_column_from_csv_bytes(csv_bytes: bytes, column_name: Optional[str] = None):
        # best-effort: parse CSV without pandas (simple)
        import io, csv
        try:
            s = io.BytesIO(csv_bytes).read().decode("utf-8", errors="ignore")
            reader = csv.DictReader(s.splitlines())
            if not reader.fieldnames:
                return {}
            # if column_name provided, sum that column
            if column_name and column_name in reader.fieldnames:
                total = 0.0
                for r in reader:
                    try:
                        total += float(r.get(column_name, "") or 0)
                    except:
                        continue
                return float(total)
            # else sum numeric columns
            totals = {}
            for fn in reader.fieldnames:
                totals[fn] = 0.0
            for r in reader:
                for fn in reader.fieldnames:
                    try:
                        val = r.get(fn, "")
                        if val is None or val == "":
                            continue
                        totals[fn] += float(val)
                    except:
                        pass
            return totals
        except Exception:
            return {}

# ----------------------------
# small helpers
# ----------------------------
def extract_code_word_from_text(text: str) -> Optional[str]:
    """Search for likely code-word / secret patterns and return the word if found."""
    if not text:
        return None
    patterns = [
        r'code\s*word\s*(?:is|:)\s*["\']?\s*([A-Za-z0-9\-_]{3,40})\s*["\']?',
        r'the\s*secret\s*(?:is|:)\s*["\']?\s*([A-Za-z0-9\-_]{3,40})\s*["\']?',
        r'code[:\s]+\b([A-Za-z0-9\-_]{3,40})\b',
        r'\bsecret[:\s]+\b([A-Za-z0-9\-_]{3,40})\b',
        r'["\']([A-Za-z0-9\-_]{4,40})["\']\s*(?:is the secret|is the code)'
    ]
    for p in patterns:
        m = re.search(p, text, flags=re.I)
        if m:
            return m.group(1).strip()
    # fallback: find a short alphanumeric token near the word secret or code
    m = re.search(r'(?:secret|code)[^\n\r]{0,40}([A-Za-z0-9\-_]{3,40})', text, flags=re.I)
    if m:
        return m.group(1).strip()
    return None

def extract_numbers_from_text(text: str):
    """Return list of numbers (int/float) found in text. Normalizes commas."""
    if not text:
        return []
    nums = re.findall(r"[-+]?\d[\d,\.]*", text)
    out = []
    for n in nums:
        s = n.replace(",", "")
        # guard against trailing dots or single '-'
        if s in ("-", "+", "."):
            continue
        try:
            if "." in s:
                out.append(float(s))
            else:
                out.append(int(s))
        except Exception:
            try:
                out.append(float(s))
            except Exception:
                continue
    return out

def parse_page_number_from_text(text: str) -> Optional[int]:
    """If text mentions 'page N' return N (int)."""
    if not text:
        return None
    m = re.search(r'page\s*(?:no\.?|number)?\s*(\d+)', text, flags=re.I)
    if m:
        try:
            return int(m.group(1))
        except:
            return None
    return None

# ----------------------------
# main answer derivation pipeline
# ----------------------------
def derive_answer_from_page(page_text: str, downloads: dict) -> dict:
    """
    Decide an answer from page_text and downloaded files.
    downloads is expected to be a dict with key "files": list of dicts with keys:
      - type: "pdf"|"csv"|"audio"|... (optional)
      - bytes: raw bytes (optional)
      - url: source url (optional)
      - filename: optional filename
    Returns {"answer": ..., "method": "<method>", "meta": {...}}
    """
    downloads = downloads or {}
    files = downloads.get("files", []) or []

    # 1) If explicit JSON string 'answer' appears in the page (pre blocks etc)
    #    look for patterns like: "answer": 123 or "answer": "some text"
    m = re.search(r'"answer"\s*:\s*(".*?"|\d+(\.\d+)?)', page_text or "", flags=re.I)
    if m:
        raw = m.group(1)
        # strip quotes if string
        if raw.startswith('"') and raw.endswith('"'):
            val = raw.strip('"')
        else:
            try:
                val = float(raw) if "." in raw else int(raw)
            except:
                val = raw
        return {"answer": val, "method": "explicit_json_string", "meta": {}}

    # 2) Try extract code/secret if page asks for a secret or contains code-word
    if page_text and re.search(r'\b(secret|code word|codeword|code)\b', page_text, flags=re.I):
        code = extract_code_word_from_text(page_text)
        if code:
            return {"answer": code, "method": "code_word_scrape", "meta": {"found_in": "page_text"}}

    # 3) If CSV file present and page explicitly asks sum of a column, prefer CSV parsing
    #    e.g., "sum of the 'value' column" or "sum of values"
    col_name = None
    col_m = re.search(r"sum of (?:the )?[\"']?([A-Za-z0-9 _\-]+)[\"']? column", page_text or "", flags=re.I)
    if col_m:
        col_name = col_m.group(1).strip()
    # If csv available, try to use it
    for f in files:
        if f.get("type") == "csv" and f.get("bytes"):
            try:
                # use csv parser helper; it may return a number or dict
                csv_res = sum_column_from_csv_bytes(f["bytes"], column_name=col_name)
                # If returned a dict (multiple numeric columns), choose column_name if present else first numeric
                if isinstance(csv_res, dict):
                    if col_name and col_name in csv_res:
                        return {"answer": float(csv_res[col_name]), "method": "csv_column_sum", "meta": {"column": col_name}}
                    # pick first numeric
                    for k, v in csv_res.items():
                        try:
                            return {"answer": float(v), "method": "csv_first_numeric_sum", "meta": {"column": k}}
                        except:
                            continue
                else:
                    # scalar
                    try:
                        return {"answer": float(csv_res), "method": "csv_column_sum", "meta": {"column": col_name}}
                    except:
                        return {"answer": csv_res, "method": "csv_column_sum", "meta": {"column": col_name}}
            except Exception:
                continue

    # 4) If PDF download present and the prompt mentions "page N" or column, extract from that page
    page_num = parse_page_number_from_text(page_text or "")
    if page_num:
        for f in files:
            if f.get("type") == "pdf" and f.get("bytes"):
                try:
                    txt = extract_text_from_pdf_bytes(f["bytes"], page_number=page_num)
                    # if column name was found, try to extract numbers for that column by scanning text lines
                    if col_name and txt:
                        # crude approach: find lines mentioning column name and numbers nearby
                        pattern = re.compile(r'.{0,40}'+re.escape(col_name)+r'.{0,120}', flags=re.I)
                        m = pattern.search(txt)
                        if m:
                            snippet = m.group(0)
                            nums = extract_numbers_from_text(snippet)
                            if nums:
                                return {"answer": sum(nums), "method": "pdf_page_column_sum_snippet", "meta": {"page": page_num, "column": col_name, "snippet": snippet}}
                    # otherwise, sum all numbers on that page as fallback
                    nums = extract_numbers_from_text(txt)
                    if nums:
                        return {"answer": sum(nums), "method": "pdf_page_sum_all_numbers", "meta": {"page": page_num}}
                except Exception:
                    continue

    # 5) If audio is present, transcribe then parse numbers or code words
    for f in files:
        if f.get("type") == "audio" and f.get("bytes"):
            try:
                # lazy import to avoid hard dependency if not used
                try:
                    from src.utils.transcribe_openai import transcribe_audio_bytes
                except Exception:
                    transcribe_audio_bytes = None
                transcript = None
                if transcribe_audio_bytes:
                    transcript = transcribe_audio_bytes(f["bytes"])
                else:
                    # if no transcribe helper, try to save bytes to file and skip (can't transcribe)
                    transcript = ""
                # if transcript contains 'secret' or 'code' try code extractor
                if transcript and re.search(r'\b(secret|code word|codeword|code)\b', transcript, flags=re.I):
                    code = extract_code_word_from_text(transcript)
                    if code:
                        return {"answer": code, "method": "audio_transcription_code", "meta": {"transcript": transcript[:200]}}
                # else extract numbers and sum
                nums = extract_numbers_from_text(transcript or "")
                if nums:
                    return {"answer": sum(nums), "method": "audio_transcription_sum", "meta": {"transcript_snippet": (transcript or "")[:200]}}
            except Exception:
                continue

    # 6) Heuristic: if page_text asks explicitly for sum of numbers, sum numbers in page_text
    if re.search(r'\bsum\b', page_text or "", flags=re.I):
        nums = extract_numbers_from_text(page_text or "")
        if nums:
            return {"answer": sum(nums), "method": "heuristic_sum_page_text", "meta": {"count": len(nums)}}

    # 7) If page_text explicitly asks for a boolean question, look for yes/no words
    if re.search(r'\bis it\b|\bshould\b|\bis the\b', page_text or "", flags=re.I):
        # naive yes/no detection: look for "yes" or "no" near the question
        if re.search(r'\byes\b', page_text or "", flags=re.I):
            return {"answer": True, "method": "heuristic_bool_yes_present", "meta": {}}
        if re.search(r'\bno\b', page_text or "", flags=re.I):
            return {"answer": False, "method": "heuristic_bool_no_present", "meta": {}}

    # 8) Fallback: return short snippet as answer (first 400 chars)
    snippet = (page_text or "").strip()[:400]
    return {"answer": snippet or "", "method": "fallback_snippet", "meta": {}}
