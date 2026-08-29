# Human decision register

No approval is recorded. Each item requires an actual human approver and blocks collection. The
proposal column makes the choice reviewable; it is not an approval.

| Decision | Proposed 0.1 choice | Status | Required human approver |
| --- | --- | --- | --- |
| Population and outcomes | Adults ≥18; special populations tagged separately; fractures, falls, all-cause mortality, hypercalcemia, nephrolithiasis and renal adverse events | blocking | protocol owner |
| Assay and specimen pooling | Preserve serum/plasma, assay and calibration separately; pool only after source-bound comparability is established | blocking | protocol owner with laboratory-method expertise |
| Risk-of-bias instruments | Adapted analytical checklist (q1), JBI prevalence (q2), ROBINS-E (q3 and observational q5), RoB 2 (q4 and randomized q5) | blocking | methods reviewer |
| Screening governance | Two independent human decisions; one designated human adjudication for disagreement; machine proposals never count as human decisions | blocking | protocol owner |

Approval must identify the human approver, decision, protocol version and timestamp in a real
verification event. Until then, `collection_allowed` remains `false`.
