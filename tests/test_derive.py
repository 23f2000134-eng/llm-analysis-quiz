from src.solver_helpers import derive_answer_from_page

def test_fallback_sum():
    page_text = "Q: What is the sum? The numbers are 10, 20 and 30."
    downloads = {"files": []}
    res = derive_answer_from_page(page_text, downloads)
    assert isinstance(res, dict)
    assert abs(float(res["answer"]) - 60.0) < 1e-6

def test_csv_sum(tmp_path):
    csv_bytes = b"item,value\nA,5\nB,7\nC,8\n"
    downloads = {"files":[{"type":"csv","url":"file://tmp/test.csv","bytes": csv_bytes}]}
    page_text = "Please compute the sum of the 'value' column."
    res = derive_answer_from_page(page_text, downloads)
    assert float(res["answer"]) == 20.0
