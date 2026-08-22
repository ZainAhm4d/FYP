"""
Google Sheets connector — downloads a publicly shared sheet as a DataFrame.

The sheet must be shared as "Anyone with the link can view".
No OAuth credentials are required; uses the public CSV export URL.
"""
import re
from io import StringIO

import httpx
import pandas as pd


def _parse_sheet_url(url: str) -> tuple[str, str | None]:
    """Extract sheet ID and optional worksheet gid from a Google Sheets URL."""
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not match:
        raise ValueError(
            "Could not find a Google Sheet ID in that URL. "
            "Copy the full URL from the browser address bar."
        )
    sheet_id = match.group(1)
    gid_match = re.search(r"[#&?]gid=(\d+)", url)
    gid = gid_match.group(1) if gid_match else None
    return sheet_id, gid


def fetch_google_sheet(url: str) -> pd.DataFrame:
    """
    Download a publicly shared Google Sheet and return it as a DataFrame.

    Raises ValueError with a user-friendly message on any access or parse failure.
    """
    sheet_id, gid = _parse_sheet_url(url)
    export_url = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    )
    if gid:
        export_url += f"&gid={gid}"

    try:
        response = httpx.get(export_url, follow_redirects=True, timeout=30)
    except httpx.TimeoutException:
        raise ValueError(
            "Request timed out. Check your internet connection and try again."
        )
    except httpx.RequestError as exc:
        raise ValueError(f"Could not reach Google Sheets: {exc}")

    if response.status_code in (401, 403):
        raise ValueError(
            "Permission denied. Open the sheet, click Share, set access to "
            "'Anyone with the link → Viewer', then try again."
        )
    if response.status_code != 200:
        raise ValueError(
            f"Google Sheets returned HTTP {response.status_code}. "
            "Check that the URL is correct and the sheet is publicly accessible."
        )

    # If Google returns HTML it's a login/access-denied page, not CSV data
    ct = response.headers.get("content-type", "")
    if "text/html" in ct:
        raise ValueError(
            "Sheet is not publicly accessible. "
            "Open the sheet → Share → Change to 'Anyone with the link → Viewer', "
            "then try again."
        )

    try:
        df = pd.read_csv(StringIO(response.text))
    except Exception as exc:
        raise ValueError(f"Could not parse sheet as CSV: {exc}")

    if df.empty:
        raise ValueError("The sheet appears to be empty.")

    return df
