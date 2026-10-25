"""Generate the synthetic loan applications, documents and bureau records.

All people, employers and lenders here are fictional. Each application is
designed to exercise one path through the architecture; the expected outcome
is recorded in data/expected_outcomes.json and asserted in tests.

Run:  uv run python scripts/generate_sample_data.py
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

CASES = [
    {
        "id": "APP-001",
        "scenario": "Clean, well-qualified applicant",
        "name": "Priya Raman", "dob": "1990-03-14", "id4": "4821",
        "email": "priya.raman@example.com",
        "address": ("18 Alder Court", "Austin", "TX", "78701"),
        "employer": "Brightwave Software", "title": "Senior Software Engineer",
        "emp_type": "full_time", "start": "2019-06-01",
        "stated": 96000, "payslip_monthly": 8000,
        "loan": (15000, 36, "debt_consolidation", 0.119), "debt": 450,
        "docs": ["payslip", "bank_statement", "employment_letter"],
        "bureau": {"score": 742, "open_accounts": 4, "delinquencies_last_24m": 0,
                   "credit_history_months": 128, "reported_monthly_debt": 450},
        "expected": "APPROVE",
    },
    {
        "id": "APP-002",
        "scenario": "Post-loan DTI ~46%: inside the manual-review band",
        "name": "Marcus Bell", "dob": "1986-11-02", "id4": "7310",
        "email": "marcus.bell@example.com",
        "address": ("402 Hillcrest Ave", "Columbus", "OH", "43215"),
        "employer": "Keystone Logistics", "title": "Operations Supervisor",
        "emp_type": "full_time", "start": "2017-02-15",
        "stated": 62000, "payslip_monthly": 5166.67,
        "loan": (20000, 48, "home_improvement", 0.149), "debt": 1800,
        "docs": ["payslip", "bank_statement"],
        "bureau": {"score": 691, "open_accounts": 7, "delinquencies_last_24m": 0,
                   "credit_history_months": 160, "reported_monthly_debt": 1800},
        "expected": "MANUAL_REVIEW",
    },
    {
        "id": "APP-003",
        "scenario": "Credit bureau has no record: the system must not invent a score",
        "name": "Elena Duarte", "dob": "1995-07-21", "id4": "5562",
        "email": "elena.duarte@example.com",
        "address": ("77 Mission Row", "San Diego", "CA", "92101"),
        "employer": "Harborview Clinic", "title": "Registered Nurse",
        "emp_type": "full_time", "start": "2021-09-01",
        "stated": 78000, "payslip_monthly": 6500,
        "loan": (12000, 36, "auto_repair", 0.129), "debt": 300,
        "docs": ["payslip", "bank_statement"],
        "bureau": None,
        "expected": "MANUAL_REVIEW",
    },
    {
        "id": "APP-004",
        "scenario": "Stated income is ~43% higher than the payslip shows",
        "name": "Daniel Okafor", "dob": "1988-01-30", "id4": "9047",
        "email": "daniel.okafor@example.com",
        "address": ("9 Juniper Lane", "Atlanta", "GA", "30303"),
        "employer": "Crestline Retail Group", "title": "Store Manager",
        "emp_type": "full_time", "start": "2018-04-09",
        "stated": 120000, "payslip_monthly": 7000,
        "loan": (25000, 60, "debt_consolidation", 0.139), "debt": 900,
        "docs": ["payslip", "bank_statement"],
        "bureau": {"score": 705, "open_accounts": 5, "delinquencies_last_24m": 0,
                   "credit_history_months": 140, "reported_monthly_debt": 900},
        "expected": "MANUAL_REVIEW",
    },
    {
        "id": "APP-005",
        "scenario": "Low score and repeated delinquencies: clear policy decline",
        "name": "Sofia Lindqvist", "dob": "1992-05-18", "id4": "3388",
        "email": "sofia.lindqvist@example.com",
        "address": ("231 Birch Street", "Minneapolis", "MN", "55401"),
        "employer": "Northgate Hospitality", "title": "Front Desk Associate",
        "emp_type": "full_time", "start": "2022-01-10",
        "stated": 41000, "payslip_monthly": 3416.67,
        "loan": (8000, 24, "personal", 0.219), "debt": 520,
        "docs": ["payslip", "bank_statement"],
        "bureau": {"score": 561, "open_accounts": 6, "delinquencies_last_24m": 4,
                   "credit_history_months": 70, "reported_monthly_debt": 520},
        "expected": "DECLINE",
    },
    {
        "id": "APP-006",
        "scenario": "Name on payslip does not match the applicant",
        "name": "James Whitfield", "dob": "1984-09-09", "id4": "6125",
        "email": "james.whitfield@example.com",
        "address": ("55 Orchard Way", "Denver", "CO", "80202"),
        "employer": "Summit Engineering", "title": "Project Engineer",
        "emp_type": "full_time", "start": "2016-08-22",
        "stated": 88000, "payslip_monthly": 7333.33,
        "payslip_name": "James Whitmore",
        "loan": (18000, 36, "personal", 0.124), "debt": 600,
        "docs": ["payslip", "bank_statement"],
        "bureau": {"score": 718, "open_accounts": 3, "delinquencies_last_24m": 0,
                   "credit_history_months": 190, "reported_monthly_debt": 600},
        "expected": "MANUAL_REVIEW",
    },
    {
        "id": "APP-007",
        "scenario": "Self-employed applicant without the required tax return",
        "name": "Aisha Karim", "dob": "1991-12-03", "id4": "2290",
        "email": "aisha.karim@example.com",
        "address": ("14 Lakeview Drive", "Chicago", "IL", "60601"),
        "employer": "Karim Design Studio", "title": "Owner",
        "emp_type": "self_employed", "start": "2020-03-01",
        "stated": 70000, "payslip_monthly": None,
        "loan": (10000, 36, "business_equipment", 0.139), "debt": 400,
        "docs": ["bank_statement"],
        "bureau": {"score": 702, "open_accounts": 4, "delinquencies_last_24m": 0,
                   "credit_history_months": 110, "reported_monthly_debt": 400},
        "expected": "MANUAL_REVIEW",
    },
    {
        "id": "APP-008",
        "scenario": "DTI ~44%: the agent stub approves, the decision engine overrides",
        "name": "Hannah Brooks", "dob": "1989-04-27", "id4": "8406",
        "email": "hannah.brooks@example.com",
        "address": ("610 Cedar Point", "Raleigh", "NC", "27601"),
        "employer": "Piedmont Health Systems", "title": "Billing Analyst",
        "emp_type": "full_time", "start": "2020-11-02",
        "stated": 72000, "payslip_monthly": 6000,
        "loan": (15000, 36, "debt_consolidation", 0.129), "debt": 2130,
        "docs": ["payslip", "bank_statement"],
        "bureau": {"score": 705, "open_accounts": 6, "delinquencies_last_24m": 0,
                   "credit_history_months": 132, "reported_monthly_debt": 2130},
        "expected": "MANUAL_REVIEW",
    },
]

STATEMENT_END = date(2026, 9, 30)


def payslip(c: dict) -> str:
    monthly = c["payslip_monthly"]
    months_ytd = 9
    return f"""PAY STATEMENT
