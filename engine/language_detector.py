"""
language_detector.py
Detects the primary language of a conversation message or full session.
Handles the Hinglish edge case (Hindi semantics in Latin/Roman script)
which langdetect consistently misidentifies as Tagalog, Indonesian,
Somali, Afrikaans, Estonian etc.

Design note on langdetect reliability for Hinglish:
  langdetect returns arbitrary non-South-Asian codes for Hinglish text
  because Hinglish has no ISO 639 code. Relying on specific wrong-codes
  ('tl', 'so') is fragile — observed codes include 'id', 'af', 'et',
  'sl', 'tl', 'so', 'ms'. The reliable signal is:
    script == Latin  AND  HINGLISH_MARKERS ratio > threshold
  langdetect is still used to distinguish real English from Hinglish
  (English has a near-zero marker ratio) and to identify regional scripts.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langdetect import detect as _ld_detect, LangDetectException
from langdetect import DetectorFactory

# Fix langdetect's random seed for reproducible results
DetectorFactory.seed = 0

# Allow running this file directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ---------------------------------------------------------------------------
# Unicode script ranges (inclusive)
# ---------------------------------------------------------------------------
_DEVANAGARI_RANGE = (0x0900, 0x097F)
_TAMIL_RANGE      = (0x0B80, 0x0BFF)
_BENGALI_RANGE    = (0x0980, 0x09FF)
_GUJARATI_RANGE   = (0x0A80, 0x0AFF)

# ---------------------------------------------------------------------------
# Langdetect codes that reliably map to real South-Asian / world languages
# (i.e., NOT Hinglish masquerading as something else)
# ---------------------------------------------------------------------------
_LD_LANG_MAP: dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "ta": "Tamil",
    "bn": "Bengali",
    "gu": "Gujarati",
    "pa": "Punjabi",
    "te": "Telugu",
    "mr": "Marathi",
    "ml": "Malayalam",
    "kn": "Kannada",
    "ur": "Urdu",
}

# Automated platform messages — filtered out before language analysis
_AUTOMATED_PATTERNS = re.compile(
    r"This is an automated message"
    r"|Welcome to Astrotalk"
    r"|Below are my details"
    r"|USER ended the chat"
    r"|\[kundli\]"
    r"|\[image\]",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Return types
# ---------------------------------------------------------------------------

@dataclass
class LanguageResult:
    """Language detection result for a single text chunk."""
    primary_language:     str    # Human-readable: "Hinglish", "English", "Hindi" …
    is_hinglish:          bool
    hinglish_confidence:  float  # 0.0–1.0 — ratio of HINGLISH_MARKERS in tokens
    detected_by_langdetect: str  # Raw langdetect output code
    script:               str    # "Devanagari" | "Tamil" | "Bengali" | "Latin" | "Mixed"


@dataclass
class SessionLanguage:
    """Aggregated language profile for a full session."""
    dominant_language:   str
    languages_detected:  dict[str, int]   # language → message count
    has_hinglish:        bool
    has_devanagari:      bool
    has_regional:        bool             # Tamil/Bengali/Telugu/Marathi/Gujarati
    sample_size:         int


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class LanguageDetector:
    """
    Detects language and Hinglish content in AstroTalk conversation messages.

    Usage
    -----
    detector = LanguageDetector()
    result   = detector.detect("mera naam kya hai aur kaise hoga mera future")
    # LanguageResult(primary_language='Hinglish', is_hinglish=True, …)

    session_lang = detector.analyse_session(session["messages"])
    instruction  = detector.get_language_instruction(session_lang)
    """

    # ------------------------------------------------------------------
    # Hinglish marker vocabulary — 80+ high-frequency Hindi words
    # that commonly appear in Roman/Latin script in AstroTalk chats.
    # Astro terms are excluded (see ASTRO_TERMS below).
    # ------------------------------------------------------------------
    HINGLISH_MARKERS: frozenset[str] = frozenset({
        # Core pronouns
        "mera", "meri", "mere", "mujhe", "mujhko",
        "tera", "teri", "tere", "tumhara", "tumhari", "tumhe", "tumko",
        "aap", "aapka", "aapki", "aapke", "aapko", "aapse", "aapne",
        "main", "hum", "hamare", "hamari",
        "woh", "uska", "uski", "uske", "unka", "unki",
        "yeh", "iska", "iski", "iske", "yahan",
        # Common verbs (base, infinitive -na, present -te/-ti, imperative)
        "hai", "hain", "tha", "thi", "the", "hoga", "hogi", "honge",
        "hua", "hui", "hue", "ho", "hoon", "hun",
        "kar", "karo", "karna", "karte", "karti", "karta", "karein",
        "jao", "jaana", "jaate", "jaati", "gaya", "gayi",
        "aao", "aana", "aate", "aati", "aaya", "aayi",
        "raho", "rehna", "rehte", "rehti",
        "karo", "karna", "karenge",
        "batao", "batana", "bolo", "bolna", "suno",
        "dekho", "dekhna", "lelo", "lena", "dedo", "dena",
        "milna", "milne", "milo", "milenge",
        "sona", "soona", "khelna", "padhna",
        "bolna", "bolne", "sunna",
        # Question words
        "kya", "kaisa", "kaisi", "kaise", "kitna", "kitni",
        "kab", "kahan", "kaun", "kyun", "kyunki",
        # Negation
        "nahi", "nahin", "mat",
        # Common adverbs / connectors
        "bahut", "accha", "achha", "theek", "bilkul",
        "bhi", "toh", "phir", "lekin", "aur", "ya",
        "abhi", "baad", "pehle", "bad", "kal", "aaj",
        "matlab", "samjhe", "matlab",
        "sirf", "bas", "zaroor", "zaruri",
        # Social / address words
        "yaar", "bhai", "didi", "ji", "bete", "jaan",
        # Common nouns that appear in NSFW / personal context
        "pyaar", "mohabbat", "zindagi", "dil", "baat",
        "kaam", "paisa", "ghar", "raat", "din",
        # Hinglish past-tense markers
        "diya", "liya", "kiya", "kia",
        # Future-tense markers
        "aunga", "aaunga", "jaaunga", "karunga", "karungi",
        # Filler / connector words common in Hinglish chat
        "iske", "uske", "jo", "jab",
    })

    # Astrological terms that should NOT count as Hinglish markers
    ASTRO_TERMS: frozenset[str] = frozenset({
        "kundali", "rashi", "nakshatra", "lagna", "graha",
        "shani", "mangal", "guru", "shukra", "budh",
        "surya", "chandra", "rahu", "ketu",
        "dasha", "mahadasha", "antardasha",
        "gochar", "sade", "saati", "varshphal",
    })

    # Marker ratio above which Latin-script text is classified as Hinglish
    HINGLISH_THRESHOLD: float = 0.08

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, text: str) -> LanguageResult:
        """
        Detect language for a single text string.

        Detection pipeline
        ------------------
        1. Detect script via Unicode range scan.
        2. If Devanagari/Tamil/Bengali/Gujarati — return immediately;
           langdetect is reliable for these scripts.
        3. For Latin-script text: compute Hinglish marker ratio.
        4. If ratio > HINGLISH_THRESHOLD → Hinglish
           (regardless of what langdetect returns — it is unreliable
           for Hinglish, returning id/af/tl/so/et/sl etc.)
        5. Otherwise map langdetect output to a human-readable name.
        """
        if not text or not text.strip():
            return LanguageResult(
                primary_language="Unknown",
                is_hinglish=False,
                hinglish_confidence=0.0,
                detected_by_langdetect="",
                script="Latin",
            )

        script = self.detect_script(text)

        # Script-based fast paths — langdetect is reliable here
        if script == "Devanagari":
            return LanguageResult(
                primary_language="Hindi",
                is_hinglish=False,
                hinglish_confidence=0.0,
                detected_by_langdetect=self._safe_langdetect(text),
                script="Devanagari",
            )
        if script == "Tamil":
            return LanguageResult(
                primary_language="Tamil",
                is_hinglish=False,
                hinglish_confidence=0.0,
                detected_by_langdetect=self._safe_langdetect(text),
                script="Tamil",
            )
        if script == "Bengali":
            return LanguageResult(
                primary_language="Bengali",
                is_hinglish=False,
                hinglish_confidence=0.0,
                detected_by_langdetect=self._safe_langdetect(text),
                script="Bengali",
            )
        if script == "Gujarati":
            return LanguageResult(
                primary_language="Gujarati",
                is_hinglish=False,
                hinglish_confidence=0.0,
                detected_by_langdetect=self._safe_langdetect(text),
                script="Gujarati",
            )

        # Latin / Mixed script — Hinglish heuristic
        ld_code          = self._safe_langdetect(text)
        marker_ratio     = self._hinglish_marker_ratio(text)
        is_hinglish      = marker_ratio > self.HINGLISH_THRESHOLD

        # Step 5: langdetect says "hi" but script is Latin → Hinglish
        if ld_code == "hi" and script == "Latin":
            is_hinglish = True

        if is_hinglish:
            primary = "Hinglish"
        else:
            # Map langdetect code to friendly name.
            # For Latin-script text, fall back to "English" rather than
            # "Unknown" — unknown-code Latin messages are at minimum
            # code-switched English in AstroTalk sessions.
            # "Unknown" is reserved for empty / sub-3-char / non-Latin input.
            if ld_code in _LD_LANG_MAP:
                primary = _LD_LANG_MAP[ld_code]
            elif script == "Latin":
                primary = "English"
            elif script == "Mixed":
                primary = "Mixed"
            else:
                primary = "Unknown"

        return LanguageResult(
            primary_language=primary,
            is_hinglish=is_hinglish,
            hinglish_confidence=round(marker_ratio, 4),
            detected_by_langdetect=ld_code,
            script=script,
        )

    def analyse_session(
        self, messages: list[dict[str, Any]]
    ) -> SessionLanguage:
        """
        Derive the language profile of a full session.

        Filters automated platform messages, then samples up to 30
        messages (first 10 + middle 10 + last 10) for efficiency.
        """
        # Filter automated messages
        real_msgs = [
            m for m in messages
            if not _AUTOMATED_PATTERNS.search(m.get("message", ""))
            and m.get("message", "").strip()
        ]

        if not real_msgs:
            return SessionLanguage(
                dominant_language="Unknown",
                languages_detected={},
                has_hinglish=False,
                has_devanagari=False,
                has_regional=False,
                sample_size=0,
            )

        sample = self._sample_messages(real_msgs, max_total=30)

        lang_counts: Counter[str] = Counter()
        has_hinglish   = False
        has_devanagari = False
        has_regional   = False

        regional_langs = {"Tamil", "Bengali", "Telugu", "Marathi", "Gujarati"}

        for msg in sample:
            result = self.detect(msg.get("message", ""))
            lang_counts[result.primary_language] += 1
            if result.is_hinglish:
                has_hinglish = True
            if result.script == "Devanagari":
                has_devanagari = True
            if result.primary_language in regional_langs:
                has_regional = True

        # Resolve dominant language with priority rules.
        #
        # Background: Fix 1 promotes short Latin-script messages whose
        # langdetect code isn't in _LD_LANG_MAP to "English". This inflates
        # the English count in Hinglish sessions because short greetings,
        # single-word replies, and Roman-Hinglish messages with few markers
        # all end up as "English". We therefore require a MINIMUM presence
        # of explicitly-detected Hinglish messages (≥6% of sample, i.e. ≥2
        # for a 30-message sample) before calling a session "Hinglish".
        # A session with only 1 detected Hinglish message is likely truly
        # English with an isolated Hinglish phrase → "Mixed".
        hinglish_count  = lang_counts.get("Hinglish", 0)
        english_count   = lang_counts.get("English",  0)
        hindi_count     = lang_counts.get("Hindi",    0)
        sample_sz       = len(sample)
        hinglish_min    = max(2, round(sample_sz * 0.06))   # ≥2 for 30-msg sample

        if not lang_counts:
            dominant = "Unknown"
        elif has_hinglish and hinglish_count >= hinglish_min:
            # Meaningful Hinglish presence — short/ambiguous messages that
            # fell through to "English" are contextually Hinglish.
            dominant = "Hinglish"
        elif has_hinglish and hinglish_count < hinglish_min:
            # Token Hinglish (1 message) with clear English majority → Mixed
            dominant = "Mixed"
        elif english_count >= hindi_count and english_count > 0:
            dominant = "English"
        elif hindi_count > 0:
            dominant = "Hindi"
        else:
            # Regional or other — use raw most-common, skip "Unknown"
            top = lang_counts.most_common(1)[0][0]
            dominant = top if top != "Unknown" else "Unknown"

        return SessionLanguage(
            dominant_language=dominant,
            languages_detected=dict(lang_counts),
            has_hinglish=has_hinglish,
            has_devanagari=has_devanagari,
            has_regional=has_regional,
            sample_size=len(sample),
        )

    def get_language_instruction(self, session_language: SessionLanguage) -> str:
        """
        Return a language-context string for injection into LLM prompts.
        Tailored to the session's dominant language.
        """
        dom = session_language.dominant_language
        suffix = (
            "\nDo not flag content based on language alone. "
            "Assess meaning and intent."
        )

        if dom == "Hinglish":
            body = (
                "This conversation is primarily in Hinglish — Hindi written in "
                "Roman/English script. Common Hindi words will appear in English "
                "letters (e.g. 'mera', 'aap', 'bahut', 'kya'). Understand the "
                "full semantic meaning across both languages. Cultural terms of "
                "endearment like 'darling', 'dear', 'ji', 'yaar' are normal in "
                "Indian professional communication and do NOT indicate romantic "
                "intent on their own."
            )
        elif dom == "Hindi":
            body = (
                "This conversation is in Hindi (Devanagari script). "
                "Assess content for violations in Hindi. Cultural warmth "
                "expressions in Hindi are normal."
            )
        elif dom == "English":
            body = "This conversation is in English."
        elif dom == "Tamil":
            body = (
                "This conversation is primarily in Tamil. Some messages may "
                "switch to English. Assess Tamil content with full semantic "
                "understanding."
            )
        elif dom == "Gujarati":
            body = (
                "This conversation is primarily in Gujarati. "
                "Some English code-switching may appear."
            )
        elif dom == "Mixed":
            langs = ", ".join(
                k for k in session_language.languages_detected
                if k not in ("Unknown",)
            )
            body = (
                f"This conversation switches between multiple languages "
                f"including {langs}. Assess each message in its own "
                f"language context."
            )
        else:
            body = (
                f"This conversation appears to be in {dom}. "
                "Assess content for violations in its original language."
            )

        return body + suffix

    def detect_script(self, text: str) -> str:
        """
        Identify the dominant writing script in the text using Unicode ranges.

        Returns: "Devanagari" | "Tamil" | "Bengali" | "Gujarati" |
                 "Latin" | "Mixed"
        """
        counts = {
            "Devanagari": 0,
            "Tamil":      0,
            "Bengali":    0,
            "Gujarati":   0,
        }
        latin_count = 0
        total       = 0

        for ch in text:
            cp = ord(ch)
            if _DEVANAGARI_RANGE[0] <= cp <= _DEVANAGARI_RANGE[1]:
                counts["Devanagari"] += 1
                total += 1
            elif _TAMIL_RANGE[0] <= cp <= _TAMIL_RANGE[1]:
                counts["Tamil"] += 1
                total += 1
            elif _BENGALI_RANGE[0] <= cp <= _BENGALI_RANGE[1]:
                counts["Bengali"] += 1
                total += 1
            elif _GUJARATI_RANGE[0] <= cp <= _GUJARATI_RANGE[1]:
                counts["Gujarati"] += 1
                total += 1
            elif ch.isalpha():
                latin_count += 1
                total += 1

        if total == 0:
            return "Latin"

        non_latin = sum(counts.values())

        # Dominant non-Latin script threshold: > 20% of alphabetic chars
        for script_name, cnt in counts.items():
            if cnt / total > 0.20:
                if latin_count / total > 0.30:
                    return "Mixed"
                return script_name

        return "Latin"

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _hinglish_marker_ratio(self, text: str) -> float:
        """
        Fraction of text tokens that are Hinglish markers.
        Astro terms are excluded from the denominator so that a session
        full of astrological vocabulary doesn't suppress the ratio.
        """
        tokens = re.findall(r'\b[a-zA-Z]+\b', text.lower())
        # Exclude pure astro terms from the token list
        content_tokens = [t for t in tokens if t not in self.ASTRO_TERMS]
        if not content_tokens:
            return 0.0
        marker_hits = sum(1 for t in content_tokens if t in self.HINGLISH_MARKERS)
        return marker_hits / len(content_tokens)

    def _sample_messages(
        self, messages: list[dict[str, Any]], max_total: int = 30
    ) -> list[dict[str, Any]]:
        """
        Return up to max_total messages sampled from the beginning,
        middle, and end of the session (10 from each zone).
        """
        n = len(messages)
        per_zone = max_total // 3  # 10 each

        if n <= max_total:
            return messages

        first  = messages[:per_zone]
        mid_s  = (n - per_zone) // 2
        middle = messages[mid_s: mid_s + per_zone]
        last   = messages[-per_zone:]

        # De-duplicate while preserving order
        seen: set[int] = set()
        sample: list[dict[str, Any]] = []
        for m in first + middle + last:
            mid = id(m)
            if mid not in seen:
                seen.add(mid)
                sample.append(m)
        return sample

    @staticmethod
    def _safe_langdetect(text: str) -> str:
        """Run langdetect and return the code; return '' on any error."""
        try:
            return _ld_detect(text)
        except LangDetectException:
            return ""


# ---------------------------------------------------------------------------
# Self-tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    detector = LanguageDetector()

    tests = [
        {
            "id":   "T1",
            "desc": "Pure Hinglish",
            "text": "mera naam kya hai aur kaise hoga mera future",
            "expect_primary":    "Hinglish",
            "expect_hinglish":   True,
            "expect_script":     None,
        },
        {
            "id":   "T2",
            "desc": "Devanagari Hindi",
            "text": "\u092e\u0947\u0930\u0940 \u0936\u093e\u0926\u0940 \u0915\u092c "
                    "\u0939\u094b\u0917\u0940 \u0914\u0930 \u092e\u0947\u0930\u093e "
                    "\u092d\u0935\u093f\u0937\u094d\u092f \u0915\u0948\u0938\u093e "
                    "\u0939\u094b\u0917\u093e",
            "expect_primary":  "Hindi",
            "expect_hinglish": False,
            "expect_script":   "Devanagari",
        },
        {
            "id":   "T3",
            "desc": "English",
            "text": "I want to know about my career prospects for 2025",
            "expect_primary":  "English",
            "expect_hinglish": False,
            "expect_script":   None,
        },
        {
            "id":   "T4",
            "desc": "Mixed AstroTalk style",
            "text": "maam aap bahut sundar hain I am very fond of you aapke bina neend nahi aati",
            "expect_primary":  "Hinglish",
            "expect_hinglish": True,
            "expect_script":   None,
        },
        {
            "id":   "T5",
            "desc": "Tamil",
            "text": "\u0b8e\u0ba9\u0bcd \u0ba4\u0bbf\u0bb0\u0bc1\u0bae\u0ba3 "
                    "\u0bb5\u0bbe\u0bb4\u0bcd\u0b95\u0bcd\u0b95\u0bc8 "
                    "\u0b8e\u0baa\u0bcd\u0baa\u0b9f\u0bbf \u0b87\u0bb0\u0bc1\u0b95\u0bcd\u0b95\u0bc1\u0bae\u0bcd",
            "expect_primary":  "Tamil",
            "expect_hinglish": False,
            "expect_script":   "Tamil",
        },
        {
            "id":   "T6",
            "desc": "Tagalog false positive case",
            "text": "aap ne jo time frame diya h main iske bad aapko raat ko milne aunga",
            "expect_primary":  "Hinglish",
            "expect_hinglish": True,
            "expect_script":   None,
            "note":            "langdetect misidentifies this as tl/et/id — must still return Hinglish",
        },
    ]

    print("=" * 64)
    print("  LanguageDetector — Self-Tests")
    print("=" * 64)
    all_pass = True

    for t in tests:
        result = detector.detect(t["text"])
        ok_primary  = result.primary_language == t["expect_primary"]
        ok_hinglish = result.is_hinglish      == t["expect_hinglish"]
        ok_script   = (t["expect_script"] is None) or (result.script == t["expect_script"])
        passed = ok_primary and ok_hinglish and ok_script
        all_pass = all_pass and passed

        status = "PASS" if passed else "FAIL"
        print(f"\n  [{status}] {t['id']} — {t['desc']}")
        print(f"         primary_language     : {result.primary_language!r}"
              f"  (expected {t['expect_primary']!r})"
              f"  {'OK' if ok_primary else 'WRONG'}")
        print(f"         is_hinglish          : {result.is_hinglish}"
              f"  (expected {t['expect_hinglish']})"
              f"  {'OK' if ok_hinglish else 'WRONG'}")
        print(f"         script               : {result.script!r}"
              + (f"  (expected {t['expect_script']!r})  {'OK' if ok_script else 'WRONG'}"
                 if t["expect_script"] else ""))
        print(f"         hinglish_confidence  : {result.hinglish_confidence}")
        print(f"         langdetect raw       : {result.detected_by_langdetect!r}")
        if "note" in t:
            print(f"         note                 : {t['note']}")

    print()
    print("=" * 64)
    print(f"  Overall: {'ALL PASS' if all_pass else 'SOME TESTS FAILED'}")
    print("=" * 64)
