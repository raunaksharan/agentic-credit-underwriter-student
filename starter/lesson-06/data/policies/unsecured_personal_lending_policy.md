# Meridian Digital Lending — Unsecured Personal Lending Policy

Version 3.2 · Effective 2026-07-01 · Owner: Credit Risk Committee

> Meridian Digital Lending is a fictional lender used for teaching. This policy
> is the source of truth that the underwriting platform retrieves from (lesson 2)
> and that the deterministic decision engine encodes (lesson 1).

## 1. Scope

1.1 This policy governs unsecured personal loans of USD 1,000 to USD 50,000 with
terms of 12 to 72 months.

1.2 Automated recommendations are advisory. The final decision is produced by the
policy decision engine and, where this policy requires, by a human underwriter.

## 2. Eligibility and employment

2.1 Applicants must be at least 21 years old on the application date.

2.2 Salaried applicants must have at least 6 months of continuous employment with
their current employer. Shorter tenure requires manual review.

2.3 Self-employed applicants must have operated the business for at least 24
months and must provide a tax return (see 5.3).

## 3. Credit score

3.1 Applicants with a bureau credit score below **580** are declined.

3.2 Applicants with a score from **580 to 659** inclusive require manual review.

3.3 Applicants with a score of **660 or above** meet the credit score criterion.

3.4 If no bureau report can be obtained, the application must be routed to manual
review with reason `CREDIT_DATA_UNAVAILABLE`. No system or person may estimate,
infer or substitute a credit score.

## 4. Debt-to-income (DTI)

4.1 DTI is calculated **after** the requested loan: (existing monthly debt
payments + new loan payment) ÷ verified monthly gross income.

4.2 Post-loan DTI **above 43% and up to 50%** requires manual review with reason
`DTI_ABOVE_REVIEW_THRESHOLD`. The reviewer may approve with compensating factors
such as significant savings or a credit score above 720.

4.3 Post-loan DTI **above 50%** is declined with reason `DTI_ABOVE_MAX`.

4.4 Existing monthly debt is the greater of the amount the applicant states and the
amount reported by the bureau.

## 5. Income verification

5.1 Income must be verified from documents. Stated income alone is never used for
DTI.

5.2 For salaried applicants, verified monthly gross income is taken from the most
recent payslip. Bank statement payroll deposits corroborate it.

5.3 For self-employed applicants, verified income is the most recent tax return's
gross business income ÷ 12. Without a tax return the application is routed to
manual review with reason `MISSING_DOCUMENT`.

5.4 If stated annual income exceeds verified annual income by more than **15%**,
the application requires manual review with reason `INCOME_MISMATCH`.

## 6. Credit conduct

6.1 One or two delinquencies (30+ days past due) in the last 24 months require
manual review with reason `RECENT_DELINQUENCY`.

6.2 Three or more delinquencies in the last 24 months are declined.

## 7. Loan amount

7.1 The requested amount may not exceed USD 50,000.

7.2 The requested amount may not exceed 50% of verified annual gross income.
Requests above this limit require manual review with reason
`LOAN_AMOUNT_ABOVE_LIMIT`.

## 8. Identity and fraud

8.1 The name on income documents must match the applicant's name. A mismatch is
routed to manual review with reason `IDENTITY_MISMATCH`.

8.2 Fraud signals are never grounds for automated decline. They are escalated to a
human reviewer, who may refer the case to the fraud team.

## 9. Human review and audit

9.1 Any application with missing, unavailable or conflicting information is routed
to manual review. Missing information is listed explicitly in the review case.

9.2 Every recommendation must cite the evidence it relies on: the document,
bureau record or policy section.

9.3 Every decision, including automated ones, must be reproducible from the audit
trail: inputs, model or rule versions, tool calls and outputs.
