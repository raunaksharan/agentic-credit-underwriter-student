"""Credit bureau client.

Lesson 1: a file-backed mock behind an interface. Lesson 4 adds an HTTP
implementation with auth, timeouts and retries; lesson 6 tests what happens
when it fails. The contract that matters from day one: when data is not
available, raise `CreditDataUnavailable`. Never return a default score.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from underwriter.domain.models import CreditProfile
from underwriter.ingestion.documents import DATA_DIR


class CreditDataUnavailable(Exception):
    """The bureau could not return a report (no file, timeout, outage)."""


class CreditBureau(Protocol):
    def get_credit_report(self, national_id_last4: str, full_name: str) -> CreditProfile: ...


class FileCreditBureau:
    def __init__(self, path: Path = DATA_DIR / "bureau" / "credit_reports.json") -> None:
        self._records = json.loads(path.read_text())

    def get_credit_report(self, national_id_last4: str, full_name: str) -> CreditProfile:
        record = self._records.get(national_id_last4)
        if record is None:
            raise CreditDataUnavailable(
                f"No bureau record for applicant ending {national_id_last4}"
            )
        return CreditProfile.model_validate(record)
