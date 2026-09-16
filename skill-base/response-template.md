# Telco RDS — Mandatory Response Template

Use this structure for every substantive architectural answer. Omit sections only if genuinely not applicable (note the omission).

---

## Summary
One paragraph: what the answer recommends, the key risk or trade-off, and whether this is RDS-aligned or a known deviation.

## Assumptions
State explicitly — do not leave ambiguous:

| Parameter | Value |
|-----------|-------|
| OCP version | e.g. 4.18.17 (stable-4.18) |
| Partner release | e.g. Partner 26R1 |
| Topology | e.g. SNO / MNO-3 |
| Architecture | e.g. x86_64 / aarch64 |
| PTP operator | Partner PTP / Red Hat PTP |
| Acceleration | None / NVIDIA GPU (AI RAN) |
| FIPS | Enabled / Disabled |

## RDS Alignment

| Area | Status | Detail |
|------|--------|--------|
| Feature X | Aligned | Matches RDS requirement |
| Feature Y | Deviation | Partner uses Z instead — Support Exception: ECOPS-NNN |
| Feature Z | Out-of-RDS | CU/AI RAN scope — no RDS coverage, best-effort guidance |

## Design
Trade-offs, capacity considerations, coexistence impacts. WHY this approach.

## Implementation
Manifests, operator configuration, commands. HOW to deploy.

```yaml
# Example manifest (include apiVersion, kind, metadata.name minimum)
```

Key operator subscriptions, CRDs, or `oc` commands required.

## Validation
Health checks, KPIs, and `oc` commands to verify the implementation.

```bash
# Confirm operator status
oc get csv -n <namespace>

# Verify resource
oc get <resource> -o yaml
```

## References
- OCP version-specific docs (always pin the version in the URL)
- ECOPS ticket(s) if deviating from RDS
- Partner solution design reference (if known)
- RFE or engineering epic (if relevant)

---

## Support Exception block (include whenever status = Deviation)

```
Support Exception
  ECOPS ticket: ECOPS-NNN (https://redhat.atlassian.net/browse/ECOPS-NNN)
  SUPPORTEX ticket: SUPPORTEX-NNNNN (if filed)
  Partner release: {Partner} {Release}
  OCP version: 4.XX.YY
  Deviation: <what the partner does differently>
  RDS baseline: <what RDS requires>
  Rationale: <why the partner deviates>
  Risk: <impact if unsupported>
  Mitigation: <how risk is managed>
  Rollback: <how to revert if needed>
  Resolution: Done-Errata / Not a Bug / Open
```
