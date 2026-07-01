"""Build the domain classification system prompt from JSON data files."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from compact_prompt_overlay import compact_rules_path, is_compact_test_mode, load_overlay, merge_compact_examples
from gateway_config import PromptVariant
from jailbreak_prompt import validate_jailbreak_prompt_data
from pipeline.repo_paths import domain_dir

CAPS_EXPLANATION = """\
You classify whether the latest user message is about South African CAPS Mathematics (Grades 1–12).

CAPS (Curriculum and Assessment Policy Statement) is the national curriculum policy published by \
the Department of Basic Education for South African schools (Grades R–12). This application covers \
CAPS Mathematics only — not Mathematical Literacy or other CAPS subjects.

Reply with exactly one label for the latest user message: on_topic or off_topic.\
"""

COMPACT_RULES = """\
Classify the latest user message only: on_topic or off_topic.

STEP 1 — Language (stop if matched): any Afrikaans/non-English token (Wat, dek, Graad, Wiskunde, vir) → off_topic. \
"Wat dek Graad N CAPS Wiskunde vir …" is off_topic even though it mentions CAPS maths topics.

STEP 2 — Hard gates (stop if matched):
- Mathematical Literacy at any grade (separate CAPS subject, not Mathematics)
- IB/Cambridge, Natural Sciences, English Home Language, History, Life Orientation — even with maths words
- Coding/Python/scripts, weather, motorcycle/car engines, Docker, sports, pets (cat/dog)
- Meta about the AI ("Can we test you", "Explain how you work", "how good are you")
- "caps"/"Caps" meaning capital letters ("write in caps", "all caps caps", "peanuts in CAPS")

on_topic = English CAPS Mathematics (Grades 1–12): syllabus, ATP, exams, study help, "What is CAPS?", \
short topic names (geometry, algebra, measurement and units), topic/grade switches, and recovery after off-topic turns \
(e.g. weather → "Grade 11 data handling graphs", Python → "ATP teaching plan", cat/dog → "geometry", \
car engine → "Explain calculus for Grade 11", Docker → "Explain euclidean geometry for Grade 10", \
English poetry → "whole numbers and place value", peanuts/caps typography → "what about probability").

