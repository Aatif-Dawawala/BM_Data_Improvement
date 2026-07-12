"""
Brilliant Muslim — AI Lesson Review Pipeline
=============================================
Architecture:
  1. Fetch lesson + all quiz content from the API
  2. For each quiz, run a separate Review Agent per quiz type
  3. Each review goes through: Review Agent → Guardrail Agent → Review Agent (revised)
  4. Combine lesson content feedback + all quiz feedback into one Markdown report

Usage:
    python review_pipeline.py --lesson l-001            # single lesson
    python review_pipeline.py --lesson lc-002           # all 26 parts of Al-Baqara
    python review_pipeline.py --lesson lc-002 --sample 5  # random 5 from Al-Baqara
    python review_pipeline.py --course c-001 --sample 5   # random 5 from entire course
"""

# Set up log file to see input and output for each agent & cost for each run
# Tweak system prompt manually after checking if the feedback matches well with the content
# Have AI raise PR with its changes to the lesson content

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Optional

import anthropic
import requests
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = "https://europe-west2-brilliantmuslim.cloudfunctions.net/mobile-api"
COURSE_URL = f"{BASE_URL}/course?course_id=c-001"
OUTPUT_DIR = Path("./lesson_reports")
MODEL = "claude-sonnet-4-6"          # always use Sonnet 4.6 for inner calls; outer calls use same
MAX_TOKENS = 2048

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class QuizQuestion(BaseModel):
    question_id: str
    question_type: str
    title: str
    explanation: str = ""
    choices: list[dict] = Field(default_factory=list)
    correct_list: list[str] = Field(default_factory=list)
    given_list: list[str] = Field(default_factory=list)
    interactive_text: Optional[dict] = None
    audio_data: Optional[dict] = None


class QuizContent(BaseModel):
    quiz_id: str
    quiz_title: str
    quiz_type_label: str          # e.g. "Basics", "Vocabulary", "Real-Life Challenges"
    questions: list[QuizQuestion]


class LessonContent(BaseModel):
    lesson_id: str
    lesson_title: str
    surah_name: str
    metadata: str = ""
    summary: str = ""
    story_text: str = ""          # extracted narrative prose from the story pages
    quizzes: list[QuizContent] = Field(default_factory=list)


class ReviewIssue(BaseModel):
    location: str                 # e.g. "Q3 explanation", "story paragraph 2"
    issue_type: str               # e.g. "factual_error", "clarity", "cognitive_load"
    severity: str                 # "critical" | "warning" | "note"
    description: str
    suggested_fix: str = ""


class ReviewResult(BaseModel):
    target: str                   # "lesson_content" | quiz_id
    issues: list[ReviewIssue]


# ---------------------------------------------------------------------------
# API Fetchers
# ---------------------------------------------------------------------------

def fetch_json(url: str) -> dict:
    """Fetch JSON from a URL with basic error handling."""
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        print(f"  [WARN] Failed to fetch {url}: {e}")
        return {}


def extract_story_text(story_data: dict) -> str:
    """Pull all text blocks out of story pages."""
    lines = []
    for page in story_data.get("pages", []):
        for block in page.get("blocks", []):
            if isinstance(block, dict) and "text" in block:
                lines.append(block["text"].strip())
    return "\n".join(filter(None, lines))


def parse_question(q: dict) -> QuizQuestion:
    return QuizQuestion(
        question_id=q.get("questionId", ""),
        question_type=q.get("questionType", ""),
        title=q.get("title", ""),
        explanation=q.get("explanation", ""),
        choices=q.get("choices", []),
        correct_list=q.get("correctList", []),
        given_list=q.get("givenList", []),
        interactive_text=q.get("interactiveText"),
        audio_data=q.get("audioData"),
    )


def _is_collection_id(lesson_id: str) -> bool:
    """Collection IDs start with 'lc-'; individual lesson IDs start with 'l-'."""
    return lesson_id.startswith("lc-")


