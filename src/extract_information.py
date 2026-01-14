import re
import json
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Tuple

import pdfplumber

GRADE_TO_POINT = {
    "A+": 4.3,
    "A": 4.0,
    "A-": 3.7,
    "B+": 3.3,
    "B": 3.0,
    "B-": 2.7,
    "C+": 2.3,
    "C": 2.0,
    "D+": 1.3,
    "D": 1.0,
    "F": 0.0,
}

NON_FINAL_RESULTS = {"R", "#", "W"} # Registered / Late assessment pending / Withdrawal
NO_GRADE_RESULTS = {"RC"}  # Credit transfer without grade

COURSE_CODE_RE = re.compile(r"^[A-Za-z]{2,5}[A-Za-z0-9]{0,4}\d{3,5}[A-Za-z0-9]{0,3}$") #subject code ex) COMP1000, AMA1000, APSS1BN04, AF1000
CREDIT_RE = re.compile(r"^\d+\.\d$")  # e.g., 3.0. (r"^\d+(\.\d+)?$")  
SEM_RE = re.compile(r"^\d{4}/[12]$") #Year/Sem

@dataclass
class CourseRecord:
    course_code: str
    course_title: str
    credits: float
    result: str                      # grade or R/#/W/RC/""...
    year_sem: str                    # "2024/1" or ""
    duplicate: bool
    section: str                     # e.g., "Major/DSR - Compulsory"
    status: str                      # included / excluded / unknown
    grade_point: Optional[float]     # None if not included



def extract_text_pages(pdf_path: str) -> List[str]:
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages.append(text)
    return pages

def normalize_lines(pages_text: List[str]) -> List[str]:
    lines: List[str] = []
    for text in pages_text:
        for line in text.split("\n"):
            line = " ".join(line.split())  # collapse repeated spaces
            if line:
                lines.append(line)
    return lines

def detect_section(line: str, current: str) -> str:
    # Major/DSR blocks
    if line.strip() == "Major/DSR":
        return "Major/DSR"
    m = re.match(r"^\d+/\d+\s+(Compulsory|COMP Elective|Free elective|WIE)\b", line)
    if m:
        return f"{current.split(' - ')[0]} - {m.group(1)}" if "Major/DSR" in current else m.group(1)

    # Standalone headers
    if line.strip() in {"GUR", "LCR"}:
        return line.strip()
    if "(Service Learning)" in line:
        return "Service Learning"
    if "(LIPD)" in line:
        return "LIPD"
    if "(LCR-Chinese)" in line:
        return "LCR-Chinese"
    if "(LCR-English)" in line:
        return "LCR-English"

    return current

def parse_course_from_line(line: str, section: str) -> Optional[CourseRecord]:
    """
    Expected (mostly):
      CODE <TITLE...> <CREDIT> <RESULT?> <YEAR/SEM?> <Y?>
    Some entries may miss RESULT and YEAR/SEM (e.g., elective list).
    """
    tokens = line.split()
    if not tokens:
        return None
    if not COURSE_CODE_RE.match(tokens[0]):
        return None

    code = tokens[0]
    # Find credit token position (first float-like token)
    credit_idx = None
    for i in range(1, len(tokens)):
        if CREDIT_RE.match(tokens[i]):
            credit_idx = i
            break
    if credit_idx is None:
        return None

    title_tokens = tokens[1:credit_idx]
    title = " ".join(title_tokens).strip()

    credits = float(tokens[credit_idx])

    # After credits: [result] [year/sem] [Y]
    rest = tokens[credit_idx + 1 :]

    result = ""
    year_sem = ""
    duplicate = False

    if rest:
        # Duplicate indicator can be at the very end
        if rest[-1] == "Y":
            duplicate = True
            rest = rest[:-1]

    # year/sem usually last (after result)
    if rest and SEM_RE.match(rest[-1]):
        year_sem = rest[-1]
        rest = rest[:-1]

    # remaining one token could be result/grade (A-, B+, R, RC, #, W)
    if rest:
        result = rest[0]

    status, gp = classify_result(result)

    return CourseRecord(
        course_code=code,
        course_title=title,
        credits=credits,
        result=result,
        year_sem=year_sem,
        duplicate=duplicate,
        section=section,
        status=status,
        grade_point=gp,
    )


def classify_result(result: str) -> Tuple[str, Optional[float]]:
    # No result shown
    if result == "":
        return "unknown", None

    # Letter grade
    if result in GRADE_TO_POINT:
        return "included", GRADE_TO_POINT[result]

    # Known non-final
    if result in NON_FINAL_RESULTS:
        return "excluded", None

    # No-grade credit transfer
    if result in NO_GRADE_RESULTS:
        return "excluded", None

    # Anything else (future-proof)
    return "unknown", None


