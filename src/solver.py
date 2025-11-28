import time
import json
import requests
import urllib.parse
import ipaddress
import socket
import base64
import re
import logging
from playwright.sync_api import sync_playwright
from .parsers.csv_parser import parse_csv_from_bytes
from .parsers.pdf_parser import parse_pdf_text
from .utils.google_drive import download_drive_file

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')

def is_private_net(url):
    try:
        host = urllib.parse.urlparse(url).hostname
        if not host:
            return True
        ip = socket.gethostbyname(host)
        addr = ipaddress.ip_address(ip)
        return addr.is_private or addr.is_loopback or addr.is_reserved or addr.is_link_local
    except Exception:
        return True

def find_submit_url_in_text(text):
    # find URLs that contain 'submit' or '/submit'
    urls = re.findall(r'https?://[^\s"\'<>]+', text)
    for u in urls:
        if 'submit' in u:
            return u
    rel = re.search(r'["\'](\/[^\s"\'<>]*submit[^\s"\'<>]*)["\']', text)
    if rel:
        return rel.group(1)
    return None

def decode_atob_blocks(html_text):
    outs = []
    for m in re.finditer(r'atob\(\s*[`\'"]([A-Za-z0-9+/=\n\r]+)[`\'"]\s*\)', html_text):
        b64 = m.group(1)
        try:
            decoded = base64.b64decode(b64).decode('utf-8', errors='ignore')
            outs.append(decoded)
        except Exception:
            pass
    return outs

def extract_candidate_texts(page):
    texts = []
    try:
        res = page.query_selector('#result')
        if res:
            t = res.inner_text().strip()
            if t:
                texts.append(t)
    except Exception:
        pass

    try:
        pres = page.query_selector_all('pre')
        for p in pres:
            t = p.text_content().strip()
            if t:
                texts.append(t)
    except Exception:
        pass

    try:
        html = page.content()
        decoded_blocks = decode_atob_blocks(html)
        texts.extend([d for d in decoded_blocks if d])
        for m in re.finditer(r'\{[^}]{10,}\}', html, re.DOTALL):
            try:
                candidate = m.group(0)
                texts.append(candidate)
            except Exception:
                pass
    except Exception:
        pass

    return texts

def find_submit_url(page):
    try:
        anchors = page.query_selector_all('a')
        for a in anchors:
            href = a.get_attribute('href')
            if href and 'submit' in href:
                return page.evaluate('(el)=>el.href', a)
    except Exception:
        pass

    try:
        forms = page.query_selector_all('form')
        for f in forms:
            action = f.get_attribute('action')
            if action and 'submit' in action:
                return page.evaluate('(el)=>el.action', f)
    except Exception:
        pass

    texts = extract_candidate_texts(page)
    for t in texts:
        u = find_submit_url_in_text(t)
        if u:
            if u.startswith('/'):
                return urllib.parse.urljoin(page.url, u)
            return u

    try:
        html = page.content()
        u = find_submit_url_in_text(html)
        if u:
            if u.startswith('/'):
                return urllib.parse.urljoin(page.url, u)
            return u
    except Exception:
        pass

    return None

def extract_download_links(page):
    links = []
    try:
        anchors = page.query_selector_all('a')
        for a in anchors:
            href = a.get_attribute('href')
            if href and href.strip():
                links.append(page.evaluate('(el)=>el.href', a))
    except Exception:
        pass
    return links

def extract_json_from_texts(texts):
    for t in texts:
        try:
            j = json.loads(t)
            if isinstance(j, dict):
                return j
        except Exception:
            try:
                m = re.search(r'(\{.*\})', t, re.DOTALL)
                if m:
                    j = json.loads(m.group(1))
                    if isinstance(j, dict):
                        return j
            except Exception:
                pass
    return None

def post_answer(submit_url, email, secret, url, answer, timeout=15):
    logging.info(f'ABOUT TO POST to: {submit_url} with answer={str(answer)[:200]}')

    body = {'email': email, 'secret': secret, 'url': url, 'answer': answer}
    resp = requests.post(submit_url, json=body, timeout=timeout)
    try:
        return resp.json()
    except Exception:
        return {'http_status': resp.status_code, 'text': resp.text}

def try_candidate_submit(page_origin, email, secret, start_url, answer, timeout=8):
    candidates = [
        '/submit', '/api/submit', '/answer', '/api/answer',
        '/submit-answer', '/api/v1/submit', '/tds/submit', '/submit/', '/submit-answer/'
    ]
    for path in candidates:
        url = urllib.parse.urljoin(page_origin, path)
        logging.info(f'Trying candidate submit endpoint: {url}')
        body = {'email': email, 'secret': secret, 'url': start_url, 'answer': answer}
        try:
            resp = requests.post(url, json=body, timeout=timeout)
            if resp.status_code not in (404, 405):
                try:
                    return url, resp.json()
                except Exception:
                    return url, {'http_status': resp.status_code, 'text': resp.text}
            else:
                logging.info(f'Candidate {url} returned status {resp.status_code}')
        except Exception as e:
            logging.info(f'Candidate {url} raised {e}')
        time.sleep(0.2)
    return None, None