Employer: {c["employer"]}
Employee: {c.get("payslip_name", c["name"])}
Job title: {c["title"]}
Pay period: 2026-09-01 to 2026-09-30
Pay frequency: monthly

Gross pay this period: {monthly:,.2f}
Federal tax: {monthly * 0.14:,.2f}
State tax: {monthly * 0.05:,.2f}
Social security & medicare: {monthly * 0.0765:,.2f}
Retirement 401(k): {monthly * 0.05:,.2f}
Net pay this period: {monthly * (1 - 0.14 - 0.05 - 0.0765 - 0.05):,.2f}

Year-to-date gross: {monthly * months_ytd:,.2f}
"""


def bank_statement(c: dict) -> str:
    rows = ["date,description,amount,balance"]
    balance = 3200.00
    if c["payslip_monthly"]:
        net = round(c["payslip_monthly"] * (1 - 0.14 - 0.05 - 0.0765 - 0.05), 2)
        deposit_desc = f"PAYROLL {c['employer'].upper()}"
    else:  # self-employed: irregular client payments
        net = None
        deposit_desc = "CLIENT PAYMENT"
    for m in (7, 8, 9):
        start = date(2026, m, 1)
        if net is not None:
            entries = [(start, deposit_desc, net)]
        else:
            entries = [(start + timedelta(days=3), deposit_desc, 2400.00 + 300 * m),
                       (start + timedelta(days=17), deposit_desc, 1650.00 + 120 * m)]
        entries += [
            (start + timedelta(days=2), "RENT / MORTGAGE", -round(c["stated"] / 12 * 0.25, 2)),
            (start + timedelta(days=9), "GROCERY MART", -412.35),
            (start + timedelta(days=14), "EXISTING LOAN PAYMENTS", -float(c["debt"])),
            (start + timedelta(days=21), "UTILITIES", -186.40),
        ]
        for d, desc, amt in sorted(entries):
            balance = round(balance + amt, 2)
            rows.append(f"{d.isoformat()},{desc},{amt:.2f},{balance:.2f}")
    return "\n".join(rows) + "\n"


def employment_letter(c: dict) -> str:
    return f"""{c["employer"]}
