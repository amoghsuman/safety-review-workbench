"""
seed_dummy_data.py
Populates the SQLite store with realistic dummy sessions so the review
interface can be tested without running the full detection pipeline.

Usage:
    python seed_dummy_data.py
"""

import sqlite3
import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Make project packages importable when run from any working directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

DB_PATH = os.getenv("DB_PATH", "store/astrotalk.db")

# Propagate to env so store.db.initialise_db() targets the same file
os.environ.setdefault("DB_PATH", DB_PATH)

from store.db import initialise_db  # noqa: E402 (import after env setup)

# ── Reproducibility ────────────────────────────────────────────────────────
random.seed(42)

# ── Session-level configuration ────────────────────────────────────────────

SESSION_IDS = [
    "294055364", "293987441", "295432187", "296701234", "297845620",
    "298312456", "299087651", "300456123", "301789045", "302134678",
    "303567891", "304892034", "305023456", "306347891", "307659012",
    "308012347", "309456781", "310789234", "311234567", "312678901",
]

# Exact distribution per spec
VERDICTS = ["SEVERE"] * 8 + ["FLAGGED"] * 7 + ["CLEAN"] * 5
LANGUAGES = (
    ["Hindi"] * 8 + ["English"] * 4 + ["Tamil"] * 3
    + ["Telugu"] * 2 + ["Punjabi"] * 2 + ["Bengali"] * 1
)
SESSION_TYPES = ["chat"] * 14 + ["voice"] * 6  # 70 / 30

random.shuffle(VERDICTS)
random.shuffle(LANGUAGES)
random.shuffle(SESSION_TYPES)

ASTROLOGERS = [
    "Pandit Rajesh Sharma",
    "Astro Priya Nair",
    "Jyotish Kumar",
    "Pandit Suresh Iyer",
    "Astro Meena Patel",
]

FLAG_CATEGORIES = [
    "OFF_PLATFORM_SOLICITATION",
    "NSFW",
    "FEAR_MANIPULATION",
    "FINANCIAL_SOLICITATION",
    "PERSONAL_DATA_COLLECTION",
]

# ── Message pools ──────────────────────────────────────────────────────────

USER_MESSAGES = [
    "Namaste ji, mujhe apni kundli ke baare mein jaanna tha",
    "Meri shaadi kab hogi? Bahut pareshan hoon",
    "Job switch karoon ya nahi? Please guide karein",
    "Hello, I wanted to know about my career prospects this year",
    "Mere ghar mein bahut kalesh hai, koi upay batao",
    "My business is not doing well, please help",
    "Kya mera ex wapas aayega? Bahut dukhi hoon",
    "Health problems chal rahe hain, koi totka?",
    "When will I get married? I am 32 years old",
    "Financial problems are troubling me a lot",
]

ASTRO_NORMAL = [
    "Namaste, apni date of birth, time aur place batao",
    "Aapki kundli mein Shani ki mahadasha chal rahi hai",
    "Mangal ashtam mein hai, thoda saavdhaan rehna",
    "Agle 6 mahine career ke liye acche hain",
    "Guru ki kripa se shaadi ke yog ban rahe hain 2026 mein",
    "Roz subah Hanuman Chalisa padhein, labh hoga",
    "Your Venus is strong, love life will improve soon",
    "I can see Jupiter entering your 7th house next month",
    "Wear a yellow sapphire on Thursday for best results",
    "Chant Om Namah Shivaya 108 times daily",
]

