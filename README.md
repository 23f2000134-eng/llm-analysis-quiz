# LLM Analysis Quiz — Automated Solver

A fully automated quiz-solving system built for the **IITM BS TDS LLM Analysis Quiz (Nov 2025)**.

This application exposes an HTTP POST endpoint that receives quiz tasks, visits the quiz URL using a headless browser (Playwright + Chromium), extracts information, analyzes associated data (PDF/CSV/HTML/Audio), computes the answer, and submits it back to the quiz server.

Designed according to the official specification:
https://discourse.onlinedegree.iitm.ac.in/t/project-2-llm-analysis-quiz-tds-sep-2025/

---

## 🚀 Features

### ✔ Fully Automated Quiz-Solving Pipeline
- Visits quiz URLs automatically  
- Executes JavaScript using **Playwright**  
- Scrapes dynamic & base64-embedded HTML  
- Downloads & parses:
  - PDF files (PyMuPDF)
  - CSV files (pandas)
  - Audio (WAV/MP3)
  - Images
- Optional: Audio transcription using **OpenAI Whisper API**
- Computes answers with custom heuristics & logic
- Submits multiple attempts within the allowed 3-minute window
- Follows chain of "next quiz" URLs automatically

---

## ✔ REST API Endpoint

### `POST /api/quiz`

**Example request body:**

```json
{
  "email": "test@example.com",
  "secret": "Monkey D Luffy",
  "url": "https://tds-llm-analysis.s-anand.net/demo"
}