def dedup_by_course_code(records: List[CourseRecord]) -> Tuple[List[CourseRecord], List[Dict]]:
    """
    Keep 1 record per course_code.
    Priority:
      1) included (has grade_point)
      2) excluded (has explicit result like R/W/RC/#)
      3) unknown
    If tie, keep the one with year_sem (more informative).
    """
    def score(r: CourseRecord) -> Tuple[int, int]:
        s1 = 2 if r.status == "included" else (1 if r.status == "excluded" else 0)
        s2 = 1 if r.year_sem else 0
        return (s1, s2)

    chosen: Dict[str, CourseRecord] = {}
    dropped_logs: List[Dict] = []

    for r in records:
        key = r.course_code
        if key not in chosen:
            chosen[key] = r
            continue

        if score(r) > score(chosen[key]):
            dropped_logs.append({
                "course_code": chosen[key].course_code,
                "dropped_section": chosen[key].section,
                "kept_section": r.section,
                "reason": "dedup_replaced_with_higher_priority_record"
            })
            chosen[key] = r
        else:
            dropped_logs.append({
                "course_code": r.course_code,
                "dropped_section": r.section,
                "kept_section": chosen[key].section,
                "reason": "dedup_dropped_lower_priority_record"
            })

    return list(chosen.values()), dropped_logs


def compute_cgpa(records: List[CourseRecord]) -> Dict:
    included = [r for r in records if r.status == "included" and r.grade_point is not None]
    total_credits = sum(r.credits for r in included)
    total_gp = sum(r.credits * r.grade_point for r in included)
    cgpa = (total_gp / total_credits) if total_credits > 0 else None
    return {
        "current_cgpa": None if cgpa is None else round(cgpa, 3),
        "total_credits_counted": round(total_credits, 1),
        "grade_points_sum": round(total_gp, 3),
    }


def compute_goal_strategy(current_gp_sum: float, current_credits: float,
                          total_required_credits: float, goal_cgpa: float) -> Dict:
    remaining = total_required_credits - current_credits
    needed_total_gp = total_required_credits * goal_cgpa
    needed_from_remaining = needed_total_gp - current_gp_sum
    required_avg = needed_from_remaining / remaining if remaining > 0 else None

    # Convert to a rough letter-equivalent description (PolyU 4.3 scale)
    letter_equiv = None
    if required_avg is not None:
        # find nearest band
        # Changed: simple banding for explanation output
        bands = [
            ("A+", 4.3), ("A", 4.0), ("A-", 3.7),
            ("B+", 3.3), ("B", 3.0), ("B-", 2.7),
            ("C+", 2.3), ("C", 2.0),
        ]
        # find closest
        closest = min(bands, key=lambda b: abs(b[1] - required_avg))
        letter_equiv = f"~{closest[0]}"

    return {
        "goal_cgpa": goal_cgpa,
        "total_required_credits": total_required_credits,
        "remaining_credits": round(remaining, 1),
        "required_average_gp": None if required_avg is None else round(required_avg, 3),
        "required_letter_equivalent": letter_equiv,
    }


def main():
    
    pdf_path = input("Enter the path to the PDF file (e.g., ./data/sample_transcript.pdf): ").strip()

    pages = extract_text_pages(pdf_path)
    lines = normalize_lines(pages)

    section = "UNKNOWN"
    records: List[CourseRecord] = []

    for line in lines:
        section = detect_section(line, section)
        rec = parse_course_from_line(line, section)
        if rec:
            records.append(rec)

    deduped, dedup_logs = dedup_by_course_code(records)

    # Exclusion logs (after dedup)
    excluded_logs = []
    for r in deduped:
        if r.status != "included":
            excluded_logs.append({
                "course_code": r.course_code,
                "result": r.result,
                "section": r.section,
                "reason": (
                    "result_non_final" if r.result in NON_FINAL_RESULTS else
                    "result_no_grade" if r.result in NO_GRADE_RESULTS else
                    "missing_or_unknown_result"
                )
            })

    cgpa_info = compute_cgpa(deduped)
    current_gp_sum = cgpa_info["grade_points_sum"]
    current_credits = cgpa_info["total_credits_counted"]

    goal_cgpa = input("Enter your target CGPA from 0.00 to 4.30: ").strip()
    # goal analysis
    goal = compute_goal_strategy(
        current_gp_sum=current_gp_sum,
        current_credits=current_credits,
        total_required_credits=109.0,  # WIE excluded target
        goal_cgpa=float(goal_cgpa),
    )

    output = {
        "university": "PolyU",
        "grading_scale": "4.3",
        "summary": cgpa_info,
        "goal_analysis": goal,
        "courses": [asdict(r) for r in sorted(deduped, key=lambda x: (x.section, x.course_code))],
        "dedup_logs": dedup_logs,
        "excluded_logs": excluded_logs,
    }

    with open("transcript_parsed.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("Saved: transcript_parsed.json")
    print("Current CGPA:", cgpa_info["current_cgpa"], "Credits counted:", cgpa_info["total_credits_counted"])
    print("Goal required avg GP:", goal["required_average_gp"], "(", goal["required_letter_equivalent"], ")")


if __name__ == "__main__":
    main()