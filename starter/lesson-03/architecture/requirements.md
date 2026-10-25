# Requirements

Captured the way a Forward Deployed Engineer would in the first week with
Meridian Digital Lending (fictional): from the people who do the work today.

## The business problem

Meridian's underwriters spend ~45 minutes per application gathering documents,
re-keying numbers, checking policy and writing a recommendation. Volume is
growing faster than the team. Leadership wants faster decisions **without**
weakening credit quality or regulatory defensibility.

## Current workflow (as observed)

1. Application arrives from the origination system with uploaded documents.
2. Underwriter reads payslips and bank statements, types income into a spreadsheet.
3. Pulls a bureau report.
4. Calculates DTI by hand.
5. Looks up the relevant clauses in a 40-page policy PDF.
6. Writes a recommendation; a senior underwriter signs off on edge cases.
7. Decision and notes are pasted into the loan system.

**Where time goes:** steps 2, 4 and 5. **Where errors come from:** re-keying (2),
stale policy knowledge (5), inconsistent notes (6–7).

## Users

| User | Needs |
|---|---|
| Underwriter | A pre-assembled case: verified facts, cited policy, a draft recommendation |
| Senior underwriter | Only the cases that need judgement, with the reason they were escalated |
| Credit risk / compliance | Every decision reproducible and explainable after the fact |
| Applicant (indirectly) | A fast, consistent, fair decision |

## Functional requirements

- FR1 Extract income facts from payslips, bank statements and tax returns.
- FR2 Verify income per policy §5 and detect overstated income.
- FR3 Retrieve the credit report from the bureau.
- FR4 Calculate post-loan DTI exactly (policy §4).
- FR5 Retrieve and cite applicable policy sections.
- FR6 Produce a recommendation with risk factors, evidence and missing information.
- FR7 Apply policy deterministically; escalate where policy requires.
- FR8 Route escalations to a human review queue.
- FR9 Record a complete audit trail.

## Non-functional requirements

| NFR | Target | Lesson |
|---|---|---|
| Never invent data (scores, income) | 0 occurrences in eval suite | 1, 6 |
| Every decision cites evidence | 100% | 3, 6 |
| End-to-end latency | p95 < 15 s | 7, 8 |
| Cost per application | tracked per decision | 7 |
| Survives a bureau outage | escalates, does not fail or guess | 6, 8 |
| Access control | underwriter vs reviewer vs admin roles | 9 |
| Reproducibility | decision replayable from audit trail | 7, 9 |

## Out of scope (v1)

Pricing / rate setting, secured loans, collections, applicant-facing UI.
