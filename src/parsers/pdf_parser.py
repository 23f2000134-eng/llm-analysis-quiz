import io, pdfplumber, re

def parse_pdf_text(b: bytes):
    with pdfplumber.open(io.BytesIO(b)) as pdf:
        texts = [p.extract_text() or '' for p in pdf.pages]
    all_text = '\n'.join(texts)
    nums = re.findall(r"[-+]?[0-9]*\\.?[0-9]+", all_text)
    nums = [float(n) for n in nums] if nums else []
    if nums:
        return sum(nums)
    return all_text[:1500]