Human Resources

To whom it may concern,

This letter confirms that {c["name"]} has been employed with {c["employer"]} as
{c["title"]} on a {c["emp_type"].replace("_", " ")} basis since {c["start"]}.
Current annual base salary: {c["payslip_monthly"] * 12:,.2f}

Issued: 2026-10-01
"""


def main() -> None:
    bureau: dict[str, dict] = {}
    expected: dict[str, dict] = {}
    for c in CASES:
        doc_dir = DATA / "documents" / c["id"]
        doc_dir.mkdir(parents=True, exist_ok=True)
        refs = []
        writers = {
            "payslip": ("payslip.txt", payslip),
            "bank_statement": ("bank_statement.csv", bank_statement),
            "employment_letter": ("employment_letter.txt", employment_letter),
        }
        for doc in c["docs"]:
            fname, fn = writers[doc]
            (doc_dir / fname).write_text(fn(c))
            refs.append({"doc_type": doc, "path": f"documents/{c['id']}/{fname}"})

        line1, city, state, postal = c["address"]
        amount, term, purpose, rate = c["loan"]
        app = {
            "application_id": c["id"],
            "submitted_at": "2026-10-05T10:15:00Z",
            "applicant": {
                "full_name": c["name"], "date_of_birth": c["dob"],
                "national_id_last4": c["id4"], "email": c["email"],
                "address": {"line1": line1, "city": city, "state": state,
                            "postal_code": postal},
            },
            "employment": {
                "employer_name": c["employer"], "job_title": c["title"],
                "employment_type": c["emp_type"], "start_date": c["start"],
                "stated_annual_income": c["stated"],
            },
            "loan": {"amount": amount, "term_months": term, "purpose": purpose,
                     "annual_interest_rate": rate},
            "existing_monthly_debt_payments": c["debt"],
            "documents": refs,
        }
        (DATA / "applications" / f"{c['id']}.json").write_text(json.dumps(app, indent=2) + "\n")
        if c["bureau"] is not None:
            bureau[c["id4"]] = c["bureau"]
        expected[c["id"]] = {"scenario": c["scenario"], "expected": c["expected"]}

    (DATA / "bureau" / "credit_reports.json").write_text(json.dumps(bureau, indent=2) + "\n")
    (DATA / "expected_outcomes.json").write_text(
        json.dumps(expected, indent=2) + "\n"
    )
    print(f"Generated {len(CASES)} applications")


if __name__ == "__main__":
    main()