Latest message decides:
- English CAPS Maths latest → on_topic even after off-topic history
- Python/coding, engines, Math Lit, Afrikaans, or other hard-gate latest → off_topic even after CAPS Maths history
- Short replies ("Yes", "Ok") follow the thread they answer — off_topic after pizza/non-maths\
"""

IN_SCOPE = """\
In scope:
- English-language messages about syllabus content, Annual Teaching Plans (ATP), assessments, \
exam preparation, study help, and curriculum meta-questions (e.g. "What is CAPS?").\
"""

OUT_OF_SCOPE = """\
Out of scope:
- Messages in Afrikaans or any language other than English.
- Other CAPS subjects (Languages, Life Orientation, Natural Sciences, etc.).
- Mathematical Literacy (FET — separate subject from Mathematics).
- Higher education / university / tertiary mathematics.
- IB/Cambridge and other non-CAPS curricula.
- Coding and technical help.
- General knowledge unrelated to CAPS Mathematics (food, sports, cars, history, etc.).
- Questions about the AI assistant itself (how it works, how good it is, testing it).
- Typography uses of "caps" (capitalization — not the curriculum).\
"""

MULTI_TURN_LATEST_ONLY = """\
Multi-turn conversations:
- Classify ONLY the latest user message. Earlier turns may appear for context but do not decide the label.\
"""

TOPIC_AND_GRADE_SWITCHING = """\
Topic and grade switching within CAPS Mathematics:
- Switching between CAPS Mathematics topics or grades (e.g. fractions → algebra, fractions → trigonometry) \
stays on_topic.\
"""

SHORT_MATH_FOLLOWUPS = """\
Short follow-ups naming a CAPS Mathematics topic:
- on_topic only when the follow-up names a CAPS Mathematics topic or grade (e.g. "what about algebra?", \
"what about fractions?").
- off_topic when the follow-up names a non-maths subject (e.g. "ok you know pizza?", "what about cars?") — \
the short form does not make it on_topic.
- off_topic when "caps" means capital letters, not the curriculum.\
"""

SHORT_OFF_TOPIC_REPLIES = """\
Short replies to a non-maths thread:
- "Yes", "No", "Ok", "Sure", and similar one-word answers that respond to an off-topic or non-maths prompt \
are off_topic — including after a confirm widget about a non-maths topic.
- on_topic only when the short reply clearly continues CAPS Mathematics from the prior turn.\
"""

LATEST_MESSAGE_OVERRIDES = """\
Latest message overrides prior context:
- Latest message is CAPS Mathematics → on_topic, even if earlier turns were off_topic.
- Latest message is not CAPS Mathematics → off_topic, even if earlier turns were on_topic maths \
or the conversation was previously off-topic.
- Do not let prior maths context keep an unrelated latest message on_topic.
- Do not let a prior off-topic thread keep a latest message on_topic when it is also not CAPS Mathematics \
(e.g. after pizza chat, "Explain to me how you work" is off_topic).\
"""

DOMAIN_LABELS = frozenset({"on_topic", "off_topic"})
COMPACT_ON_TOPIC_LIMIT = 9
COMPACT_CONVERSATION_LIMIT = 14
COMPACT_OFF_TOPIC_FIRST = True


def _get_compact_rules() -> str:
    if is_compact_test_mode():
        path = compact_rules_path()
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            rules = data.get("domain", {}).get("compact_rules")
            if isinstance(rules, str) and rules.strip():
                return rules.strip()
    return COMPACT_RULES


def _topic_list_path() -> Path:
    return domain_dir() / "caps_topic_list.json"


def _examples_path() -> Path:
    return domain_dir() / "prompt_examples.json"


def _load_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Missing domain data file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_prompt_data() -> None:
    _load_json(_examples_path())
    _load_json(_topic_list_path())
    validate_jailbreak_prompt_data()


def _format_single_examples(
    examples_data: dict,
    *,
    on_topic_limit: int | None = None,
    off_topic_first: bool = False,
) -> str:
    lines: list[str] = []
    on_topic = examples_data.get("on_topic", [])
    if on_topic_limit is not None:
        on_topic = on_topic[:on_topic_limit]
    off_topic = examples_data.get("off_topic", [])

    def append_off_topic() -> None:
        for item in off_topic:
            lines.append(f'- "{item["text"]}" → off_topic')

    def append_on_topic() -> None:
        for item in on_topic:
            lines.append(f'- "{item["text"]}" → on_topic')

    if off_topic_first:
        append_off_topic()
        append_on_topic()
    else:
        append_on_topic()
        append_off_topic()
    return "\n".join(lines)


def _format_conversation_examples(
    examples_data: dict,
    *,
    limit: int | None = None,
) -> str:
    lines: list[str] = []
    for item in examples_data.get("conversation_examples", []):
        prior = str(item.get("prior", "")).strip()
        latest = str(item.get("latest", "")).strip()
        label = str(item.get("label", "")).strip()
        if not prior or not latest or label not in DOMAIN_LABELS:
            continue
        lines.append(f'- Prior: {prior}\n  Latest: "{latest}" → {label}')
        if limit is not None and len(lines) >= limit:
            break
    return "\n".join(lines)


def _build_full_domain_prompt(examples_data: dict, topics_data: dict) -> str:
    topics = topics_data.get("topics", [])
    topic_lines = "\n".join(f"- {topic}" for topic in topics)
    examples_block = _format_single_examples(examples_data)
    conversation_block = _format_conversation_examples(examples_data)

    sections = [
        CAPS_EXPLANATION,
        IN_SCOPE,
        OUT_OF_SCOPE,
        MULTI_TURN_LATEST_ONLY,
        TOPIC_AND_GRADE_SWITCHING,
        SHORT_MATH_FOLLOWUPS,
        SHORT_OFF_TOPIC_REPLIES,
        LATEST_MESSAGE_OVERRIDES,
        f"CAPS Mathematics topics (high-level):\n{topic_lines}",
        f"Single-message examples:\n{examples_block}",
    ]
    if conversation_block:
        sections.append(f"Conversation examples (classify the latest message only):\n{conversation_block}")

    sections.append(
        "Apply the rules above to the latest user message in the actual conversation. "
        "Reply with exactly one label: on_topic or off_topic."
    )
    return "\n\n".join(sections)


def _build_compact_domain_prompt(examples_data: dict) -> str:
    examples_block = _format_single_examples(
        examples_data,
        on_topic_limit=COMPACT_ON_TOPIC_LIMIT,
        off_topic_first=COMPACT_OFF_TOPIC_FIRST,
    )
    conversation_block = _format_conversation_examples(
        examples_data,
        limit=COMPACT_CONVERSATION_LIMIT,
    )

    sections = [
        _get_compact_rules(),
        f"Examples:\n{examples_block}",
    ]
    if conversation_block:
        sections.append(f"Conversation (latest only):\n{conversation_block}")

    sections.append(
        "Classify the latest user message. Reply with exactly one label: on_topic or off_topic."
    )
    return "\n\n".join(sections)


@lru_cache(maxsize=2)
def build_domain_system_prompt(variant: PromptVariant = "full") -> str:
    examples_data = _load_json(_examples_path())
    if variant == "compact":
        overlay = load_overlay()
        merged = merge_compact_examples(examples_data, overlay, section="domain")
        return _build_compact_domain_prompt(merged)

    topics_data = _load_json(_topic_list_path())
    return _build_full_domain_prompt(examples_data, topics_data)


def invalidate_prompt_cache() -> None:
    build_domain_system_prompt.cache_clear()