def _build_lesson_content(lesson_id: str, lesson_data: dict) -> LessonContent:
    """Build a LessonContent from a raw lesson API response dict."""
    surah_name = lesson_data.get("name", lesson_id)

    story_text = ""
    story_ref = lesson_data.get("story", {})
    if story_ref and story_ref.get("url"):
        story_data = fetch_json(story_ref["url"])
        story_text = extract_story_text(story_data)

    quizzes: list[QuizContent] = []
    for quiz_ref in lesson_data.get("quizzes", []):
        quiz_data = fetch_json(quiz_ref.get("url", ""))
        if not quiz_data:
            continue
        questions = [parse_question(q) for q in quiz_data.get("questions", [])]
        quizzes.append(QuizContent(
            quiz_id=quiz_data.get("quizId", quiz_ref.get("id", "")),
            quiz_title=quiz_data.get("name", ""),
            quiz_type_label=quiz_ref.get("title", ""),
            questions=questions,
        ))
        time.sleep(0.2)

    return LessonContent(
        lesson_id=lesson_id,
        lesson_title=lesson_data.get("name", lesson_id),
        surah_name=surah_name,
        metadata=lesson_data.get("metaData", ""),
        summary=lesson_data.get("summary", ""),
        story_text=story_text,
        quizzes=quizzes,
    )


def fetch_single_lesson(lesson_id: str) -> Optional[LessonContent]:
    """
    Fetch one individual lesson (l-XXX) and all its quizzes.
    Uses the /lesson endpoint.
    """
    print(f"\n→ Fetching lesson {lesson_id}...")
    lesson_data = fetch_json(f"{BASE_URL}/lesson?lesson_id={lesson_id}")
    if not lesson_data:
        return None
    return _build_lesson_content(lesson_id, lesson_data)


def fetch_collection_sub_lesson_ids(collection_id: str) -> list[str]:
    """
    Fetch a lesson-collection (lc-XXX) and return the list of individual
    sub-lesson IDs it contains.
    """
    print(f"\n→ Fetching collection index {collection_id}...")
    collection_data = fetch_json(f"{BASE_URL}/lesson-collection?collection_id={collection_id}")
    if not collection_data:
        return []

    # The collection response has a "lessons" array, each with a "lessonUrl"
    # and an "id" field for the individual lesson.
    sub_ids: list[str] = []
    for entry in collection_data.get("lessons", []):
        sub_id = entry.get("id", "")
        if sub_id:
            sub_ids.append(sub_id)

    if not sub_ids:
        # Fallback: some collections embed lessonIds at the top level
        sub_ids = collection_data.get("lessonIds", [])

    print(f"  → Found {len(sub_ids)} sub-lesson(s) in {collection_id}")
    return sub_ids


def fetch_lesson(lesson_id: str) -> Optional[LessonContent]:
    """
    Smart dispatcher: detects whether lesson_id is a collection (lc-XXX)
    or a single lesson (l-XXX) and routes accordingly.

    - Single lesson → fetches directly and returns one LessonContent.
    - Collection ID → fetches the FIRST sub-lesson only (used when the caller
      passes a specific collection ID directly via --lesson).
      Use fetch_collection_sub_lesson_ids() to get all sub-lesson IDs for
      batch processing.
    """
    if _is_collection_id(lesson_id):
        sub_ids = fetch_collection_sub_lesson_ids(lesson_id)
        if not sub_ids:
            print(f"  [ERROR] Collection {lesson_id} returned no sub-lessons.")
            return None
        # Return the first sub-lesson as a representative; batch mode uses
        # review_collection() to iterate all of them.
        print(f"  [INFO] Collection detected. Pass --lesson {lesson_id} with --sample N to review a subset,")
        print(f"         or use --course c-001 --sample N to sample across the full course.")
        print(f"  → Processing first sub-lesson: {sub_ids[0]}")
        return fetch_single_lesson(sub_ids[0])
    else:
        return fetch_single_lesson(lesson_id)


def resolve_lesson_ids(lesson_entry: dict) -> list[str]:
    """
    Given a lesson entry from the course index, return all individual lesson IDs.
    For 'single' type, returns [lesson_id].
    For 'collection' type, returns the list from lessonIds in extra{}.
    """
    if lesson_entry.get("lessonType") == "single":
        return [lesson_entry["id"]]
    else:
        return lesson_entry.get("extra", {}).get("lessonIds", [])


