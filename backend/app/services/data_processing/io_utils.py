"""
Encoding-aware tabular file reader (CP-07).

Upload validation accepts both UTF-8 and Latin-1/cp1252 CSVs, but a plain
`pd.read_csv(path)` assumes UTF-8 and either crashes with UnicodeDecodeError
or silently mojibakes ("Müller" -> "MÃ¼ller") on the very files we accepted.

This module is the SINGLE entry point for reading a raw dataset file from
disk. Every code path that opens an uploaded/original dataset file must go
through `read_tabular` / `read_tabular_ex` so behaviour is identical
everywhere.
"""
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

# Encodings tried in order for CSV:
#   utf-8-sig : UTF-8, transparently stripping a byte-order mark if present
#   utf-8     : plain UTF-8
#   cp1252    : Windows-1252, the default Excel/Windows "ANSI" CSV export
#   latin-1   : ISO-8859-1 — maps all 256 byte values, so it NEVER raises;
#               guaranteed last-resort that always decodes (may mojibake, but
#               only reached when the file is genuinely neither UTF-8 nor cp1252)
_CSV_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")


def read_tabular_ex(path, **read_kwargs) -> Tuple[pd.DataFrame, str]:
    """
    Read a CSV / Excel dataset file into a DataFrame.

    Returns (df, encoding_used). For Excel the encoding is reported as
    "binary". Extra kwargs are forwarded to the underlying pandas reader.

    UTF-8 is always tried before cp1252, so a valid UTF-8 file is never
    misdecoded; only files that fail UTF-8 fall through to the Windows
    encodings.
    """
    p = Path(path)
    ext = p.suffix.lower()

    if ext in (".xlsx", ".xls"):
        return pd.read_excel(p, **read_kwargs), "binary"

    last_err: Optional[Exception] = None
    for enc in _CSV_ENCODINGS:
        try:
            return pd.read_csv(p, encoding=enc, **read_kwargs), enc
        except (UnicodeDecodeError, UnicodeError) as e:
            last_err = e
            continue
        # A non-encoding parse error (bad delimiter, empty file, …) will not be
        # fixed by trying another encoding — let it propagate.
    # latin-1 should always succeed, so this is defensive only.
    raise last_err if last_err else ValueError(f"Could not read tabular file: {path}")


def read_tabular(path, **read_kwargs) -> pd.DataFrame:
    """Read a CSV / Excel dataset file (encoding-aware). Convenience wrapper."""
    df, _enc = read_tabular_ex(path, **read_kwargs)
    return df
