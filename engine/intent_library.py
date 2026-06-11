"""
intent_library.py
Defines the full taxonomy of 12 NSFW intents for AstroTalk's detection
engine, and provides formatting helpers that inject intent definitions
into LLM classification prompts.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

# Allow running this file directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Intent:
    """A single NSFW intent category."""

    intent_id:          str
    name:               str
    description:        str
    severity:           str            # "Red" | "Amber"
    examples:           list[str]      # phrases that SHOULD trigger
    counter_examples:   list[str]      # phrases that should NOT trigger
    annexure_category:  str
    detection_notes:    str            # special instructions for the LLM


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class IntentLibrary:
    """
    Registry of all 12 AstroTalk NSFW detection intents.

    Usage
    -----
    library = IntentLibrary()
    prompt_block = library.format_for_prompt(third_party_names=["Priyanka"])
    red_only = library.get_red_intents()
    """

    # ------------------------------------------------------------------
    # Intent definitions
    # ------------------------------------------------------------------

    _INTENTS: list[Intent] = [

        Intent(
            intent_id="INT-01",
            name="Explicit Sexual Description Directed at Consultant",
            description=(
                "User or consultant describes sexual acts, body parts, or intimate "
                "physical actions directed personally at the other party in the "
                "conversation — not about a third party."
            ),
            severity="Red",
            examples=[
                "mujhe aapke saath sona hai",
                "I want to kiss you all over",
                "aapki body kaisi hai, touch karna chahta hoon",
                "can we have sex, I am very attracted to you",
                "uski chut jyada achi hai ya gaand (directed at consultant)",
                "meri kaisi chudayi honi chahiye (asking consultant personally)",
            ],
            counter_examples=[
                "mere husband ki physical needs ke baare mein batao (third-party reading)",
                "kya mera physical relationship improve hoga (asking about own life)",
                "Priyanka ke saath meri physical compatibility kaisi hai (third party — name in third_party_names list)",
                "aapke 7th house mein physical union ka yoga hai (astrological prediction language)",
            ],
            annexure_category="Category A — Explicit Sexual Content",
            detection_notes=(
                "Only flag if sexual description is directed AT the consultant or from "
                "consultant TO user personally. Third-party references in readings are "
                "NOT violations. Check third_party_names context before flagging."
            ),
        ),

        Intent(
            intent_id="INT-02",
            name="Minor-Related Sexual Content",
            description=(
                "Any sexual content involving or referencing minors, incest, or "
                "physical intimacy with underage individuals."
            ),
            severity="Red",
            examples=[
                "meri beti ke saath kuch hua (context: inappropriate/sexual)",
                "bacche ke saath galat kaam",
                "any explicit content where age under 18 is implied or stated",
            ],
            counter_examples=[
                "mera beta 16 saal ka hai, uski career guidance chahiye",
                "meri beti ki shaadi kab hogi (normal reading question)",
            ],
            annexure_category="Category A — Explicit Sexual Content",
            detection_notes=(
                "Extremely high sensitivity. Flag any ambiguous reference involving "
                "minors and sexual context. Do not require explicit confirmation — "
                "flag on suspicion."
            ),
        ),

        Intent(
            intent_id="INT-03",
            name="Physical Appearance Probing of Consultant",
            description=(
                "User asking consultant about their body, appearance, physical "
                "features, or requesting photos for non-astrological purposes."
            ),
            severity="Amber",
            examples=[
                "aap kitni tall hain",
                "aapka figure kaisa hai",
                "apni photo bhejo na",
                "are you fair or dark, I am attracted to you",
                "show me your pic, I want to see you",
            ],
            counter_examples=[
                "astrological chart ki photo bhejo",
                "kundali ki image share karo",
                "astrologer asking for user's photo for palm reading",
            ],
            annexure_category="Category B — Inappropriate Personal Probing",
            detection_notes=(
                "Context matters. Photo requests for astrological purposes (kundali, "
                "palm, face reading) are legitimate. Personal photo requests with "
                "romantic context are violations."
            ),
        ),

        Intent(
            intent_id="INT-04",
            name="Explicit Image Solicitation",
            description=(
                "Requesting or sending nude, semi-nude, or sexually explicit "
                "images or videos."
            ),
            severity="Red",
            examples=[
                "apni nude photo bhejo",
                "video call pe kapde utaro",
                "send me your hot pic",
                "[IMAGE] token followed by sexual context in surrounding messages",
            ],
            counter_examples=[
                "kundali ki image share ki",
                "palm ki photo bhejo for reading",
            ],
            annexure_category="Category A — Explicit Sexual Content",
            detection_notes=(
                "The [IMAGE] token in messages should be assessed in context. "
                "If preceding or following messages are sexual, flag as INT-04."
            ),
        ),

        Intent(
            intent_id="INT-05",
            name="Inappropriate Attire Reference",
            description=(
                "References to consultant or user wearing revealing, inappropriate, "
                "or sexualised clothing during video or live calls."
            ),
            severity="Amber",
            examples=[
                "video pe kam kapde pahno",
                "bra mein aa jao video pe",
                "tumhara dress bahut revealing tha aaj",
            ],
            counter_examples=[
                "formal kapde pahno please (professional dress request)",
                "saree mein bahut sundar lag rahi hain (compliment, not directive)",
            ],
            annexure_category="Category B — Inappropriate Personal Probing",
            detection_notes=(
                "Only flag if there is a directive or explicit sexualisation of attire. "
                "A compliment alone is not a violation."
            ),
        ),

        Intent(
            intent_id="INT-06",
            name="Off-Platform Solicitation",
            description=(
                "Attempts to move communication outside AstroTalk — sharing phone "
                "numbers, WhatsApp, email, social media, or requesting in-person meetings."
            ),
            severity="Red",
            examples=[
                "mera number hai 98XXXXXXXX, WhatsApp karo",
                "Instagram pe follow karo @xxxxx",
                "ghar aa jao milne ke liye",
                "email karo mujhe, main bahar baat karta hoon",
                "Paytm pe directly pay karo mujhe",
            ],
            counter_examples=[
                "AstroTalk ka support number use karo",
                "app ke through hi baat karo",
                "birth place ka STD code 022 hai (phone code in birth details, not contact sharing)",
                "my pin code is 110001 (address detail in reading context)",
            ],
            annexure_category="Category C — Platform Policy Violation",
            detection_notes=(
                "Phone number patterns in birth detail messages at the START of a "
                "session are NOT violations — these are profile details. Only flag if "
                "a number or contact detail is shared mid-conversation with clear "
                "intent to communicate outside the platform."
            ),
        ),

        Intent(
            intent_id="INT-07",
            name="Vulgar Sexual Language",
            description=(
                "Use of explicit sexual slurs, vulgar abuse, or graphic sexual "
                "vocabulary in a sexual context — in Hindi, English, or Hinglish."
            ),
            severity="Red",
            examples=[
                "chut, lund, gaand, bhosdike used in a sexual context",
                "fuck you, suck my dick",
                "sexual abuse directed at either party",
            ],
            counter_examples=[
                "slang used as general frustration without sexual context",
                "bhenchod used as a casual expletive without sexual targeting",
            ],
            annexure_category="Category A — Explicit Sexual Content",
            detection_notes=(
                "Assess intent. Casual swearing without sexual targeting is different "
                "from sexualised vulgar language. Flag only when language is sexual "
                "in nature, not merely coarse."
            ),
        ),

        Intent(
            intent_id="INT-08",
            name="Personal Sexual Information Request",
            description=(
                "Requesting personal sexual information from the user under the guise "
                "of astrological consultation — sexual history, preferences, or "
                "fantasies not relevant to any reading."
            ),
            severity="Red",
            examples=[
                "kitne log the aapki zindagi mein physically",
                "aapki sexual fantasy kya hai, reading ke liye zaroori hai",
                "kya aap masturbate karte ho, kundali ke liye batao",
            ],
            counter_examples=[
                "kya aapki married life mein physical compatibility hai (legitimate reading question)",
                "7th house se physical relationship ka pata chalta hai (astrological context)",
            ],
            annexure_category="Category B — Inappropriate Personal Probing",
            detection_notes=(
                "The guise of astrology does not make personal sexual information "
                "requests legitimate. If the information requested goes beyond what "
                "is needed for any standard reading, flag it."
            ),
        ),

        Intent(
            intent_id="INT-09",
            name="Unsolicited Sexual Content",
            description=(
                "Sending sexual messages, suggestions, or media that the other party "
                "did not ask for and has not engaged with."
            ),
            severity="Amber",
            examples=[
                "consultant sending sexual jokes unprompted",
                "user sending graphic descriptions of their fantasies without any invitation",
                "sexual emojis combined with suggestive text sent to consultant",
            ],
            counter_examples=[
                "user asking about their own sexual compatibility with partner (invited topic)",
                "consultant explaining planetary influences on intimacy (reading context)",
            ],
            annexure_category="Category A — Explicit Sexual Content",
            detection_notes=(
                "Assess whether the recipient engaged or invited the content. "
                "If consultant deflected and user continues — escalate severity "
                "with each repetition. Repeated unsolicited content becomes Red."
            ),
        ),

        Intent(
            intent_id="INT-10",
            name="Romantic Relationship Attempt",
            description=(
                "Attempting to establish a personal romantic or emotional relationship "
                "with the consultant beyond the professional consultation context."
            ),
            severity="Amber",
            examples=[
                "main aapse pyaar karta hoon, aap meri life mein aao",
                "I want to marry you, will you be my girlfriend",
                "mujhe aapke bina neend nahi aati",
                "aap sirf mere liye hain na",
            ],
            counter_examples=[
                "darling aap bahut helpful hain (cultural endearment, not romantic advance)",
                "dear, aapki reading bahut achi thi (professional warmth)",
                "I love your readings (appreciation, not romantic intent)",
                "aap bahut caring hain (appreciation of service quality)",
            ],
            annexure_category="Category B — Inappropriate Personal Probing",
            detection_notes=(
                "Single compliments or cultural warmth expressions are NOT this intent. "
                "This requires a clear attempt to establish a personal romantic "
                "connection — expressions of love, desire for relationship, jealousy, "
                "or possessiveness directed at the consultant. "
                "IMPORTANT: 'darling', 'dear', 'bachha', 'sweetheart' used by consultants "
                "— even repeatedly — are NOT this intent. These are culturally normal terms "
                "of address in Indian professional communication. Only flag INT-10 when the "
                "consultant explicitly expresses romantic feelings, desire for a relationship, "
                "or jealousy/possessiveness toward the user."
            ),
        ),

        Intent(
            intent_id="INT-11",
            name="Sexual Roleplay or Fictional Framing",
            description=(
                "Using fictional scenarios, roleplay framing, or hypothetical contexts "
                "to initiate or normalise sexual conversation."
            ),
            severity="Red",
            examples=[
                "agar hum dono akele hote toh kya hota",
                "imagine karo tum mere ghar pe ho, phir kya karoge",
                "let's play a game — you are my girlfriend",
                "as a character in a story, what would you do to me",
            ],
            counter_examples=[
                "agar meri shaadi ho jaati toh meri life kaisi hoti (hypothetical reading, not roleplay)",
                "imagine karo mere future mein kya hai (reading framing, not sexual)",
            ],
            annexure_category="Category A — Explicit Sexual Content",
            detection_notes=(
                "The fictional or hypothetical frame does not reduce severity. "
                "If the underlying content would be a violation without the fictional "
                "wrapper, flag it."
            ),
        ),

        Intent(
            intent_id="INT-12",
            name="Persistent Flirtation After Disengagement",
            description=(
                "Continuing flirtatious, romantic, or personal advances after the "
                "other party has clearly disengaged, redirected, or not responded "
                "to previous advances."
            ),
            severity="Amber",
            examples=[
                "user continues personal compliments across 5+ messages after consultant redirected to reading",
                "consultant continues using romantic language after user showed discomfort",
            ],
            counter_examples=[
                "single flirtatious comment followed by professional conversation",
                "aap bahut sundar ho said once, not repeated",
            ],
            annexure_category="Category B — Inappropriate Personal Probing",
            detection_notes=(
                "This intent requires a PATTERN across multiple messages — not a "
                "single instance. Look for escalation or repetition after a clear "
                "signal to stop or redirect. Minimum 3 instances before flagging."
            ),
        ),

        Intent(
            intent_id="RE_ENGAGEMENT_SOLICITATION",
            name="Post-Session Re-Engagement Solicitation",
            description=(
                "Astrologer sends unsolicited messages after the session has formally "
                "ended — indicated by an automated system message about session end, "
                "low balance, or chat termination. These follow-up messages are designed "
                "to re-engage the user and encourage wallet recharge or continued paid "
                "interaction."
            ),
            severity="Red",
            examples=[
                "Any ASTROLOGER message sent after an automated message containing: "
                "'chat ended', 'low balance', 'recharge', 'automated message', "
                "'session ended', 'contact customer support'",
                "Soch rahi thi tumhare baare mein (unsolicited emotional appeal after session end)",
                "Tumhara dard mehsoos ho raha hai (empathy bait after session close)",
                "Aapke baare mein kuch important dikh raha hai (urgency hook after termination)",
            ],
            counter_examples=[
                "System automated messages themselves",
                "Astrologer messages sent before the session-end automated message",
                "User-initiated messages after recharge",
            ],
            annexure_category="Category C — Platform Policy Violation",
            detection_notes=(
                "This intent is detected exclusively by the REGEX layer "
                "(ConsultantAnalyser.detect_post_session_messages) — do NOT attempt "
                "LLM classification for this category. Detection is deterministic: "
                "any non-automated ASTROLOGER message after the last session-end "
                "automated message is a violation, regardless of message content."
            ),
        ),

    ]

    # Build the lookup index once at class definition time
    _INDEX: dict[str, Intent] = {i.intent_id: i for i in _INTENTS}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def format_for_prompt(
        self, third_party_names: list[str] | None = None
    ) -> str:
        """
        Return all 12 intents serialised as a plain-text block ready for
        injection into an LLM classification prompt.

        If third_party_names is provided, prepends a context note so the
        model does not flag third-party references as INT-01 or INT-10.
        """
        lines: list[str] = []

        if third_party_names:
            names_str = ", ".join(third_party_names)
            lines += [
                "=" * 72,
                "CONTEXT — KNOWN THIRD PARTIES IN THIS SESSION",
                "=" * 72,
                (
                    f"KNOWN THIRD PARTIES IN THIS SESSION: {names_str}. "
                    "Any sexual or romantic content referencing these names is about "
                    "the user's personal life subject — NOT directed at the consultant. "
                    "Do not flag as INT-01 or INT-10."
                ),
                "",
            ]

        lines += [
            "=" * 72,
            "NSFW INTENT TAXONOMY — ASTROTALK DETECTION ENGINE",
            "=" * 72,
            (
                "Classify the conversation chunk against EACH of the following intents. "
                "For each intent that is triggered, return its intent_id, a confidence "
                "score (0.0–1.0), and a one-line reason. Return an empty list if none apply."
            ),
            "",
        ]

        for intent in self._INTENTS:
            lines += [
                "-" * 72,
                f"[{intent.intent_id}]  {intent.name}",
                f"Severity : {intent.severity}",
                f"Category : {intent.annexure_category}",
                "",
                f"Description:",
                f"  {intent.description}",
                "",
                "Examples (SHOULD trigger):",
            ]
            for ex in intent.examples:
                lines.append(f"  - {ex}")
            lines += [
                "",
                "Counter-examples (should NOT trigger):",
            ]
            for cx in intent.counter_examples:
                lines.append(f"  - {cx}")
            lines += [
                "",
                f"Detection notes:",
                f"  {intent.detection_notes}",
                "",
            ]

        lines.append("=" * 72)
        return "\n".join(lines)

    def get_intent(self, intent_id: str) -> Intent:
        """Return a single Intent by ID; raises KeyError if not found."""
        if intent_id not in self._INDEX:
            raise KeyError(
                f"Unknown intent_id {intent_id!r}. "
                f"Valid IDs: {self.get_intent_ids()}"
            )
        return self._INDEX[intent_id]

    def get_red_intents(self) -> list[Intent]:
        """Return all intents with severity == 'Red'."""
        return [i for i in self._INTENTS if i.severity == "Red"]

    def get_amber_intents(self) -> list[Intent]:
        """Return all intents with severity == 'Amber'."""
        return [i for i in self._INTENTS if i.severity == "Amber"]

    def get_intent_ids(self) -> list[str]:
        """Return all intent IDs in definition order."""
        return [i.intent_id for i in self._INTENTS]


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    lib = IntentLibrary()

    # ---- print all 12 intents ----
    print("=" * 72)
    print("ALL 12 INTENTS")
    print("=" * 72)
    for intent in lib._INTENTS:
        sev_marker = "[RED  ]" if intent.severity == "Red" else "[AMBER]"
        print(f"\n  {sev_marker} {intent.intent_id}  {intent.name}")
        print(f"           Category : {intent.annexure_category}")
        print(f"           Examples : {intent.examples[0]!r}")

    print()
    red   = lib.get_red_intents()
    amber = lib.get_amber_intents()
    print(f"Red intents   ({len(red)})  : {[i.intent_id for i in red]}")
    print(f"Amber intents ({len(amber)}): {[i.intent_id for i in amber]}")
    print(f"All IDs             : {lib.get_intent_ids()}")

    # ---- format_for_prompt with third_party_names ----
    print()
    print("=" * 72)
    print("format_for_prompt(third_party_names=['Priyanka'])")
    print("=" * 72)
    prompt_with = lib.format_for_prompt(third_party_names=["Priyanka"])
    assert "KNOWN THIRD PARTIES" in prompt_with, "KNOWN THIRD PARTIES block missing!"
    assert "Priyanka" in prompt_with
    print(prompt_with[:600], "...\n[truncated]")

    print()
    print(f"Character count (with third_party_names) : {len(prompt_with):,}")

    # ---- format_for_prompt without third_party_names ----
    prompt_plain = lib.format_for_prompt()
    assert "KNOWN THIRD PARTIES" not in prompt_plain
    print(f"Character count (no third_party_names)   : {len(prompt_plain):,}")

    # Rough token estimate (1 token ~ 4 chars for English)
    print(f"Approx token budget (chars / 4)          : ~{len(prompt_plain) // 4:,} tokens")

    # ---- spot-check get_intent ----
    i01 = lib.get_intent("INT-01")
    assert i01.severity == "Red"
    assert i01.intent_id == "INT-01"
    i10 = lib.get_intent("INT-10")
    assert i10.severity == "Amber"
    print()
    print("All assertions passed.")
