

# --- DEBUG HELPERS ADDED BY ASSISTANT ---
import re, json, sys
def normalize_secret(s):
    if s is None:
        return ""
    s = s.strip()
    s = re.sub(r'\s+', ' ', s)
    return s

def dbg_print(tag, value):
    try:
        print(f"DEBUG[{tag}]:", repr(value))
        sys.stdout.flush()
    except Exception:
        pass
# --- END DEBUG HELPERS ---

import time
import json
import re
import os
import logging
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright

from src.solver_helpers import derive_answer_from_page

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Debug dump helper (HTML + downloads)
# -----------------------------------------------------------------------------
def _debug_dump_page(url: str, html: str, downloads: dict):
    safe = (
        url.replace("://", "_")
        .replace("/", "_")
        .replace("?", "_")
        .replace("&", "_")
        .replace("=", "_")
    )
    ts = int(time.time())
    outdir = "/tmp/llm_quiz_debug"
    os.makedirs(outdir, exist_ok=True)

    # HTML
    html_file = os.path.join(outdir, f"{safe}_{ts}.html")
    with open(html_file, "w", encoding="utf-8", errors="ignore") as fh:
        fh.write(html or "")

    # Download metadata
    meta_file = os.path.join(outdir, f"{safe}_{ts}_downloads.json")
    simplified = []
    for f in downloads.get("files", []):
        simplified.append({
            "type": f.get("type"),
            "url": f.get("url"),
            "filename": f.get("filename"),
            "bytes_len": len(f.get("bytes") or b""),
        })
    with open(meta_file, "w", encoding="utf-8") as fh:
        json.dump(simplified, fh, indent=2)

    # Save audio for debugging
    for i, f in enumerate(downloads.get("files", []) or []):
        if f.get("type") == "audio" and f.get("bytes"):
            fname = os.path.join(outdir, f"{safe}_{ts}_audio_{i}.wav")
            try:
                with open(fname, "wb") as af:
                    af.write(f["bytes"])
            except Exception:
                pass

    print("DEBUG DUMP →", outdir)


# -----------------------------------------------------------------------------
# Utility: determine file type from URL or content-type
# -----------------------------------------------------------------------------
def _detect_type(url: str, content_type: str = "") -> str:
    url = url.lower() if url else ""
    c = content_type.lower() if content_type else ""

    if url.endswith(".pdf") or "pdf" in c:
        return "pdf"
    if url.endswith(".csv") or "csv" in c:
        return "csv"
    if url.endswith(".wav") or url.endswith(".mp3") or "audio" in c:
        return "audio"
    return "binary"


# -----------------------------------------------------------------------------
# Download helper using Playwright fetch()
# -----------------------------------------------------------------------------
def _fetch_downloads(page, base_url) -> List[dict]:
    """Download referenced assets like PDF/CSV/audio."""
    results = []

    # collect <a href="..."> links
    links = page.query_selector_all("a")
    hrefs = []
    for a in links:
        try:
            h = a.get_attribute("href")
            if h:
                hrefs.append(h)
        except:
            pass

    # normalize to absolute URLs
    abs_urls = []
    for h in hrefs:
        try:
            abs_urls.append(urljoin(base_url, h))
        except:
            continue

    # fetch assets
    for u in abs_urls:
        try:
            # skip same page / JS links
            if u.startswith("javascript:"):
                continue

            resp = page.request.get(u, timeout=8000)
            if resp.status != 200:
                continue

            ctype = resp.headers.get("content-type", "")
            ftype = _detect_type(u, ctype)
            data = resp.body()

            results.append({
                "type": ftype,
                "url": u,
                "filename": os.path.basename(urlparse(u).path),
                "bytes": data,
            })
        except Exception:
            continue

    return results


# -----------------------------------------------------------------------------
# Post answer helper

def _post_answer(submit_url: str, email: str, secret: str, url: str, answer, timeout=12):
    """Post answer JSON to the target submit endpoint and return parsed JSON or error dict."""
    import requests
    payload = {
        "email": email,
        "secret": secret,
        "url": url,
        "answer": answer,
    }
    try:
        r = requests.post(submit_url, json=payload, timeout=timeout)
        try:
            return r.json()
        except Exception:
            return {"http_status": r.status_code, "text": r.text}
    except Exception as e:
        return {"http_status": "exception", "text": repr(e)}


# -----------------------------------------------------------------------------
# Main solver
# -----------------------------------------------------------------------------
def solve_quiz_sequence(start_url: str, email: str, secret: str, timeout_seconds: int = 170):
    logger.info(f"START solve_quiz_sequence for {start_url} with timeout {timeout_seconds}s")

    deadline = time.time() + timeout_seconds
    out_results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = browser.new_context()
        page = ctx.new_page()

        current_url = start_url

        while time.time() < deadline and current_url:
            logger.info(f"VISIT {current_url}")
            try:
                page.goto(current_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                logger.error(f"Page load error for {current_url}: {e}")
                break

            # page HTML
            try:
                html = page.content()
            except Exception:
                html = ""

            # download assets
            downloads = {"files": _fetch_downloads(page, current_url)}

            # debug dump
            _debug_dump_page(current_url, html, downloads)

            # derive answer
            derived = derive_answer_from_page(html, downloads)

            # find submit endpoint
            submit_url = None

            # Look for /submit in HTML
            m = re.search(r'https://[^"\'<>]+/submit\b', html)
            if m:
                submit_url = m.group(0)
            else:
                # fallback candidate
                parsed = urlparse(current_url)
                submit_url = f"{parsed.scheme}://{parsed.netloc}/submit"

            # post answer
            logger.info("SUBMIT to %s", submit_url)
            resp = _post_answer(submit_url, email, secret, current_url, derived["answer"])

            logger.info(f"POSTED RESPONSE: {resp}")

            out_results.append({
                "url": current_url,
                "submit_url": submit_url,
                "derived": derived,
                "submit_response": resp,
            })

            # follow next URL
            next_url = resp.get("url")
            if next_url:
                logger.info(f"FOLLOW NEXT URL → {next_url}")
                current_url = next_url
                continue
            else:
                break

        browser.close()

    return out_results
import re
def sum_numbers_from_csv_text(csv_text):
    nums = []
    for line in csv_text.splitlines():
        line = line.strip()
        if not line: continue
        tok = re.sub(r'[^0-9\-]', '', line)
        if not tok: continue
        try:
            nums.append(int(tok))
        except:
            continue
    return nums, sum(nums)

from playwright.sync_api import sync_playwright
def extract_secret_via_playwright(scrape_url, timeout_ms=60000):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox','--disable-dev-shm-usage'])
        page = browser.new_page()
        page.goto(scrape_url, timeout=timeout_ms)
        page.wait_for_selector("#question", timeout=20000)
        text = page.locator("#question").inner_text()
        browser.close()
    dbg_print("secret_from_dom", text)
    return normalize_secret(text)