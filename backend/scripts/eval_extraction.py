"""Measure extraction accuracy against emails you label by hand.

Step 1, export a sample (about 50 AI-judged emails + 20 the keyword filter dropped):
    python -m scripts.eval_extraction export --email you@example.com

Step 2, open eval/to_label.csv, fill the true_* columns, save as eval/labeled.csv:
    true_is_app     yes / no   (is this really about an application you submitted?)
    true_company    the right company, or "=" if pred_company is right
    true_title      the right job title, or "=" if pred_title is right ("" if none)
    true_status     applied / interview / offer / rejected / withdrawn / unknown, or "="
  For rows where source == "filtered", only true_is_app is needed.

Step 3, score:
    python -m scripts.eval_extraction score
"""

import argparse
import csv
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.services.matching import company_words
from scripts.common import EVAL_DIR, pct

FIELDS = [
    "message_id", "source", "subject", "sender", "snippet",
    "pred_is_app", "pred_company", "pred_title", "pred_status",
    "true_is_app", "true_company", "true_title", "true_status",
]

# --------------------------------------------------------------------- export


def export(email: str, n: int, filtered: int, seed: int) -> None:
    from app.db import get_db
    from app.services import gmail_client, heuristics
    from app.services.crypto import decrypt_token
    from app.services.email_extraction import classify_and_extract
    from scripts.common import load_user

    user = load_user(email)
    token = decrypt_token(user["google_refresh_token_encrypted"])
    rows = (
        get_db().table("processed_emails").select("gmail_message_id, classification")
        .eq("user_id", user["id"]).execute().data or []
    )
    if not rows:
        sys.exit("No processed emails yet. Run scripts.resume_metrics first.")

    rng = random.Random(seed)
    positives = [r["gmail_message_id"] for r in rows if r["classification"] == "job_application"]
    negatives = [r["gmail_message_id"] for r in rows if r["classification"] != "job_application"]
    rng.shuffle(positives)
    rng.shuffle(negatives)

    # Aim for ~70% emails the AI accepted, the rest emails it rejected, so both
    # precision and recall get evidence. Negatives that fail the keyword filter
    # never reached the AI; they fill the separate "filtered" bucket instead.
    want_pos = min(len(positives), round(n * 0.7))
    # Fetch in batches on one login. Negatives are over-fetched (capped) because
    # only some of them reached the AI; the rest feed the "filtered" bucket.
    neg_pool = negatives[: min(len(negatives), 3 * (n + filtered))]
    fetched = gmail_client.get_message_summaries(token, positives + neg_pool)
    judged: list[dict] = [fetched[m] for m in positives[:want_pos] if m in fetched]
    dropped: list[dict] = []

    for message_id in neg_pool:
        summary = fetched.get(message_id)
        if summary is None:
            continue
        if heuristics.is_candidate_email(summary["subject"], summary["sender"]):
            if len(judged) < n:
                judged.append(summary)
        elif len(dropped) < filtered:
            dropped.append(summary)

    for message_id in positives[want_pos:]:  # top up if there weren't enough negatives
        if len(judged) >= n:
            break
        if message_id in fetched:
            judged.append(fetched[message_id])

    out_rows = []
    print(f"Re-running extraction on {len(judged)} emails...")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(
            lambda e: classify_and_extract(e["subject"], e["sender"], e["body_text"]), judged))
    for s, ex in zip(judged, results):
        out_rows.append({
            "message_id": s["id"], "source": "ai", "subject": s["subject"],
            "sender": s["sender"], "snippet": s["snippet"],
            "pred_is_app": "yes" if ex.is_job_application_email else "no",
            "pred_company": ex.company or "", "pred_title": ex.job_title or "",
            "pred_status": ex.status,
        })
    for s in dropped:
        out_rows.append({
            "message_id": s["id"], "source": "filtered", "subject": s["subject"],
            "sender": s["sender"], "snippet": s["snippet"], "pred_is_app": "no",
        })
    rng.shuffle(out_rows)

    EVAL_DIR.mkdir(exist_ok=True)
    out = EVAL_DIR / "to_label.csv"
    # utf-8-sig so Excel opens it with the right encoding.
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for row in out_rows:
            writer.writerow({k: row.get(k, "") for k in FIELDS})
    print(f"Wrote {len(judged)} AI-judged + {len(dropped)} filtered rows to {out}")
    print("Fill the true_* columns, save as eval/labeled.csv, then run `score`.")


# ---------------------------------------------------------------------- score

def normalize(value: str, *, company: bool = False) -> str:
    if company:
        return " ".join(company_words(value))
    return " ".join(re.sub(r"[^\w\s]", " ", value.lower()).split())


def _yes(value: str) -> bool | None:
    v = value.strip().lower()
    if v in {"yes", "y", "1", "true"}:
        return True
    if v in {"no", "n", "0", "false"}:
        return False
    return None


def _truth(row: dict, field: str) -> str:
    value = row.get(f"true_{field}", "").strip()
    return row.get(f"pred_{field}", "") if value == "=" else value


def score(path: Path) -> dict:
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    tp = fp = fn = tn = 0
    company_ok = title_ok = status_ok = extracted = 0
    filtered_total = filtered_missed = unlabeled = 0

    for row in rows:
        truth = _yes(row.get("true_is_app", ""))
        if truth is None:
            unlabeled += 1
            continue
        if row["source"] == "filtered":
            filtered_total += 1
            filtered_missed += truth
            continue

        pred = row["pred_is_app"] == "yes"
        if pred and truth:
            tp += 1
            extracted += 1
            company_ok += normalize(row["pred_company"], company=True) == normalize(
                _truth(row, "company"), company=True)
            title_ok += normalize(row["pred_title"]) == normalize(_truth(row, "title"))
            status_ok += row["pred_status"] == _truth(row, "status").lower()
        elif pred:
            fp += 1
        elif truth:
            fn += 1
        else:
            tn += 1

    judged = tp + fp + fn + tn
    print(f"Scored {judged} AI-judged + {filtered_total} filtered rows"
          + (f" ({unlabeled} unlabeled rows skipped)" if unlabeled else ""))
    print("\nIs it a job-application email?")
    print(f"  Accuracy:  {pct(tp + tn, judged)}")
    print(f"  Precision: {pct(tp, tp + fp)}")
    print(f"  Recall:    {pct(tp, tp + fn)}")
    print("\nField extraction (on correctly detected applications)")
    print(f"  Company:   {pct(company_ok, extracted)}")
    print(f"  Job title: {pct(title_ok, extracted)}")
    print(f"  Status:    {pct(status_ok, extracted)}")
    print("\nKeyword pre-filter")
    print(f"  Real applications it wrongly dropped: {pct(filtered_missed, filtered_total)}")

    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "company_ok": company_ok,
            "title_ok": title_ok, "status_ok": status_ok, "extracted": extracted,
            "filtered_total": filtered_total, "filtered_missed": filtered_missed}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_exp = sub.add_parser("export")
    p_exp.add_argument("--email", required=True)
    p_exp.add_argument("--n", type=int, default=50, help="AI-judged emails to sample")
    p_exp.add_argument("--filtered", type=int, default=20,
                       help="keyword-filter-dropped emails to sample")
    p_exp.add_argument("--seed", type=int, default=7)
    p_score = sub.add_parser("score")
    p_score.add_argument("--file", type=Path, default=EVAL_DIR / "labeled.csv")
    args = parser.parse_args()

    if args.cmd == "export":
        export(args.email, args.n, args.filtered, args.seed)
    else:
        score(args.file)


if __name__ == "__main__":
    main()