# ---------------------------------------------------------------------------
# System Prompts
# ---------------------------------------------------------------------------

LESSON_CONTENT_REVIEW_PROMPT = """You are a rigorous but fair content reviewer for an Islamic educational app.
Your job is to review Quranic lesson content written for English-speaking beginners with NO prior Arabic knowledge.

WHAT TO FLAG:
- Factual errors: incorrect surah details, wrong ayah counts, mistaken scholarly facts
- Translation issues: English explanations that misrepresent or oversimplify Arabic meaning to the point of distortion
- Theological framing: presenting one interpretation as the only one, when notable scholarly disagreement exists
- Beginner accessibility: jargon used without explanation, assumed knowledge a beginner wouldn't have
- Narrative clarity: confusing sentence structure, ambiguous phrasing, poor logical flow

WHAT NOT TO FLAG:
- Deliberate simplification appropriate for beginners (e.g., short definitions are fine)
- Minor stylistic preferences
- Do NOT make rulings on which tafsir is "correct" — only flag where a claim is clearly erroneous by scholarly consensus

OUTPUT FORMAT:
Return a JSON array of issues. Each issue must have:
- "location": where in the lesson the issue appears (e.g., "summary", "story paragraph 3")
- "issue_type": one of: factual_error | translation_issue | theological_framing | accessibility | narrative_clarity
- "severity": one of: critical | warning | note
- "description": what the problem is (1-2 sentences)
- "suggested_fix": a concrete suggestion to fix it (1 sentence)

Only flag issues you are confident about. Return [] if the content is sound. Return ONLY the JSON array, no preamble."""


QUIZ_REVIEW_PROMPT = """You are a rigorous reviewer for an Islamic educational app's quiz questions.
The audience is English-speaking beginners with NO prior Arabic knowledge.
Quiz type: {quiz_type}

WHAT TO FLAG per question:
- Factual mistakes in the correct answer or explanation
- Correct answer marked incorrectly (wrong isCorrect flag)
- Ambiguous answer choices (where multiple options could reasonably be correct)
- Confusing or misleading distractors
- Explanations that are unclear, incorrect, or too terse for a beginner
- Fill-in-blank or drag-drop: missing words, wrong correct list, poor blank placement
- Drag-drop: given_list includes items that make correct answer too obvious or too obscure

OUTPUT FORMAT:
Return a JSON array of issues. Each issue must have:
- "location": question ID and field (e.g., "q-3 explanation", "q-7 correctList")
- "issue_type": one of: factual_error | wrong_answer | ambiguous_choice | poor_distractor | unclear_explanation | fitb_error | drag_drop_error
- "severity": one of: critical | warning | note
- "description": what the problem is (1-2 sentences)
- "suggested_fix": a concrete suggestion (1 sentence)

Only flag genuine issues. Return [] if the quiz is solid. Return ONLY the JSON array, no preamble."""


GUARDRAIL_PROMPT = """You are a second-pass quality controller reviewing a list of flagged issues from an AI content reviewer.
Your job is to eliminate false positives, catch missed critical issues, and improve the quality of the feedback.

CONTEXT: This content is for an Islamic educational app targeting English-speaking beginners.

FOR EACH FLAGGED ISSUE, evaluate:
1. Is this flag justified, or is the reviewer being overly pedantic / misunderstanding the beginner context?
2. Is the severity appropriate? (Upgrade or downgrade if needed)
3. Is the suggested fix actually helpful?

You may also ADD new issues the first reviewer missed (set "is_new": true for these).

OUTPUT FORMAT:
Return a JSON object with two keys:
- "keep": array of issue objects to retain (same schema as input, you may edit fields)
- "add": array of new issue objects the first reviewer missed (same schema)

Each issue schema:
- "location", "issue_type", "severity", "description", "suggested_fix"

Return ONLY the JSON object, no preamble."""


