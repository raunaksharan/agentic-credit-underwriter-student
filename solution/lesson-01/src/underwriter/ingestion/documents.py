"""Document loading and extraction.

Lesson 1: deterministic parsers for our clean synthetic formats, so the whole
pipeline runs with no LLM. Lesson 3 replaces `extract_payslip` with an LLM
extractor that returns the same `PayslipFacts` type for messy real documents,
which is why the output is a typed contract rather than a dict.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from pydantic import BaseModel

from underwriter.domain.models import DocumentType, LoanApplication

DATA_DIR = Path(__file__).resolve().parents[3] / "data"


class PayslipFacts(BaseModel):
    employee_name: str
    employer: str
    monthly_gross: float
    ytd_gross: float | None
    source: str


class BankTransaction(BaseModel):
    date: str
    description: str
    amount: float
    balance: float


class BankStatementFacts(BaseModel):
    transactions: list[BankTransaction]
    source: str

    def deposits_matching(self, keyword: str) -> list[BankTransaction]:
        k = keyword.lower()
        return [t for t in self.transactions if t.amount > 0 and k in t.description.lower()]


def load_application(path: str | Path) -> LoanApplication:
    return LoanApplication.model_validate_json(Path(path).read_text())


class DocumentStore:
    """Reads application documents. Swappable for blob storage in lesson 9."""

    def __init__(self, root: Path = DATA_DIR) -> None:
        self.root = root

    def read(self, rel_path: str) -> str:
        return (self.root / rel_path).read_text()

    def find(self, app: LoanApplication, doc_type: DocumentType) -> str | None:
        """Path of the first document of this type, or None if it was not submitted."""
        for d in app.documents:
            if d.doc_type == doc_type:
                return d.path
        return None


def _money(pattern: str, text: str) -> float | None:
    m = re.search(pattern + r"\s*([\d,]+\.?\d*)", text)
    return float(m.group(1).replace(",", "")) if m else None


def _field(label: str, text: str) -> str:
    m = re.search(rf"^{label}:\s*(.+)$", text, flags=re.MULTILINE)
    if not m:
        raise ValueError(f"field '{label}' not found")
    return m.group(1).strip()


def extract_payslip(text: str, source: str) -> PayslipFacts:
    gross = _money(r"Gross pay this period:", text)
    if gross is None:
        raise ValueError("gross pay not found on payslip")
    return PayslipFacts(
        employee_name=_field("Employee", text),
        employer=_field("Employer", text),
        monthly_gross=gross,
        ytd_gross=_money(r"Year-to-date gross:", text),
        source=source,
    )


def extract_bank_statement(text: str, source: str) -> BankStatementFacts:
    rows = csv.DictReader(io.StringIO(text))
    return BankStatementFacts(
        transactions=[BankTransaction(date=r["date"], description=r["description"],
                                      amount=float(r["amount"]), balance=float(r["balance"]))
                      for r in rows],
        source=source,
    )