# Each violation type: messages, detection layer, reasoning, FP risk
VIOLATION_POOLS = {
    "OFF_PLATFORM_SOLICITATION": {
        "messages": [
            "Aap mujhe WhatsApp par contact karein seedha — 98XXXXXXXX",
            "Mere personal number pe call karein for detailed reading",
            "Add me on Telegram for special discount puja services",
        ],
        "detection_layer": "REGEX",
        "reasoning": "Astrologer explicitly shared personal contact information for off-platform communication",
        "fp_risk": "LOW",
    },
    "FEAR_MANIPULATION": {
        "messages": [
            "Aapki kundli mein bahut bada sankat aa raha hai agle 3 mahine mein",
            "Kala jadu ka asar hai aap par, turant upay karna hoga warna...",
            "Your chart shows extreme danger in the coming months, only I can help",
        ],
        "detection_layer": "LLM",
        "reasoning": "Fear-based language used to pressure user into purchasing remedy",
        "fp_risk": "LOW",
    },
    "FINANCIAL_SOLICITATION": {
        "messages": [
            "Is special puja ke liye 5100 rupees chahiye, seedha mujhe bhejo",
            "Send Rs 2100 to this UPI: pandit@upi for the remedy to work",
            "For complete protection kavach, pay 7500 to my personal account",
        ],
        "detection_layer": "REGEX",
        "reasoning": "Direct financial solicitation outside platform payment system",
        "fp_risk": "LOW",
    },
    "NSFW": {
        "messages": [
            "Aap bahut attractive hain, aapke saath personal time spend karna chahta hoon",
        ],
        "detection_layer": "LLM",
        "reasoning": "Sexually suggestive language directed at user",
        "fp_risk": "MEDIUM",
    },
}

# ── Helpers ────────────────────────────────────────────────────────────────

def random_start(days_range: int = 90) -> datetime:
    """Return a random datetime within the last days_range days."""
    base = datetime.now() - timedelta(days=random.randint(1, days_range))
    return base.replace(
        hour=random.randint(8, 22),
        minute=random.randint(0, 59),
        second=0,
        microsecond=0,
    )


def confidence_for(verdict: str) -> float:
    if verdict == "SEVERE":
        return round(random.uniform(0.82, 0.97), 2)
    if verdict == "FLAGGED":
        return round(random.uniform(0.61, 0.81), 2)
    return round(random.uniform(0.88, 0.98), 2)


