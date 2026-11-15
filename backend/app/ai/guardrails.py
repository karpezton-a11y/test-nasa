"""Conservative deterministic validation of all user-visible LLM output."""
import json
import re
import unicodedata

from ..core_schemas import LlmOutput
from ..advanced_schemas import INTERACTION_GUARDRAIL

BANNED_CAUSAL_PHRASES = ["cause", "causes", "caused", "causing", "because of", "due to", "leads to",
                        "lead to", "results in", "resulted in", "driven by", "responsible for", "effect of"]
NUMERIC_LITERAL = r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?"
NUMBER = re.compile(r"(?<![\w.])" + NUMERIC_LITERAL + r"(?!\w|\.\d)")
# Detect alternative spellings/operators as claims too, then compare them with
# the exact code-formatted relation. An allowed number alone is insufficient.
P_CLAIM = re.compile(r"\bp(?:[-_\s]+value)?\s*(?:(?:is|of|equals)\s+)?"
                     r"([<>=!≤≥≠≈~:]{0,2}|greater\s+than|less\s+than|at\s+least|at\s+most|"
                     r"not\s+equal\s+to|above|below|approximately)\s*("
                     + NUMERIC_LITERAL + r")(?!\w|\.\d)")


def normalize(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    text = re.sub("[\u2010-\u2015\u2212]", "-", text)
    return re.sub(r"\s+", " ", text).strip()


def verbatim_fact_strings(facts: dict) -> list[str]:
    """Sentences the model is told to copy word for word. Their wording is ours, so word-level checks
    (number words, the word "significant") must not fire on them; numbers in them are still checked."""
    out = [facts.get("aod_caveat", ""), INTERACTION_GUARDRAIL]
    for item in facts["items"]:
        out.append(item.get("significance_statement") or "")
        out.extend(item.get("limitations", []))
    return sorted({normalize(x) for x in out if x}, key=len, reverse=True)


def strip_verbatim(normalized_text: str, facts: dict) -> str:
    for phrase in verbatim_fact_strings(facts):
        normalized_text = normalized_text.replace(phrase, " ")
    return normalized_text


def check(output: LlmOutput, facts: dict) -> list[str]:
    visible = " ".join([output.text, *output.key_points, *output.caveats])
    normalized = normalize(visible)
    own_words = strip_verbatim(normalized, facts)   # what the model wrote itself
    issues = []
    if len(visible.split()) > 120: issues.append("word_limit")
    number_words = r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion|trillion|dozen|half|quarter|double|twice|thrice)\b"
    if re.search(number_words, own_words): issues.append("unformatted_number")
    for phrase in BANNED_CAUSAL_PHRASES:
        if re.search(r"\b" + re.escape(phrase).replace(r"\ ", r"[\s-]+") + r"\b", own_words):
            issues.append("causal_language"); break
    # Compare lexical tokens, never float equality: 0.02 cannot replace 0.021.
    allowed = set(NUMBER.findall(normalize(json.dumps(facts, ensure_ascii=False))))
    tokens = NUMBER.findall(normalized)
    # A token occurring in a year/unit must not be substituted as a p-value.
    p_claims = P_CLAIM.findall(normalized)
    p_facts = set(P_CLAIM.findall(normalize(json.dumps(facts, ensure_ascii=False))))
    if any(claim not in p_facts for claim in p_claims): issues.append("p_value_mismatch")
    if any(n not in allowed for n in tokens + [n for text in output.numbers_used for n in NUMBER.findall(normalize(text))]):
        issues.append("unsupported_number")
    if any(n not in set(NUMBER.findall(normalize(" ".join(output.numbers_used)))) for n in tokens):
        issues.append("numbers_used_incomplete")
    statements = [r["significance_statement"] for r in facts["items"] if r["kind"] == "trend"]
    if any(normalize(s) not in normalize(output.text) for s in statements):
        issues.append("significance_mismatch")
    remainder = own_words
    if re.search(r"\bsignifican(?:t|ce)\b", remainder):
        issues.append("significance_mismatch")
    if any(i.get("significant") is False for i in facts["items"]):
        if re.search(r"\b(?:increasing|increased|decreasing|decreased|rose|fell)\b", remainder):
            issues.append("non_significant_direction")
    limits = [lim for item in facts["items"] for lim in item["limitations"]]
    if not any(normalize(lim) in normalized for lim in limits): issues.append("limitation_missing")
    if any(i["kind"] == "interaction" for i in facts["items"]) and INTERACTION_GUARDRAIL not in output.text:
        issues.append("interaction_guardrail_missing")
    if "pm2.5" in normalized:
        remaining_pm = normalized.replace(normalize(facts["aod_caveat"]), "")
        if "pm2.5" in remaining_pm: issues.append("aod_pm25_equivalence")
    # prevent untrusted metadata or output from becoming active HTML in downstream UIs
    if (re.search(r"<[^>]*>", visible)
            or re.search(r"(?:https?|javascript|data)\s*:", normalized)
            or re.search(r"!?\[[^\]]*\]\s*(?:\([^)]*\)|\[[^\]]*\])", normalized)):
        issues.append("markup")
    return sorted(set(issues))
