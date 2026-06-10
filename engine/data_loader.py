"""
data_loader.py
Loads AstroTalk CSV data (one row per message) and reconstructs
session objects for the classification pipeline.

Accepts either a single CSV file path or a folder of CSV files.
All .csv files in a folder are concatenated and processed as one dataset.

Usage
-----
    loader   = DataLoader('data/raw/astrotalk_data.csv')
    loader   = DataLoader('data/raw/')
    sessions = loader.load_sessions()   # -> list[dict]
"""

from __future__ import annotations

import sys
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

# Allow running this file directly (python engine/data_loader.py)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ---------------------------------------------------------------------------
# Speaker normalisation
# ---------------------------------------------------------------------------
_SPEAKER_MAP = {
    "consultant": "ASTROLOGER",
    "user":       "USER",
}


class DataLoader:
    """
    Reads AstroTalk CSV exports (one row per message) and exposes
    clean session dicts for the classification pipeline.

    Initialise with a file path or folder path:
        loader = DataLoader('data/raw/astrotalk_data.csv')
        loader = DataLoader('data/raw/')

    Public interface:
        sessions = loader.load_sessions()  -> list[dict]
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._sessions: list[dict[str, Any]] = []
        self._loaded = False
        self._duplicates_removed = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_sessions(self) -> list[dict[str, Any]]:
        """
        Load CSV(s), build session dicts, print a summary, and return
        the session list. Keeps the same public interface as the previous
        loader so batch_runner.py requires no changes.
        """
        df = self._load_dataframe()
        self._sessions = self._build_sessions(df)
        self._loaded = True
        self._print_summary()
        return self._sessions

    # ------------------------------------------------------------------
    # Private — I/O
    # ------------------------------------------------------------------

    def _load_dataframe(self) -> pd.DataFrame:
        """
        Load one CSV or all .csv files in a folder into a single DataFrame.
        Unreadable files are skipped with a warning; raises if nothing loads.
        All columns are read as strings to avoid pandas type inference
        silently mangling IDs or codes.
        """
        if self.path.is_dir():
            csv_files = sorted(self.path.glob("*.csv"))
            if not csv_files:
                raise FileNotFoundError(
                    f"No .csv files found in directory: {self.path}"
                )
            frames: list[pd.DataFrame] = []
            for f in csv_files:
                try:
                    frames.append(
                        pd.read_csv(f, dtype=str, keep_default_na=False)
                    )
                    print(f"[DataLoader] Loaded: {f.name}")
                except Exception as exc:
                    warnings.warn(
                        f"[DataLoader] Skipping {f.name} — could not read: {exc}"
                    )
            if not frames:
                raise RuntimeError(
                    f"All CSV files in {self.path} failed to load."
                )
            return pd.concat(frames, ignore_index=True)

        if not self.path.exists():
            raise FileNotFoundError(f"CSV file not found: {self.path}")
        df = pd.read_csv(self.path, dtype=str, keep_default_na=False)
        print(f"[DataLoader] Loaded: {self.path.name}")
        return df

    # ------------------------------------------------------------------
    # Private — session construction
    # ------------------------------------------------------------------

    def _build_sessions(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """
        Group the flat message rows by session_id and build one
        session dict per group. Returns a list sorted by session_start.
        """
        # Drop rows whose session_id is null or empty string
        df = df[df["session_id"].str.strip().astype(bool)].copy()

        sessions: list[dict[str, Any]] = []

        for session_id, group in df.groupby("session_id", sort=False):
            session_id = str(session_id).strip()

            # Skip sessions that have nothing to classify
            n_classifiable = (
                group["is_automated_message"]
                .apply(self._normalise_automated)
                .eq(0)
                .sum()
            )
            if n_classifiable == 0:
                continue

            # Dedup exact-duplicate rows (export artefacts)
            group, removed = self._dedup_messages(group)
            self._duplicates_removed += removed

            # ── Timestamps ────────────────────────────────────────────
            timestamps = group["sent_at_ist"].apply(self._parse_timestamp)
            valid_ts   = [t for t in timestamps if t is not None]
            session_start = min(valid_ts).isoformat() if valid_ts else None
            session_end   = max(valid_ts).isoformat() if valid_ts else None
            if len(valid_ts) >= 2:
                delta    = (max(valid_ts) - min(valid_ts)).total_seconds() / 60
                duration = round(delta, 1)
            else:
                duration = 0.0

            # ── AstroTalk flag ─────────────────────────────────────────
            astrotalk_flagged = (
                1
                if (group["flagged"].str.strip().str.lower() == "yes").any()
                else 0
            )

            # ── Scalar session fields (first non-empty value in group) ─
            def first_val(col: str) -> str | None:
                if col not in group.columns:
                    return None
                nonempty = group[col].str.strip()
                nonempty = nonempty[nonempty != ""]
                return nonempty.iloc[0] if not nonempty.empty else None

            # ── Turn list ──────────────────────────────────────────────
            messages: list[dict[str, Any]] = []
            for _, row in group.iterrows():
                ts_val  = self._parse_timestamp(row.get("sent_at_ist", ""))
                turn_id = self._parse_turn_id(
                    row.get("message_seq", ""), len(messages) + 1
                )
                messages.append({
                    "turn_id":      turn_id,
                    "speaker":      self._normalise_speaker(
                                        row.get("sender", "")
                                    ),
                    "message_text": str(row.get("message_text", "")).strip(),
                    "is_automated": self._normalise_automated(
                                        row.get("is_automated_message", 0)
                                    ),
                    "timestamp":    ts_val.isoformat() if ts_val else None,
                })

            sessions.append({
                "session_id":              session_id,
                "astrologer_id":           first_val("astrologer_id"),
                "user_id":                 None,
                "session_date":            first_val("session_date"),
                "month":                   first_val("month"),
                "language_code":           first_val("language"),
                "session_type":            "chat",
                "astrotalk_flagged":       astrotalk_flagged,
                "astrotalk_flag_category": None,
                "astrotalk_severity":      None,
                "session_start":           session_start,
                "session_end":             session_end,
                "duration_minutes":        duration,
                "messages":                messages,
            })

        # Sort by session_start ascending; sessions with no timestamp sort last
        sessions.sort(key=lambda s: s["session_start"] or "")
        return sessions

    @staticmethod
    def _dedup_messages(
        group: pd.DataFrame,
    ) -> tuple[pd.DataFrame, int]:
        """
        Drop rows that are exact duplicates on (sender, message_text,
        sent_at_ist). Handles repeated rows from multi-file export artefacts.
        First occurrence is kept.
        """
        before = len(group)
        group  = group.drop_duplicates(
            subset=["sender", "message_text", "sent_at_ist"], keep="first"
        )
        return group, before - len(group)

    # ------------------------------------------------------------------
    # Private — field normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_speaker(sender: Any) -> str:
        """'consultant' → 'ASTROLOGER', 'user' → 'USER', else 'UNKNOWN'."""
        return _SPEAKER_MAP.get(str(sender).strip().lower(), "UNKNOWN")

    @staticmethod
    def _normalise_automated(val: Any) -> int:
        """Safely coerce is_automated_message to 0 or 1."""
        if isinstance(val, bool):
            return int(val)
        try:
            return 1 if int(str(val).strip()) else 0
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _parse_timestamp(val: Any) -> datetime | None:
        """
        Try common IST datetime formats in order; fall back to pandas
        inference for unusual formats. Returns None on any failure —
        never raises.
        """
        raw = str(val).strip() if val is not None else ""
        if not raw:
            return None
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%d-%m-%Y %H:%M:%S",
            "%d/%m/%Y %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d-%m-%Y %H:%M",
        ):
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue
        try:
            return pd.to_datetime(raw, dayfirst=False).to_pydatetime()
        except Exception:
            return None

    @staticmethod
    def _parse_turn_id(val: Any, fallback: int) -> int:
        """
        Parse message_seq as int. Returns fallback (sequential counter)
        if val is absent or non-numeric, per spec requirement 7.
        """
        try:
            return int(str(val).strip())
        except (ValueError, TypeError):
            return fallback

    # ------------------------------------------------------------------
    # Private — summary
    # ------------------------------------------------------------------

    def _print_summary(self) -> None:
        sessions   = self._sessions
        total      = len(sessions)
        total_msgs = sum(len(s["messages"]) for s in sessions)
        flagged    = sum(1 for s in sessions if s["astrotalk_flagged"])

        dates    = [s["session_date"] for s in sessions if s["session_date"]]
        date_min = min(dates) if dates else "N/A"
        date_max = max(dates) if dates else "N/A"

        print()
        print("=" * 40)
        print("  AstroTalk DataLoader - Session Summary")
        print("=" * 40)
        print(f"  Total sessions  : {total}")
        print(f"  Total messages  : {total_msgs}")
        print(f"  Duplicates rmvd : {self._duplicates_removed}")
        print(f"  Date range      : {date_min} to {date_max}")
        print(f"  Sessions flagged by AstroTalk: {flagged}")
        print("=" * 40)
        print()


# ---------------------------------------------------------------------------
# Quick self-test — python engine/data_loader.py <path>
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AstroTalk DataLoader self-test")
    parser.add_argument("path", help="CSV file or folder containing CSV files")
    args = parser.parse_args()

    loader   = DataLoader(args.path)
    sessions = loader.load_sessions()
    if sessions:
        s = sessions[0]
        print(f"First session : {s['session_id']}  ({len(s['messages'])} messages)")
        print(f"  astrologer  : {s['astrologer_id']}")
        print(f"  date        : {s['session_date']}  lang={s['language_code']}")
        print(f"  flagged     : {s['astrotalk_flagged']}")
