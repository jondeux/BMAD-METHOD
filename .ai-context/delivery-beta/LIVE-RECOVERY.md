# Live delivery beta recovery trials

Both synthetic Mode C trials completed after a controller restart. Each used four dispatches and required no owner input. All 13 original acceptance checks passed.

| Trial | Published artifacts | Checks | Dispatches | Evidence |
| --- | --- | ---: | ---: | --- |
| Workshop capacity | [capacity.sql](live-recovery-evidence/workshop/run/artifacts/capacity.sql) · [workshop-pilot-brief.md](live-recovery-evidence/workshop/run/artifacts/workshop-pilot-brief.md) | 6/6 | 4/4 | [Final status](live-recovery-evidence/workshop/final-status.json) · [Recovery](live-recovery-evidence/workshop/recovery-event.json) · [Build receipt](live-recovery-evidence/workshop/run/attempts/2/receipt.json) · [Verification](live-recovery-evidence/workshop/run/attempts/4/worker.log) |
| Inventory reorder | [reorder.py](live-recovery-evidence/inventory/run/artifacts/reorder.py) · [reorder-pilot-brief.md](live-recovery-evidence/inventory/run/artifacts/reorder-pilot-brief.md) | 7/7 | 4/4 | [Final status](live-recovery-evidence/inventory/final-status.json) · [Recovery](live-recovery-evidence/inventory/recovery-event.json) · [Build receipt](live-recovery-evidence/inventory/run/attempts/2/receipt.json) · [Verification](live-recovery-evidence/inventory/run/attempts/4/worker.log) |

In each trial, the first code-build receipt was saved while the controller was paused. A new controller adopted the same receipt after the original process was stopped. The receipt hash matched before and after resume. The recorded dispatches show one route, one code build, one document build, and one verification. The artifact and native evidence hashes matched the saved files.

The trials used the exact private v0.1.0 release through its workspace host. Launching from the account plugin interface remains unverified.

Extract the [evidence archive](live-recovery-evidence.zip) beside this report to open the links above. Run `sha256sum -c SHA256SUMS` from the extracted `live-recovery-evidence` directory. The archive includes the original receipts and verifier, plus state snapshots that omit local launch settings.
