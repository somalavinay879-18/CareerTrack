"""Pure analytics functions (no Flask, no database), so they are easy to test."""
from collections import Counter
from datetime import date, timedelta

STATUSES = ("Applied", "Interview", "Accepted", "Rejected")


def parse_date(value):
    """Return a date for 'YYYY-MM-DD' strings, otherwise None."""
    try:
        return date.fromisoformat(str(value).strip())
    except (ValueError, TypeError):
        return None


def _pct(part, whole):
    return round(100 * part / whole) if whole else 0


def summary(rows):
    """Counts and conversion rates for a list of application rows."""
    counts = Counter(r["status"] for r in rows)
    total = len(rows)
    interview = counts["Interview"]
    accepted = counts["Accepted"]
    rejected = counts["Rejected"]
    reached_interview = interview + accepted
    responded = interview + accepted + rejected
    return {
        "total": total,
        "applied": counts["Applied"],
        "interview": interview,
        "accepted": accepted,
        "rejected": rejected,
        # Share of applications that got any answer (interview, offer or rejection)
        "response_rate": _pct(responded, total),
        # Share that reached the interview stage or later
        "interview_rate": _pct(reached_interview, total),
        # Share that ended in an offer
        "offer_rate": _pct(accepted, total),
        "funnel": [
            ("Applications", total),
            ("Interview or later", reached_interview),
            ("Offers", accepted),
        ],
    }


def weekly_counts(rows, weeks=12, today=None):
    """Applications per week for the last `weeks` weeks (weeks start on Monday)."""
    today = today or date.today()
    this_monday = today - timedelta(days=today.weekday())
    starts = [this_monday - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]
    counts = {s: 0 for s in starts}
    for r in rows:
        d = parse_date(r["date_applied"])
        if d is None:
            continue
        monday = d - timedelta(days=d.weekday())
        if monday in counts:
            counts[monday] += 1
    labels = [s.strftime("%d %b") for s in starts]
    return labels, [counts[s] for s in starts]


def by_source(rows, top=8):
    """Applications per source, most common first."""
    counter = Counter((r["source"] or "Unknown") for r in rows)
    items = counter.most_common(top)
    return [k for k, _ in items], [v for _, v in items]
