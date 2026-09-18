# Experiments

TeachMeMusic contains research questions in addition to ordinary software
engineering. This directory records experiments that test research
hypotheses with evidence.

## Identifier Convention

```text
EXP-SCORE-xxx     EXP-ANALYSIS-xxx     EXP-PED-xxx
EXP-CURR-xxx      EXP-PERF-xxx
```

Numbers are sequential within a namespace. Experiment IDs are stable and
never silently reused.

## The Golden Rule

> **Experimental hypotheses must not silently become product
> requirements.**

The preferred flow is:

```text
Hypothesis → Experiment → Evidence → Decision → Requirement / Architecture Change
```

Only when the evidence and an explicit decision (recorded in the experiment
record and, where architectural, an ADR) justify it does a hypothesis turn
into a requirement or design change.

## Experiment Record Format

One file per experiment, named `EXP-XXX-xxx-short-title.md`, supporting:

```text
ID
Title
Status            (Proposed / Running / Completed / Abandoned)
Question
Hypothesis
Rationale
Baseline
Experimental Method
Dataset
Metrics
Procedure
Results
Limitations
Conclusion
Decision
Related Requirements
Related ADRs
Related Commits
```

## Status

**No experiments exist yet.** This framework is established in DEV-002;
the first experiments will arise from Stage A/B research questions
(score representation choices, analysis approaches) as they are
formulated. Do not create speculative experiment records.
