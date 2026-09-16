# Implementation and learning loop

Read this reference only when the user explicitly requests implementation, supplies experiment results, or asks to iterate an existing selected concept.

## Authorization gates

Idea generation and an implementation plan do not authorize external mutations. Obtain authorization before contacting participants, sending messages, spending money, creating accounts, accepting terms, publishing, deploying, changing production data, handling sensitive data, or running a high-cost job. Use local or simulated experiments when they answer the question, and label simulations as simulations.

Never treat selection as permission to overwrite unrelated work. Inspect workspace instructions, repository state, tests, and baseline before editing. Preserve user changes and limit implementation to the chosen smallest testable slice.

## Define the learning contract first

Before implementation, record:

- hypothesis and most important uncertainty;
- one primary metric and any guardrails;
- baseline, target, direction (`increase`, `decrease`, or `range`), and minimum meaningful change;
- measurement source, window, and limitations;
- kill condition, cost/time ceiling, and rollback or containment plan;
- outcomes mapped to `stop`, `keep`, `iterate`, and `pivot`.

Use observed metrics only. A test pass proves the tested behavior, not market desirability or business viability. A prototype does not count as a deployed outcome.

## Implement the smallest informative slice

Build only enough to test the critical assumption. Prefer reversible changes and inexpensive instrumentation. Run relevant repository tests and add focused tests when behavior changes. Record changed artifacts, checks run, failures, limitations, and any deviation from the selected concept.

Do not expand into adjacent features merely because they are convenient. If implementation exposes a hard-constraint failure, stop and return to selection rather than relabeling the constraint as technical debt.

## Evaluate and decide

Compare real results with predeclared baselines and thresholds, stating provenance and data quality. Use exactly one disposition:

- `stop`: end work because a kill condition, unacceptable risk, ethical/legal issue, or exhausted learning budget makes continuation unjustified;
- `keep`: retain the implementation because its success threshold is met and no guardrail fails;
- `iterate`: keep the concept but change implementation or experiment to address a diagnosed gap;
- `pivot`: revisit another concept or the brief because the core assumption or fit failed.

An `iterate` decision names one causal hypothesis and the smallest next change. A `pivot` decision identifies the failed assumption and whether to revisit the shortlist or regenerate candidates under a revised brief.

Count implementation/measurement cycles as iterations. Allow at most three by default. Stop earlier when the outcome is decisive, evidence cannot distinguish options, required access is unavailable, the next cycle exceeds the authorized budget, or marginal learning does not justify cost. More than three cycles requires an explicit user request and revised learning contract.

Use the helper's `evaluate` command for deterministic threshold comparison and history enforcement. The model remains responsible for provenance, evidence quality, causal interpretation, and recommendation.
