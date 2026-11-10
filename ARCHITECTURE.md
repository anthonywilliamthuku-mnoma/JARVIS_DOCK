# LEON architecture

LEON is a local-first PC agent. A Python core service (`leond`) plans and runs
tasks through skills. A compact dock UI (Tauri 2 + React) is the main way to talk
to it and to see what it is doing. Admin work goes through a separate elevated
helper that starts only after a real Windows UAC prompt.

Status: Phase 0 (foundations). Only the package skeleton exists. The components
below are the target design; they are built in later phases (see `PROGRESS.md`).

## Components

```
Dock UI (Tauri/React)  <--JSON-RPC over WebSocket, loopback + token-->  leond (core service)
                                                                        |- Brain (LLM providers, router)
                                                                        |- Agent loop / task manager
                                                                        |- Skill registry (hot reload)
                                                                        |- Policy engine + approvals
                                                                        |- Perception (screen/UIA/OCR)
                                                                        |- Memory (SQLite + vectors)
                                                                        |- Scheduler / triggers
                                                                        '- Audit log (hash-chained)
                                                                              |
                                                       named pipe (mutual auth)
                                                                              |
                                                     leon-elevated (admin, on demand)
```

| Component | Phase | Notes |
|---|---|---|
| `leond` core | 1+ | Python 3.12, async, typed with pydantic |
| Skill framework | 2 | Progressive disclosure, tiers enforced by core |
| Dock | 5 | Tauri 2 + React + TypeScript, frameless, always on top |
| `leon-elevated` | 4 | Allowlisted, schema-validated operations only |

## Privilege model

Every skill action is classified into a tier and passes through
`policy.check(action) -> allow | ask | deny (+ reason)`:

- **T0 Observe**: read-only, auto-allowed.
- **T1 Act (reversible, user level)**: auto-allowed after first-run consent, scoped to allowed folders.
- **T2 Sensitive**: asks the user (once, or for this task).
- **T3 Admin**: asks with a full preview, real UAC, time-boxed grant, revocable.
- **T4 Never**: hard-denied with no override (see the list in the master spec, section 2).

Skills cannot raise their own tier. The tier is declared in the manifest and
enforced by core.

## Key flows

These sequence diagrams are added with the phase that implements each flow.

- **Normal task**: user request -> plan -> execute tools -> verify -> report. (Phase 1-2)
- **Approval**: T2/T3 action -> approval sheet (exact action, reason, rollback) -> decision -> audit entry. (Phase 2, 5)
- **Elevated task**: approval -> UAC -> `leon-elevated` starts -> allowlisted ops -> idle timeout -> helper exits. (Phase 4)
- **Kill switch**: hotkey or button -> cancel queued tasks -> stop in-flight actions -> revoke elevation. (Phase 2, 5)
- **Crash resume**: tasks are persisted with checkpoints; on restart, resumable tasks continue from the last checkpoint. (Phase 7)

## Safety invariants

- Visible, never stealthy: tray and dock indicator whenever LEON acts.
- Audit everything: append-only, hash-chained log with secrets redacted.
- Reversible by default: Recycle Bin for deletes, restore point or export before risky system changes.
- Untrusted content (web, files, email, OCR, clipboard, tool output) is data, never instructions.
- Secrets live in Windows Credential Manager (DPAPI), never in the repo or logs.
- Local IPC is loopback only and token-authenticated.
