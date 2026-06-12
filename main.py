"""
main.py
Full pipeline runner for the AstroTalk Content Intelligence Engine.

Usage examples:
  python main.py                          # run all 50 sessions
  python main.py --session 294055364      # run one session
  python main.py --category "Explicit"    # run one category
  python main.py --limit 5               # run first 5 sessions
  python main.py --resume                # skip already-processed sessions
  python main.py --limit 3 --dry-run     # verify filters only (no API calls)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import glob
from datetime import datetime
from pathlib import Path

import colorama
from colorama import Fore, Style

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine.data_loader         import DataLoader
from engine.consultant_analyser import ConsultantAnalyser
from engine.classifier          import LLMClassifier
from engine.aggregator          import SessionAggregator, SessionResult

# ---------------------------------------------------------------------------
# Colour aliases
# ---------------------------------------------------------------------------

RED_TXT   = Fore.RED    + Style.BRIGHT
AMBER_TXT = Fore.YELLOW + Style.BRIGHT
GREEN_TXT = Fore.GREEN  + Style.BRIGHT
CYAN_TXT  = Fore.CYAN   + Style.BRIGHT
RESET     = Style.RESET_ALL

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

from config import OUTPUTS_DIR

# Rough cost model for Claude Sonnet ($/1M tokens)
_COST_INPUT_PER_M  = 3.00
_COST_OUTPUT_PER_M = 15.00
_EST_INPUT_PER_CHUNK  = 3_400   # tokens
_EST_OUTPUT_PER_CHUNK = 250     # tokens


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="AstroTalk Content Intelligence Engine — GT Bharat Pilot",
    )
    p.add_argument(
        "--session", type=int, metavar="ORDER_ID",
        help="Run a single session by order_id",
    )
    p.add_argument(
        "--category", type=str,
        choices=["Explicit", "Borderline", "Moderate", "False Positives"],
        help="Run only sessions of this human category",
    )
    p.add_argument(
        "--limit", type=int, metavar="N",
        help="Run only the first N sessions",
    )
    p.add_argument(
        "--resume", action="store_true",
        help="Skip sessions already saved in outputs/",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Verify filters and data loading only — no API calls",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def load_existing_results() -> dict[int, dict]:
    """Scan outputs/ for existing {order_id}_result.json files."""
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    existing: dict[int, dict] = {}
    for fp in OUTPUTS_DIR.glob("*_result.json"):
        try:
            oid = int(fp.stem.replace("_result", ""))
            with open(fp, encoding="utf-8") as fh:
                existing[oid] = json.load(fh)
        except Exception:
            pass
    return existing


def save_result(result: SessionResult, session_metadata: dict) -> Path:
    """Save SessionResult + original metadata to outputs/{order_id}_result.json."""
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    aggregator = SessionAggregator()
    payload = aggregator.to_dict(result)
    # Attach original GT dataset fields
    payload["human_category"] = session_metadata.get("category", "")
    payload["human_action"]   = session_metadata.get("action", "")
    payload["human_feedback"] = session_metadata.get("human_feedback", "")
    payload["ai_reason"]      = session_metadata.get("ai_reason", "")
    payload["date"]           = session_metadata.get("date", "")

    out_path = OUTPUTS_DIR / f"{result.session_id}_result.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return out_path


# ---------------------------------------------------------------------------
# Live display
# ---------------------------------------------------------------------------

def _severity_icon(severity: str) -> str:
    return {"Red": "🔴", "Amber": "🟡", "Green": "🟢"}.get(severity, "⚪")


def _match_symbol(gt_severity: str, human_category: str) -> str:
    """
    ✓ = GT verdict aligns with human label
    ~ = both non-Green but different severity (partial)
    ✗ = GT says Green but human said violation, or vice versa
    """
    mapped = SessionAggregator().map_label_to_severity(human_category)
    if mapped == "Unknown":
        return "?"
    if gt_severity == mapped:
        return "✓"
    # Both non-Green but different level
    if gt_severity != "Green" and mapped != "Green":
        return "~"
    return "✗"


def print_live_table_row(
    session_id:      int,
    human_category:  str,
    gt_severity:     str,
    match:           str,
    action:          str,
    chunk_count:     int,
    elapsed_seconds: float,
) -> None:
    mins  = int(elapsed_seconds) // 60
    secs  = int(elapsed_seconds) % 60
    time_str = f"{mins}m {secs:02d}s"

    sev_colour = {"Red": RED_TXT, "Amber": AMBER_TXT, "Green": GREEN_TXT}.get(
        gt_severity, RESET
    )
    match_colour = {
        "✓": GREEN_TXT, "~": AMBER_TXT, "✗": RED_TXT
    }.get(match, RESET)

    icon = _severity_icon(gt_severity)

    print(
        f"  {session_id} │ "
        f"{human_category:<15} │ "
        f"{sev_colour}{icon} {gt_severity:<5}{RESET} │ "
        f"{match_colour}{match}{RESET} │ "
        f"{action:<18} │ "
        f"{chunk_count:>3} chunks │ "
        f"{time_str}"
    )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def compute_final_stats(outputs_dir: str) -> dict:
    """
    Compute summary stats from ALL result files in outputs/.
    Used at the end of run_pipeline() so --resume runs show complete totals.
    """
    
    all_results = []
    for f in glob.glob(f"{outputs_dir}/*_result.json"):
        try:
            with open(f, encoding="utf-8") as fh:
                all_results.append(json.load(fh))
        except Exception:
            pass

    total = len(all_results)
    red   = sum(1 for r in all_results if r.get("final_severity") == "Red")
    amber = sum(1 for r in all_results if r.get("final_severity") == "Amber")
    green = sum(1 for r in all_results if r.get("final_severity") == "Green")

    fp_results = [r for r in all_results
                  if r.get("human_category") == "False Positives"]
    fp_total_n = len(fp_results)
    fp_correct = sum(1 for r in fp_results if r.get("final_severity") == "Green")
    fp_wrong   = fp_total_n - fp_correct

    exact = partial = mismatch = 0
    for r in all_results:
        cat    = r.get("human_category", "")
        sev    = r.get("final_severity", "")
        action = r.get("human_action", "")

        if cat in ("Explicit", "Borderline"):
            if sev == "Red":       exact    += 1
            elif sev == "Amber":   partial  += 1
            else:                  mismatch += 1
        elif cat == "False Positives":
            if sev == "Green":     exact    += 1
            elif sev == "Amber":   partial  += 1
            else:                  mismatch += 1
        elif cat == "Moderate":
            if "Not Required" in action:
                if sev in ("Green", "Amber"): exact   += 1
                else:                         partial += 1
            else:
                if sev in ("Red", "Amber"):   exact    += 1
                else:                         mismatch += 1

    total_chunks  = sum(r.get("total_chunks", 0) for r in all_results)
    est_cost_usd  = (total_chunks * 3_400 / 1_000_000) * 3.0
    est_cost_inr  = est_cost_usd * 84

    return {
        "total":         total,
        "red":           red,
        "amber":         amber,
        "green":         green,
        "fp_total":      fp_total_n,
        "fp_correct":    fp_correct,
        "fp_wrong":      fp_wrong,
        "exact":         exact,
        "partial":       partial,
        "mismatch":      mismatch,
        "total_chunks":  total_chunks,
        "est_cost_usd":  est_cost_usd,
        "est_cost_inr":  est_cost_inr,
    }


def run_pipeline(sessions: list[dict], resume: bool = False) -> list[dict]:
    """
    Main execution loop.  Returns list of result dicts (for testing / chaining).
    """
    existing   = load_existing_results() if resume else {}
    analyser   = ConsultantAnalyser()
    clf        = LLMClassifier()
    aggregator = SessionAggregator()

    total     = len(sessions)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── Header ─────────────────────────────────────────────────────────
    print(CYAN_TXT + "═" * 60 + RESET)
    print(CYAN_TXT + "  AstroTalk Content Intelligence Engine" + RESET)
    print(CYAN_TXT + "  GT Bharat — Pilot Run" + RESET)
    print(CYAN_TXT + f"  {timestamp} — {total} session(s) queued" + RESET)
    print(CYAN_TXT + "═" * 60 + RESET)
    print()

    # ── Running totals ──────────────────────────────────────────────────
    counts   = {"Red": 0, "Amber": 0, "Green": 0}
    match_c  = {"exact": 0, "partial": 0, "mismatch": 0}
    fp_total = sum(1 for s in sessions if s.get("category") == "False Positives")
    fp_green = 0
    total_chunks = 0
    all_results:  list[dict] = []
    pipeline_start = time.time()

    for session in sessions:
        oid      = session.get("order_id")
        category = session.get("category", "")
        t_start  = time.time()

        # ── Resume check ───────────────────────────────────────────────
        if resume and oid in existing:
            print(f"  {oid} │ {category:<15} │ [SKIPPED — already processed]")
            existing_r = existing[oid]
            all_results.append(existing_r)
            counts[existing_r.get("final_severity", "Green")] = (
                counts.get(existing_r.get("final_severity", "Green"), 0) + 1
            )
            continue

        try:
            # ── Step A — Consultant analysis ───────────────────────────
            profile = analyser.analyse(session)

            # ── Step B — LLM classification ────────────────────────────
            classification = clf.classify_session(session)

            # ── Step C — Aggregation ───────────────────────────────────
            result = aggregator.aggregate(
                classification,
                profile,
                human_label=category,
                existing_engine_severity=aggregator.map_label_to_severity(category),
            )

            # ── Step D — Save ──────────────────────────────────────────
            save_result(result, session)

            # ── Step E — Track stats ───────────────────────────────────
            sev    = result.final_severity
            counts[sev] = counts.get(sev, 0) + 1
            total_chunks += classification.total_chunks
            if category == "False Positives" and sev == "Green":
                fp_green += 1

            match = _match_symbol(sev, category)
            if match == "✓":
                match_c["exact"]   += 1
            elif match == "~":
                match_c["partial"] += 1
            else:
                match_c["mismatch"] += 1

            elapsed = time.time() - t_start
            print_live_table_row(
                session_id=      oid,
                human_category=  category,
                gt_severity=     sev,
                match=           match,
                action=          result.recommended_action,
                chunk_count=     classification.total_chunks,
                elapsed_seconds= elapsed,
            )

            result_dict = aggregator.to_dict(result)
            result_dict["human_category"] = category
            all_results.append(result_dict)

        except Exception as exc:
            elapsed = time.time() - t_start
            print(
                f"  {RED_TXT}FAILED{RESET}  {oid} │ {category} │ "
                f"{type(exc).__name__}: {exc} │ "
                f"{int(elapsed)}s"
            )
            all_results.append({
                "session_id":   oid,
                "final_severity": "FAILED",
                "human_category": category,
                "error":        str(exc),
            })

        time.sleep(0.5)

    elapsed_total = time.time() - pipeline_start
    stats = compute_final_stats(str(OUTPUTS_DIR))
    print_final_summary(stats, elapsed_total)
    return all_results


def print_final_summary(stats: dict, elapsed: float) -> None:
    total = stats["total"]
    mins  = int(elapsed) // 60
    secs  = int(elapsed) % 60
    pct   = lambda n: f"{n/total*100:.0f}%" if total else "0%"

    print()
    print(CYAN_TXT + "═" * 60 + RESET)
    print(CYAN_TXT + "  PILOT RUN COMPLETE" + RESET)
    print(CYAN_TXT + "═" * 60 + RESET)
    print(f"  Sessions processed   : {total}")
    print()
    print("  GT ENGINE VERDICTS:")
    print(f"  {RED_TXT}  Red   {RESET}: {stats['red']:3d} ({pct(stats['red'])})")
    print(f"  {AMBER_TXT}  Amber {RESET}: {stats['amber']:3d} ({pct(stats['amber'])})")
    print(f"  {GREEN_TXT}  Green {RESET}: {stats['green']:3d} ({pct(stats['green'])})")
    print()
    print("  MATCH VS HUMAN LABELS:")
    print(f"    {GREEN_TXT}Exact match  {RESET}: {stats['exact']}/{total}")
    print(f"    {AMBER_TXT}Partial match{RESET}: {stats['partial']}/{total}")
    print(f"    {RED_TXT}Mismatch     {RESET}: {stats['mismatch']}/{total}")
    print()
    print("  FALSE POSITIVE PERFORMANCE:")
    print(f"    Human FP cases        : {stats['fp_total']}")
    print(f"    {GREEN_TXT}GT correctly Green{RESET}    : "
          f"{stats['fp_correct']}/{stats['fp_total']}  ← KEY METRIC")
    print(f"    {RED_TXT}GT wrongly flagged{RESET}    : "
          f"{stats['fp_wrong']}/{stats['fp_total']}")
    print()
    print("  ESTIMATED API COST:")
    print(f"    Total chunks          : {stats['total_chunks']}")
    print(f"    Est. input tokens     : {stats['total_chunks'] * 3_400:,}")
    print(f"    Est. cost             : "
          f"${stats['est_cost_usd']:.2f}  (₹{stats['est_cost_inr']:.0f})")
    print()
    print(f"  Elapsed time           : {mins}m {secs:02d}s")
    print(f"  Results saved to       : {OUTPUTS_DIR}")
    print(CYAN_TXT + "═" * 60 + RESET)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    colorama.init()
    args = parse_args()

    loader   = DataLoader()
    sessions = loader.load()

    # Ensure sessions.json is up to date
    loader.save_processed()

    # Apply filters
    if args.session:
        sessions = [s for s in sessions if s["order_id"] == args.session]
    if args.category:
        sessions = [s for s in sessions if s["category"] == args.category]
    if args.limit:
        sessions = sessions[: args.limit]

    # ── Dry-run validation ──────────────────────────────────────────────
    if args.dry_run:
        print()
        print(CYAN_TXT + "DRY RUN — verifying filters only (no API calls)" + RESET)
        print()

        all_sessions = loader.load()   # full set for filter checks

        # Check 1 — all sessions loaded
        assert len(all_sessions) == 50, \
            f"Expected 50 sessions, got {len(all_sessions)}"
        print(f"  ✓  DataLoader loaded {len(all_sessions)} sessions")

        # Check 2 — --session filter
        filtered_one = [s for s in all_sessions
                        if s["order_id"] == 294055364]
        assert len(filtered_one) == 1, \
            f"--session filter failed: {len(filtered_one)} results"
        print(f"  ✓  --session 294055364 → {len(filtered_one)} session")

        # Check 3 — --category filter
        filtered_fp = [s for s in all_sessions
                       if s["category"] == "False Positives"]
        assert len(filtered_fp) == 13, \
            f"--category filter failed: {len(filtered_fp)} results"
        print(f"  ✓  --category 'False Positives' → {len(filtered_fp)} sessions")

        # Check 4 — --limit filter
        filtered_3 = all_sessions[:3]
        assert len(filtered_3) == 3, \
            f"--limit filter failed: {len(filtered_3)} results"
        print(f"  ✓  --limit 3 → {len(filtered_3)} sessions")

        print()
        print(GREEN_TXT +
              f"Dry run OK — ready to process {len(sessions)} session(s)" +
              RESET)
        sys.exit(0)

    # ── Check API key before long run ───────────────────────────────────
    from config import USE_CLAUDE_API
    if USE_CLAUDE_API and not os.environ.get("ANTHROPIC_API_KEY"):
        print(RED_TXT +
              "ERROR: ANTHROPIC_API_KEY environment variable not set.\n"
              "Run: $env:ANTHROPIC_API_KEY='sk-ant-...'" +
              RESET)
        sys.exit(1)

    run_pipeline(sessions, resume=args.resume)
