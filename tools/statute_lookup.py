"""APEX Statute Lookup Tool — resolves HRS and USC citations to full text via web search."""
import httpx
from typing import Optional

STATUTE_MAP = {
    "HRS §571-46": "https://www.capitol.hawaii.gov/hrscurrent/Vol12_Ch0501-0588/HRS0571/HRS_0571-0046.htm",
    "HRS §571-46.4": "https://www.capitol.hawaii.gov/hrscurrent/Vol12_Ch0501-0588/HRS0571/HRS_0571-0046_0004.htm",
    "HRS §601-7": "https://www.capitol.hawaii.gov/hrscurrent/Vol12_Ch0501-0588/HRS0601/HRS_0601-0007.htm",
    "HRS §657-7": "https://www.capitol.hawaii.gov/hrscurrent/Vol13_Ch0601-0675/HRS0657/HRS_0657-0007.htm",
    "42 U.S.C. §1983": "https://www.law.cornell.edu/uscode/text/42/1983",
    "18 U.S.C. §1961": "https://www.law.cornell.edu/uscode/text/18/1961",
    "18 U.S.C. §1962": "https://www.law.cornell.edu/uscode/text/18/1962",
    "18 U.S.C. §1964": "https://www.law.cornell.edu/uscode/text/18/1964",
    "28 U.S.C. §455": "https://www.law.cornell.edu/uscode/text/28/455",
}


def lookup_statute(citation: str) -> dict:
    """Return URL and description for a known statute citation."""
    normalized = citation.strip()
    if normalized in STATUTE_MAP:
        return {
            "citation": normalized,
            "url": STATUTE_MAP[normalized],
            "status": "found"
        }
    return {
        "citation": normalized,
        "url": f"https://www.law.cornell.edu/search/site/{normalized.replace(' ', '+')}",
        "status": "search_fallback"
    }


def get_sol_status(accrual_date: str, sol_years: int) -> dict:
    """Calculate days remaining on a statute of limitations."""
    from datetime import datetime, timezone
    accrual = datetime.fromisoformat(accrual_date).replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    from dateutil.relativedelta import relativedelta
    deadline = accrual + relativedelta(years=sol_years)
    days_remaining = (deadline - now).days
    return {
        "accrual_date": accrual_date,
        "sol_years": sol_years,
        "deadline": deadline.isoformat(),
        "days_remaining": days_remaining,
        "status": "URGENT" if days_remaining < 90 else "ACTIVE" if days_remaining > 0 else "EXPIRED"
    }
