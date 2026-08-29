# B87-I5-B Implementation Plan Governance Ordering Addendum

| Field | Value |
| --- | --- |
| Applies to | `docs/superpowers/plans/2026-08-29-b87-i5-b-executable-evaluation-subsystem.md` |
| Original plan commit | `969a0c8ba384888553e28aa7d92c9795f8967a5a` |
| Governing design addendum | `docs/superpowers/specs/2026-08-29-b87-i5-b-governance-ordering-addendum.md` |
| Scope | Required execution-order correction only |

## Mandatory precondition before Task 1

Do not begin Task 1 or create any I5-B implementation edit until Nolan has issued the exact phase release:

```text
AUTHORIZE B87-I5-B
```

This is required by the controlling B87-I5 programme-entry gate.

After that release, Tasks 1 through 17 may implement and verify the accepted I5-B subsystem using deterministic/mock providers only. The phase release does not waive any later executable-campaign review condition.

## Correction to the original plan's formal-execution wording

Where the original plan says the exact release is issued only after implementation verification, read it instead as follows:

> The exact phase release `AUTHORIZE B87-I5-B` must already be on record before implementation begins. Formal real-candidate execution remains blocked until the implemented harness has passed non-formal verification and Nolan has separately accepted the exact frozen executable campaign manifest produced by Task 17.

## Replacement semantics for Task 16

Task 16 must enforce **two independent prerequisites** for real-provider construction:

1. an exact previously issued phase-authority record containing `AUTHORIZE B87-I5-B`; and
2. a later human campaign-acceptance record bound to the exact frozen campaign-manifest SHA-256.

The intended interface is:

```python
def verify_i5b_execution_authority(
    phase_authority_record,
    campaign_acceptance_record,
    *,
    expected_manifest_hash: str,
):
    if phase_authority_record.get("release") != "AUTHORIZE B87-I5-B":
        raise AuthorityError("B87-I5-B phase authority is absent")
    if campaign_acceptance_record.get("accepted_by") != "Nolan":
        raise AuthorityError("human campaign acceptance is absent")
    if campaign_acceptance_record.get("campaign_manifest_sha256") != expected_manifest_hash:
        raise AuthorityError("campaign acceptance does not bind the frozen manifest")
    return I5BExecutionAuthority.from_records(
        phase_authority_record,
        campaign_acceptance_record,
    )
```

The implementation may create neither human authority artifact automatically.

## Replacement final gate wording

After Task 17, stop with the exact implementation/evidence and frozen executable campaign candidate for human review. Do not execute a real model merely because the phase release already exists.

Formal autonomous candidate execution may begin only when both are true:

```text
phase authority:       AUTHORIZE B87-I5-B
campaign acceptance:   exact manifest hash accepted by Nolan
```

No other part of the original implementation plan changes.