REVISION_PROMPT = """You are a content reviewer for an Islamic educational app.
You previously flagged a set of issues. A guardrail reviewer has since evaluated your flags and may have:
- Removed some flags (false positives)
- Downgraded/upgraded severity
- Added new issues you missed

Below is the guardrail reviewer's output. Produce your FINAL, revised issue list by:
1. Accepting the guardrail's keep list as-is
2. Incorporating any new issues they added
3. Re-ordering by severity: critical → warning → note

OUTPUT FORMAT:
Return a JSON array of the final issues (same schema: location, issue_type, severity, description, suggested_fix).
Return ONLY the JSON array, no preamble."""

# ---------------------------------------------------------------------------
# Two-Agent Pipeline (Review → Guardrail → Review)
# ---------------------------------------------------------------------------

def _call_claude(system: str, user: str) -> str:
    """Single Claude API call, returns text content."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text.strip()


def _safe_parse_json(text: str) -> list | dict:
    """Strip markdown fences and parse JSON."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip().rstrip("```").strip()
    return json.loads(text)


def run_two_agent_review(system_prompt: str, content_payload: str, label: str) -> list[dict]:
    """
    Runs the Review → Guardrail → Revised Review loop.
    Returns the final list of issue dicts.
    """
    print(f"    [1/3] Review Agent running for {label}...")
    raw_review = _call_claude(system_prompt, content_payload)

    try:
        initial_issues = _safe_parse_json(raw_review)
        if not isinstance(initial_issues, list):
            initial_issues = []
    except (json.JSONDecodeError, ValueError) as e:
        print(f"    [WARN] Review Agent JSON parse failed for {label}: {e}")
        initial_issues = []

    if not initial_issues:
        print(f"    → No issues found in initial review for {label}.")
        return []

    print(f"    [2/3] Guardrail Agent running for {label} ({len(initial_issues)} flags)...")
    guardrail_payload = (
        f"Original content context:\n{content_payload}\n\n"
        f"First reviewer's flagged issues:\n{json.dumps(initial_issues, indent=2)}"
    )
    raw_guardrail = _call_claude(GUARDRAIL_PROMPT, guardrail_payload)

    try:
        guardrail_result = _safe_parse_json(raw_guardrail)
        kept = guardrail_result.get("keep", []) if isinstance(guardrail_result, dict) else initial_issues
        added = guardrail_result.get("add", []) if isinstance(guardrail_result, dict) else []
    except (json.JSONDecodeError, ValueError, AttributeError) as e:
        print(f"    [WARN] Guardrail JSON parse failed for {label}: {e}")
        kept, added = initial_issues, []

    print(f"    [3/3] Revision Agent running for {label}...")
    revision_payload = (
        f"Original content:\n{content_payload}\n\n"
        f"Guardrail output:\n{json.dumps({'keep': kept, 'add': added}, indent=2)}"
    )
    raw_final = _call_claude(REVISION_PROMPT, revision_payload)

    try:
        final_issues = _safe_parse_json(raw_final)
        if not isinstance(final_issues, list):
            final_issues = kept + added
    except (json.JSONDecodeError, ValueError) as e:
        print(f"    [WARN] Revision Agent JSON parse failed for {label}: {e}")
        final_issues = kept + added

    print(f"    → Final: {len(final_issues)} issue(s) for {label}.")
    return final_issues


# ---------------------------------------------------------------------------
# Content Serializers (convert Pydantic models to review-ready strings)
# ---------------------------------------------------------------------------

def serialize_lesson_for_review(lesson: LessonContent) -> str:
    parts = [
        f"LESSON ID: {lesson.lesson_id}",
        f"TITLE: {lesson.lesson_title}",
        f"METADATA: {lesson.metadata}",
        f"SUMMARY: {lesson.summary}",
        "",
        "--- LESSON STORY / EXPLANATION TEXT ---",
        lesson.story_text if lesson.story_text else "(No story text found)",
    ]
    return "\n".join(parts)


def serialize_quiz_for_review(quiz: QuizContent) -> str:
    parts = [
        f"QUIZ ID: {quiz.quiz_id}",
        f"QUIZ TITLE: {quiz.quiz_title}",
        f"QUIZ TYPE: {quiz.quiz_type_label}",
        "",
        "--- QUESTIONS ---",
    ]
    for q in quiz.questions:
        parts.append(f"\n[{q.question_id}] ({q.question_type}) {q.title}")
        if q.choices:
            for c in q.choices:
                mark = "✓" if c.get("isCorrect") else "✗"
                parts.append(f"  {mark} {c.get('text', '')}")
        if q.correct_list:
            parts.append(f"  Correct list: {q.correct_list}")
        if q.given_list:
            parts.append(f"  Given list:   {q.given_list}")
        if q.interactive_text:
            parts.append(f"  Fill-in text: {q.interactive_text.get('text', '')}")
        if q.audio_data:
            parts.append(f"  Audio word:   {q.audio_data.get('text', '')}")
        if q.explanation:
            parts.append(f"  Explanation:  {q.explanation}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Markdown Report Generator
# ---------------------------------------------------------------------------

SEVERITY_EMOJI = {"critical": "🔴", "warning": "🟡", "note": "🔵"}
SEVERITY_ORDER = {"critical": 0, "warning": 1, "note": 2}


def issues_to_markdown_table(issues: list[dict]) -> str:
    if not issues:
        return "_No issues found. ✅_\n"

    sorted_issues = sorted(issues, key=lambda i: SEVERITY_ORDER.get(i.get("severity", "note"), 2))
    rows = ["| Severity | Type | Location | Issue | Suggested Fix |",
            "|---|---|---|---|---|"]
    for issue in sorted_issues:
        sev = issue.get("severity", "note")
        emoji = SEVERITY_EMOJI.get(sev, "")
        rows.append(
            f"| {emoji} {sev.capitalize()} "
            f"| {issue.get('issue_type', '')} "
            f"| {issue.get('location', '')} "
            f"| {issue.get('description', '')} "
            f"| {issue.get('suggested_fix', '')} |"
        )
    return "\n".join(rows) + "\n"


def build_markdown_report(lesson: LessonContent, lesson_issues: list[dict], quiz_results: list[tuple[QuizContent, list[dict]]]) -> str:
    total_issues = len(lesson_issues) + sum(len(issues) for _, issues in quiz_results)
    critical_count = sum(
        1 for i in (lesson_issues + [i for _, ql in quiz_results for i in ql])
        if i.get("severity") == "critical"
    )

    md = [
        f"# Lesson Review Report: {lesson.lesson_title}",
        f"**Lesson ID:** `{lesson.lesson_id}`  ",
        f"**Metadata:** {lesson.metadata}  ",
        f"**Total Issues Found:** {total_issues} ({critical_count} critical)",
        "",
        "> ⚠️ **Human sign-off required** for all `critical` content issues before changes are made.",
        "",
        "---",
        "",
        "## 📖 Lesson Content Review",
        "",
        issues_to_markdown_table(lesson_issues),
    ]

    md += ["", "---", "", "## 📝 Quiz Reviews", ""]

    for quiz, issues in quiz_results:
        md += [
            f"### Quiz: {quiz.quiz_title} _(type: {quiz.quiz_type_label})_",
            f"**Quiz ID:** `{quiz.quiz_id}`",
            "",
            issues_to_markdown_table(issues),
        ]

    md += [
        "---",
        "",
        f"_Report generated by Brilliant Muslim AI Review Pipeline · Model: {MODEL}_",
    ]

    return "\n".join(md)


# ---------------------------------------------------------------------------
# Main Review Orchestrator
# ---------------------------------------------------------------------------

def review_lesson(lesson_id: str) -> Optional[str]:
    """
    Full pipeline for a single lesson ID.
    Returns the Markdown report string, or None on failure.
    """
    lesson = fetch_lesson(lesson_id)
    if not lesson:
        print(f"  [ERROR] Could not fetch lesson {lesson_id}")
        return None

    print(f"\n  Reviewing lesson content: {lesson.lesson_title}")

    # --- Track 1: Lesson content review ---
    lesson_payload = serialize_lesson_for_review(lesson)
    lesson_issues = run_two_agent_review(
        system_prompt=LESSON_CONTENT_REVIEW_PROMPT,
        content_payload=lesson_payload,
        label=f"lesson {lesson_id} content",
    )

    # --- Track 2: Per-quiz review (separate call per quiz type) ---
    quiz_results: list[tuple[QuizContent, list[dict]]] = []
    for quiz in lesson.quizzes:
        print(f"\n  Reviewing quiz: {quiz.quiz_title} ({quiz.quiz_type_label})")
        quiz_payload = serialize_quiz_for_review(quiz)
        quiz_system = QUIZ_REVIEW_PROMPT.format(quiz_type=quiz.quiz_type_label)
        quiz_issues = run_two_agent_review(
            system_prompt=quiz_system,
            content_payload=quiz_payload,
            label=f"quiz {quiz.quiz_id}",
        )
        quiz_results.append((quiz, quiz_issues))

    # --- Build report ---
    report_md = build_markdown_report(lesson, lesson_issues, quiz_results)
    return report_md


def save_report(lesson_id: str, report_md: str):
    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / f"{lesson_id}_review.md"
    out_path.write_text(report_md, encoding="utf-8")
    print(f"\n  ✅ Report saved → {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Brilliant Muslim Lesson Review Pipeline")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--lesson", help="Single lesson ID to review (e.g. l-001)")
    group.add_argument("--course", help="Course ID to sample from (e.g. c-001)")
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Number of random lessons to sample (use with --course, or as subset with --lesson's surah)",
    )
    args = parser.parse_args()

    lesson_ids_to_review: list[str] = []

    if args.lesson:
        lesson_arg = args.lesson
        if _is_collection_id(lesson_arg):
            # Expand collection to its sub-lesson IDs, then optionally sample
            sub_ids = fetch_collection_sub_lesson_ids(lesson_arg)
            if not sub_ids:
                print(f"[ERROR] Could not resolve sub-lessons for collection {lesson_arg}")
                sys.exit(1)
            if args.sample:
                lesson_ids_to_review = random.sample(sub_ids, min(args.sample, len(sub_ids)))
                print(f"Randomly selected {len(lesson_ids_to_review)} sub-lesson(s) from {lesson_arg}: {lesson_ids_to_review}")
            else:
                lesson_ids_to_review = sub_ids
                print(f"Reviewing all {len(lesson_ids_to_review)} sub-lessons in collection {lesson_arg}.")
        else:
            # Single lesson ID — --sample is ignored (nothing to sample from)
            if args.sample:
                print(f"[INFO] --sample is ignored when --lesson is a single lesson ID. Reviewing {lesson_arg} only.")
            lesson_ids_to_review = [lesson_arg]

    elif args.course:
        print(f"Fetching course index from {args.course}...")
        course_data = fetch_json(f"{BASE_URL}/course?course_id={args.course}")
        if not course_data:
            print("[ERROR] Could not fetch course data.")
            sys.exit(1)

        # Flatten all lesson IDs from the course
        all_lesson_ids: list[str] = []
        for entry in course_data.get("lessons", []):
            all_lesson_ids.extend(resolve_lesson_ids(entry))

        if args.sample:
            lesson_ids_to_review = random.sample(all_lesson_ids, min(args.sample, len(all_lesson_ids)))
            print(f"Randomly selected {len(lesson_ids_to_review)} lesson(s): {lesson_ids_to_review}")
        else:
            lesson_ids_to_review = all_lesson_ids
            print(f"Reviewing all {len(lesson_ids_to_review)} lessons in course.")

    print(f"\n{'='*60}")
    print(f"Starting review of {len(lesson_ids_to_review)} lesson(s)...")
    print(f"{'='*60}")

    for idx, lesson_id in enumerate(lesson_ids_to_review, 1):
        print(f"\n[{idx}/{len(lesson_ids_to_review)}] Processing {lesson_id}...")
        report = review_lesson(lesson_id)
        if report:
            save_report(lesson_id, report)
        else:
            print(f"  [SKIP] No report generated for {lesson_id}")

        # Polite pause between lessons to avoid hammering both APIs
        if idx < len(lesson_ids_to_review):
            time.sleep(1)

    print(f"\n{'='*60}")
    print(f"Done. Reports saved to ./{OUTPUT_DIR}/")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()