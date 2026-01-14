# Academic Transcript Data Pipeline (PolyU)

A rule-based ETL pipeline that extracts and normalizes semi-structured academic records from PDF transcripts, deduplicates multi-category entries, and computes CGPA / goal-based GPA planning metrics with traceable exclusion logs.

---

## Why this project

Academic transcripts often come as PDF documents that are easy for humans to read but inconvenient for automation. This project focuses on deterministic parsing and validation (not ML) to transform transcript PDFs into structured, auditable records.

---

## Features

- **PDF input support**: Extracts text from transcript PDFs and parses course records
- **Course record structuring**: Produces schema-consistent JSON for each parsed course row
- **Deduplication**: Removes duplicate course rows that appear under multiple categories (e.g., Free Elective + LCR)
- **Automatic classification**
  - **Letter-graded** courses included in CGPA
  - **Registered / in-progress** records excluded (e.g., `R`)
  - **Missing grade / unknown status** excluded with reason logs
  - **Pass/Fail scenarios** supported via toggle (e.g., WIE)
- **CGPA calculation**
  - Computes CGPA using included courses only
  - Outputs an **exclusion log** explaining why each record was skipped
- **Goal-based planning**
  - Given a **target CGPA** and **remaining credits**, estimates the required average grade point
  - Supports scenario analysis (e.g., whether Capstone is counted as letter-graded or excluded)

---

## Output Format (JSON)

The pipeline outputs a single JSON file containing:

- `courses[]`: structured course records
- `dedup_logs[]`: which duplicate entries were dropped and why
- `excluded_logs[]`: excluded courses and exclusion reasons
- `summary`: credit-weighted CGPA computation summary
- `goal_analysis`: required performance to reach target CGPA

Example (abridged):

```json
{
  "summary": {
    "current_cgpa": 3.42,
    "total_credits_counted": 79.0
  },
  "goal_analysis": {
    "goal_cgpa": 3.50,
    "remaining_credits": 30.0,
    "required_average_gp": 3.78
  },
  "courses": [
    {
      "course_code": "COMP2011",
      "course_title": "DATA STRUCTURES",
      "credits": 3.0,
      "result": "B+",
      "year_sem": "2024/1",
      "section": "Major/DSR - Compulsory",
      "status": "included"
    }
  ]
}
````

---

## Privacy & Data Ethics

This repository does **not** contain any real academic records.

* All sample transcripts and outputs are **fully anonymized** and contain **synthetic grades**.
* The author tested the pipeline locally on a real transcript, but publishes only mock data to protect privacy.

---

## Repository Structure

```text
academic-transcript-data-pipeline/
├─ src/
│  ├─ eda.py
│  ├─ parser.py
│  ├─ cgpa.py
│  └─ rules.py
├─ samples/
│  ├─ sample_transcript.txt
│  ├─ sample_transcript.pdf
│  └─ sample_output.json
├─ generate_sample_pdf.py
└─ README.md
```

---

## Quick Start

### 1) Install dependencies

```bash
pip install -r requirements.txt
```

If you don’t have a `requirements.txt` yet, this is the typical minimal set:

```bash
pip install pdfplumber reportlab
```

### 2) Generate a synthetic sample PDF (optional)

```bash
python generate_sample_pdf.py
```

This creates:

* `samples/sample_transcript.pdf`

### 3) Run the pipeline

```bash
python -u src/eda.py
```

Expected output:

* Parsed pages printed to stdout
* Structured JSON saved (e.g., `transcript_parsed.json`)

---

## Configuration Notes

### Course code parsing

The pipeline uses a flexible course-code pattern to support variations such as:

* `AF1000`
* `APSS1BN04`
* codes with mixed letters/digits and non-uniform suffix lengths

The extracted course codes are normalized to uppercase for consistency.

### Exclusion rules

Common exclusion reasons include:

* `R` (registered / in-progress)
* missing grade
* transfer credits without grade
* pass/fail items (toggleable)

All excluded items are logged in `excluded_logs[]`.

---

## Capstone / Pass-Fail Scenarios

Some programmes may treat certain courses (e.g., WIE, Capstone) differently for CGPA.
This project supports scenario branching by allowing:

* **include** as letter-graded
* **exclude** as pass/fail or non-counted

The chosen scenario is recorded in output metadata.

---

## Roadmap

* Add CLI flags:

  * `--target-cgpa`
  * `--total-required-credits`
  * `--capstone-mode {include,exclude}`
* Add JSON Schema validation (data contract)
* Add batch processing for multiple PDFs
* Add more robust table-aware extraction when PDFs contain embedded tables

---
