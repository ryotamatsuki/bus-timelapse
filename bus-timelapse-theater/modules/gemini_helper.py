"""
Stub for Gemini narration generation.

The full Ehime Bus Time‑Lapse Theater specification includes an optional
feature that uses the Gemini API to generate text descriptions of the
bus operations.  In this prototype the function below simply returns a
placeholder string.  To enable real narration you would need to set
the ``GEMINI_API_KEY`` environment variable and implement an API call
to Gemini (or another LLM) within this module.

See the project documentation for more details.
"""

from __future__ import annotations


def get_comment(date: str, hour: int) -> str:
    """Return a placeholder comment for a given date and hour.

    Parameters
    ----------
    date : str
        Date in ``YYYY‑MM‑DD`` format.
    hour : int
        Hour of day (0–23).

    Returns
    -------
    str
        A human‑readable message describing the bus operations.  In this
        prototype the message is static.
    """
    return f"バスの運行状況: {date} {hour:02d}:00 時点で多数の路線が運行中です。"
