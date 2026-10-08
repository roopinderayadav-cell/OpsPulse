"""AI provider layer.  Gemini first; other providers plug in by adding a class
with the same ``generate_json`` method - nothing else in the app changes.

The AI never calculates official numbers.  It only writes commentary from the
verified facts the KPI engine hands it."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass

from opspulse import config


class AIError(Exception):
    """Raised with a friendly message whenever the AI cannot answer."""


@dataclass
class AIStatus:
    enabled: bool
    provider: str
    model: str
    reason: str = ""


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str):
        self.model = model
        self._key = api_key
        self._client = None

    def _c(self):
        if self._client is None:
            try:
                from google import genai
            except ImportError as e:         # pragma: no cover - dependency missing
                raise AIError("The google-genai package is not installed.") from e
            self._client = genai.Client(api_key=self._key)
        return self._client

    def generate_json(self, prompt: str, max_tokens: int = 1500) -> dict:
        from google.genai import types

        def call(thinking: bool):
            cfg = dict(temperature=0.2, max_output_tokens=max_tokens + 1024,
                       response_mime_type="application/json")
            if thinking:
                cfg["thinking_config"] = types.ThinkingConfig(thinking_level="low")
            r = self._c().models.generate_content(model=self.model, contents=[prompt],
                                                  config=types.GenerateContentConfig(**cfg))
            return (r.text or "").strip()

        def run():
            try:
                return call(True)
            except Exception as e:           # some models do not accept thinking options
                if "thinking" in str(e).lower():
                    return call(False)
                raise

        raw = _retry(run)
        return parse_json(raw)


def parse_json(raw: str) -> dict:
    txt = raw.strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        txt = txt[txt.find("{"):]
    start, end = txt.find("{"), txt.rfind("}")
    if start < 0 or end < 0:
        raise AIError("The AI reply was not in the expected format. Please try again.")
    try:
        return json.loads(txt[start:end + 1])
    except json.JSONDecodeError as e:
        raise AIError("The AI reply was not in the expected format. Please try again.") from e


def _retry(fn):
    last = None
    for attempt in range(2):
        try:
            return fn()
        except Exception as e:               # noqa: BLE001
            last = e
            low = str(e).lower()
            if attempt == 0 and any(k in low for k in ("429", "503", "overloaded", "unavailable", "resource_exhausted")):
                time.sleep(2)
                continue
            break
    raise AIError(friendly(last))


def friendly(e: Exception | None) -> str:
    low = str(e).lower()
    if any(k in low for k in ("api key", "api_key", "401", "403", "permission")):
        return "The AI key was rejected. Check GEMINI_API_KEY in Streamlit Secrets."
    if any(k in low for k in ("429", "quota", "resource_exhausted")):
        return "The AI quota is used up for now. Verified KPI results are unaffected; try again later."
    if "not found" in low or "404" in low:
        return "The configured AI model was not found. Check GEMINI_MODEL in Streamlit Secrets."
    return "The AI service is unavailable right now. Verified KPI results are unaffected."


def status() -> AIStatus:
    if (config.secret("AI_PROVIDER", "auto") or "auto").lower() == "off":
        return AIStatus(False, "off", "", "AI is switched off (AI_PROVIDER = off).")
    if not config.secret("GEMINI_API_KEY"):
        return AIStatus(False, "none", "", "No GEMINI_API_KEY in Streamlit Secrets.")
    return AIStatus(True, "gemini", config.secret("GEMINI_MODEL", config.DEFAULT_GEMINI_MODEL))


def get_provider():
    st = status()
    if not st.enabled:
        raise AIError(st.reason)
    return GeminiProvider(config.secret("GEMINI_API_KEY"), st.model)
