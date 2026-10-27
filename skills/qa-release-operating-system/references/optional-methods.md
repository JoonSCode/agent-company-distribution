# Optional QA methods

Use the following only when the trigger matters; no extra test-count, coverage
target, artifact or tool installation is implied. These are Company adaptations
of sources checked in the supplied research on 2026-10-26, not validated prompts
or execution authority. None substitutes for a required matching surface or
changes the approved acceptance claim.

| Lens and source | Use / skip | Benefit, limit, and reversal evidence |
| --- | --- | --- |
| [Property-based checks](https://research.chalmers.se/en/publication/237427) | Use for a broad input space with an independently justified invariant; skip when a focused example already resolves the risk or no valid property is known. | Generated cases can find overlooked combinations. A tautological property or poor generator gives false confidence; a reproducible counterexample or excluded material input class changes the property or test choice. |
| [Selective mutation](https://research.google/pubs/practical-mutation-testing-at-scale-a-view-from-google/) | Use when an important assertion may pass despite a realistic defect; skip exhaustive mutation or duplicate controls that add no decision value. | A bounded negative control tests the detector, not just code execution. Equivalent mutations and test cost limit interpretation; a meaningful defect surviving the check reopens its adequacy. Use only an authorized isolated fixture, not the release candidate. |
| [Flaky-test diagnosis](https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html) | Use when the same candidate alternates between pass and fail; skip repeated retries of a deterministic failure. | Retaining contradictory outcomes avoids green-by-retry claims. Apparent flakiness can be a product race; a controlled reproducer or isolated environment cause changes diagnosis, while a passing retry alone does not clear readiness. |
| [Coverage as a diagnostic](https://www.cs.ubc.ca/~rtholmes/papers/icse_2014_inozemtseva.pdf) | Use an uncovered changed or high-risk path to locate a possible missing falsifier; skip tests whose only purpose is raising a percentage. | Finds blind spots but does not measure oracle quality. The study's Java/mutation setting does not establish a universal threshold; a missed regression, weak assertion or newly exposed boundary changes the strategy, not a target number. Existing explicit requirements remain binding. |

