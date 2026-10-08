"""AI executive summary built ONLY from verified facts, with a number check.

Output is split into three clearly separated parts:
  confirmed_facts       - restated from the verified facts (numbers are checked)
  possible_explanations - hypotheses, always worded as such, never a stated root cause
  recommendations       - suggested leadership actions
"""
from __future__ import annotations

import json
import re

from op_provider import AIError, get_provider

PROMPT = """You are an operations analyst writing for a senior executive.

STRICT RULES
1. Use ONLY the VERIFIED FACTS below. Do not use outside knowledge about the organisation.
2. Every number you write must appear in the facts exactly (same rounding). Never calculate new numbers.
3. "confirmed_facts" may only restate facts. Mention the selection and period.
4. "possible_explanations" are hypotheses. Start each with "Possibly" or "May be" and name the
   supporting metric from the facts. NEVER state a root cause as certain. If the facts do not
   suggest an explanation, return an empty list.
5. "recommendations" are practical leadership actions linked to a specific KPI and location/process.
6. If data coverage is incomplete or there are data gaps, say so in confirmed_facts.
7. Plain business English, short sentences, no markdown.

Return JSON exactly in this shape:
{{"headline": "one sentence",
  "confirmed_facts": ["...", "..."],
  "possible_explanations": [{{"text": "...", "supporting_metrics": ["..."]}}],
  "recommendations": [{{"action": "...", "kpi": "...", "where": "..."}}]}}
Maximum: 5 confirmed facts, 3 possible explanations, 3 recommendations.

VERIFIED FACTS (JSON):
{facts}
"""

_NUM = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set[float]:
    out = set()
    for m in _NUM.findall(text or ""):
        try:
            out.add(round(float(m.replace(",", "")), 2))
        except ValueError:
            pass
    return out


def unverified_numbers(summary: dict, facts: dict) -> list[float]:
    """Numbers the AI wrote in confirmed facts / headline that do not exist in the facts."""
    allowed = _numbers(json.dumps(facts, default=str))
    # derived differences (e.g. "down 1.2 points") are allowed if both ends are present
    written = _numbers(" ".join([summary.get("headline", "")] + list(summary.get("confirmed_facts", []))))
    allowed_diffs = {round(abs(a - b), 1) for a in allowed for b in allowed if abs(a - b) < 100} if len(allowed) < 400 else set()
    return sorted(n for n in written if n not in allowed and round(n, 1) not in allowed_diffs)


def _clean(summary: dict) -> dict:
    def as_list(v):
        return v if isinstance(v, list) else ([] if v in (None, "") else [v])
    expl = []
    for e in as_list(summary.get("possible_explanations"))[:3]:
        if isinstance(e, str):
            e = {"text": e, "supporting_metrics": []}
        txt = str(e.get("text", "")).strip()
        if txt and not txt.lower().startswith(("possibly", "may be", "maybe", "this may", "it may", "could")):
            txt = "Possibly: " + txt
        if txt:
            expl.append({"text": txt, "supporting_metrics": [str(m) for m in as_list(e.get("supporting_metrics"))]})
    recs = []
    for r in as_list(summary.get("recommendations"))[:3]:
        if isinstance(r, str):
            r = {"action": r}
        if r.get("action"):
            recs.append({"action": str(r["action"]), "kpi": str(r.get("kpi", "") or ""), "where": str(r.get("where", "") or "")})
    return {"headline": str(summary.get("headline", "")).strip(),
            "confirmed_facts": [str(x) for x in as_list(summary.get("confirmed_facts"))][:5],
            "possible_explanations": expl, "recommendations": recs}


def executive_summary(facts: dict, provider=None) -> dict:
    """Returns the cleaned summary plus 'unverified_numbers', 'provider' and 'model'."""
    provider = provider or get_provider()
    raw = provider.generate_json(PROMPT.format(facts=json.dumps(facts, indent=1, default=str)))
    if not isinstance(raw, dict):
        raise AIError("The AI reply was not in the expected format. Please try again.")
    out = _clean(raw)
    out["unverified_numbers"] = unverified_numbers(out, facts)
    out["provider"], out["model"] = provider.name, provider.model
    return out