def generate_turns_and_flags(
    session_id: str, verdict: str, start_dt: datetime, n_turns: int
) -> tuple[list, list]:
    """
    Build turn and flag rows for one session.
    Turns alternate USER / ASTROLOGER starting with USER.
    Violation messages are injected into ASTROLOGER turns for
    SEVERE (3-4) and FLAGGED (1-2) sessions.
    Returns (turns, flags).
    """
    turns: list[dict] = []
    flags: list[dict] = []

    # Choose violation categories
    if verdict == "SEVERE":
        n_viol = random.randint(3, 4)
        categories = random.choices(list(VIOLATION_POOLS.keys()), k=n_viol)
    elif verdict == "FLAGGED":
        n_viol = random.randint(1, 2)
        categories = random.choices(list(VIOLATION_POOLS.keys()), k=n_viol)
    else:
        categories = []

    # ASTROLOGER speaks on odd turn indices (0-based)
    astro_indices = [i for i in range(n_turns) if i % 2 == 1]

    # Inject violations into the latter two-thirds of astrologer turns
    violation_at: dict[int, str] = {}
    if categories and astro_indices:
        mid = len(astro_indices) // 3
        eligible = astro_indices[mid:]
        chosen = sorted(random.sample(eligible, min(len(categories), len(eligible))))
        for idx, cat in zip(chosen, categories):
            violation_at[idx] = cat

    # Build individual turns
    for i in range(n_turns):
        turn_id = i + 1
        speaker = "USER" if i % 2 == 0 else "ASTROLOGER"
        ts = (start_dt + timedelta(minutes=i * random.randint(2, 5))).isoformat()

        if speaker == "USER":
            message = random.choice(USER_MESSAGES)
        elif i in violation_at:
            cat  = violation_at[i]
            pool = VIOLATION_POOLS[cat]
            message = random.choice(pool["messages"])
            flags.append({
                "session_id":          session_id,
                "turn_id":             None,   # known limitation — turn_id not resolved
                "category_code":       cat,
                "detection_layer":     pool["detection_layer"],
                "severity":            "HIGH" if verdict == "SEVERE" else "MEDIUM",
                "confidence_score":    round(random.uniform(0.75, 0.97), 2),
                "reasoning":           pool["reasoning"],
                "false_positive_risk": pool["fp_risk"],
                "pattern_matched":     cat if pool["detection_layer"] == "REGEX" else None,
            })
        else:
            message = random.choice(ASTRO_NORMAL)

        turns.append({
            "turn_id":           turn_id,
            "session_id":        session_id,
            "speaker":           speaker,
            "message_text":      message,
            "timestamp":         ts,
            "language_detected": None,
        })

    return turns, flags


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    # Step 1 — initialise schema
    print(f"Initialising database at {DB_PATH} ...")
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    initialise_db()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    now = datetime.now()
    total_turns = 0
    total_flags = 0

    # Pre-clear any stale turns and flags for the sessions we're about to seed
    # (idempotent re-runs — sessions are handled by INSERT OR REPLACE on PK)
    for sid in SESSION_IDS:
        cur.execute("DELETE FROM turns WHERE session_id = ?", (sid,))
        cur.execute("DELETE FROM flags WHERE session_id = ?", (sid,))

    # Step 2 — sessions
    print("Seeding 20 sessions ...")
    for n, session_id in enumerate(SESSION_IDS):
        verdict      = VERDICTS[n]
        language     = LANGUAGES[n]
        stype        = SESSION_TYPES[n]
        astrologer   = ASTROLOGERS[n % len(ASTROLOGERS)]
        duration     = round(random.uniform(12, 65), 1)
        start_dt     = random_start(90)
        end_dt       = start_dt + timedelta(minutes=duration)
        confidence   = confidence_for(verdict)
        is_flagged   = 0 if verdict == "CLEAN" else 1
        flag_cat     = "" if verdict == "CLEAN" else random.choice(FLAG_CATEGORIES)

        # First 3 sessions already reviewed
        if n < 3:
            review_status = "REVIEWED"
            reviewer_id   = "Amogh Suman"
            reviewer_note = (
                "Confirmed violation — clear pattern of off-platform redirection"
            )
            reviewed_at   = (
                now - timedelta(days=random.randint(1, 3))
            ).isoformat()
        else:
            review_status = "PENDING"
            reviewer_id   = None
            reviewer_note = None
            reviewed_at   = None

        cur.execute(
            """
            INSERT OR REPLACE INTO sessions (
                session_id, astrologer_id, user_id,
                session_start, session_end, duration_minutes,
                session_type, language_detected,
                overall_verdict, confidence_score,
                astrotalk_flagged, astrotalk_flag_category, astrotalk_severity,
                review_status, reviewer_id, reviewer_note, reviewed_at,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                astrologer,
                f"User_{n + 1}",
                start_dt.isoformat(),
                end_dt.isoformat(),
                duration,
                stype,
                language,
                verdict,
                confidence,
                is_flagged,
                flag_cat,
                verdict if is_flagged else "",
                review_status,
                reviewer_id,
                reviewer_note,
                reviewed_at,
                now.isoformat(),
            ),
        )

        # Steps 3 & 4 — turns and flags
        n_turns = random.randint(8, 20)
        turns, flags = generate_turns_and_flags(session_id, verdict, start_dt, n_turns)

        cur.executemany(
            """
            INSERT OR REPLACE INTO turns
                (session_id, turn_id, speaker, message_text, timestamp, language_detected)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    t["session_id"], t["turn_id"], t["speaker"],
                    t["message_text"], t["timestamp"], t["language_detected"],
                )
                for t in turns
            ],
        )

        cur.executemany(
            """
            INSERT INTO flags
                (session_id, turn_id, category_code, detection_layer, severity,
                 confidence_score, reasoning, false_positive_risk, pattern_matched)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    f["session_id"], f["turn_id"], f["category_code"],
                    f["detection_layer"], f["severity"],
                    f["confidence_score"], f["reasoning"],
                    f["false_positive_risk"], f["pattern_matched"],
                )
                for f in flags
            ],
        )

        total_turns += len(turns)
        total_flags += len(flags)

    conn.commit()
    conn.close()

    # Step 5 — summary
    print()
    print("Dummy data seeded successfully")
    print(f"Sessions: 20 (8 SEVERE, 7 FLAGGED, 5 CLEAN)")
    print(f"Total turns inserted: {total_turns}")
    print(f"Total flags inserted: {total_flags}")
    print(f"Database: {DB_PATH}")


if __name__ == "__main__":
    main()