def solve_one_page(page, current_url, email, secret):
    try:
        page.goto(current_url, wait_until='domcontentloaded', timeout=20000)
    except Exception:
        try:
            page.goto(current_url, timeout=20000)
        except Exception:
            pass

    try:
        page.wait_for_timeout(800)
        page.wait_for_selector('#result', timeout=3000)
    except Exception:
        pass

    texts = extract_candidate_texts(page)
    payload = extract_json_from_texts(texts)

    answer = None
    submit_url = None
    if payload:
        # Prefer explicit submit fields only. Do NOT treat generic 'url' in payload as submit target
        submit_url = None
        for k in ('submit', 'submit_url', 'submitUrl'):
            if k in payload:
                submit_url = payload.get(k)
                break
        # As a weak fallback only if the URL value explicitly contains 'submit' text, accept it
        if not submit_url:
            maybe = str(payload.get('url') or '')
            if 'submit' in maybe.lower():
                submit_url = maybe
        if submit_url and isinstance(submit_url, str) and submit_url.startswith('/'):
            submit_url = urllib.parse.urljoin(page.url, submit_url)
        if 'answer' in payload:
            answer = payload.get('answer')

    if not submit_url:
        submit_url = find_submit_url(page)

    # If still no submit_url, try candidate endpoints on same origin
    if not submit_url:
        page_origin = urllib.parse.urljoin(page.url, '/')
        cand_url, cand_resp = try_candidate_submit(page_origin, email, secret, current_url, answer or "anything")
        if cand_url:
            logging.info(f'Found candidate submit_url {cand_url} with response {cand_resp}')
            submit_url = cand_url
            _candidate_submit_response = cand_resp
        else:
            _candidate_submit_response = None
    else:
        _candidate_submit_response = None

    # If no answer yet, try to find downloadable file and parse it
    if answer is None:
        download_links = extract_download_links(page)
        file_link = None
        for l in download_links:
            if l.lower().endswith(('.pdf', '.csv', '.xlsx')) or 'drive.google.com' in l:
                file_link = l
                break
        if file_link:
            if 'drive.google.com' in file_link:
                fid = None
                if '/d/' in file_link:
                    fid = file_link.split('/d/')[1].split('/')[0]
                elif 'id=' in file_link:
                    fid = file_link.split('id=')[1].split('&')[0]
                if fid:
                    tmp_path = f"/tmp/{fid}"
                    download_drive_file(fid, tmp_path)
                    try:
                        with open(tmp_path, 'rb') as fh:
                            b = fh.read()
                        answer = parse_pdf_text(b)
                    except Exception:
                        answer = 'downloaded_drive_file'
            else:
                if is_private_net(file_link):
                    raise Exception("Blocked private/internal URL")
                r = requests.get(file_link, timeout=30)
                r.raise_for_status()
                if file_link.lower().endswith('.csv'):
                    answer = parse_csv_from_bytes(r.content)
                elif file_link.lower().endswith('.pdf'):
                    answer = parse_pdf_text(r.content)
                else:
                    answer = len(r.content)

    if answer is None:
        combined = "\n\n".join(texts + [page.inner_text('body')[:2000]])
        nums = re.findall(r"[-+]?[0-9]*\.?[0-9]+", combined)
        if nums:
            try:
                answer = sum(float(n) for n in nums)
            except Exception:
                answer = combined[:500]
        else:
            answer = combined.strip()[:500]

    if submit_url and submit_url.startswith('/'):
        submit_url = urllib.parse.urljoin(page.url, submit_url)

    return answer, submit_url

def solve_quiz_sequence(start_url, email, secret, timeout_seconds=170):
    start_time = time.time()
    current_url = start_url
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox','--disable-dev-shm-usage'])
        context = browser.new_context()
        page = context.new_page()

        logging.info(f'START solve_quiz_sequence for {start_url} with timeout {timeout_seconds}s')

        while current_url and (time.time() - start_time) < timeout_seconds:
            logging.info(f'VISIT {current_url} at t={time.time()-start_time:.1f}s')
            page.goto(current_url, wait_until='domcontentloaded')
            answer, submit_url = solve_one_page(page, current_url, email, secret)
            if not submit_url:
                results.append({'url': current_url, 'error': 'no submit url found', 'answer_attempt': answer})
                break
            logging.info('POSTING answer to submit_url')
            # if candidate response was already captured, use it
            if '_candidate_submit_response' in locals() and locals().get('_candidate_submit_response') is not None:
                submit_resp = locals().get('_candidate_submit_response')
                logging.info(f'Using candidate submit response: {submit_resp}')
            else:
                submit_resp = post_answer(submit_url, email, secret, current_url, answer)
                logging.info(f'POSTED, got response: {submit_resp}')
            results.append({'url': current_url, 'submit_response': submit_resp})
            time.sleep(0.5)
            next_url = submit_resp.get('url') if isinstance(submit_resp, dict) else None
            current_url = next_url

        browser.close()
    return results
