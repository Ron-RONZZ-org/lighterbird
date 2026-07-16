# IMAP Sync Engine Overhaul — Architectural Plan

## Issue
GitHub issue #146: https://github.com/Ron-RONZZ-org/lighterbird/issues/146

## Summary
Bring email IMAP sync engine up to top-tier standard with CONDSTORE/QRESYNC, UIDVALIDITY, IMAP IDLE, dead-letter backlog, localized folder names, connection pooling, and selective flag pull.

## Background
Exploring the existing sync-back code identified 10 gaps (see issue #146). The proposal was checked against AGENTS.md — it aligns (no new deps, stdlib imaplib only, pre-release timing ideal).

## Phased Plan
- Phase 0: Schema + Service Extraction (extract BacklogService, DeadLetterService, FlagSyncService from msg_ops.py)
- Phase 1: UIDVALIDITY tracking (prerequisite for CONDSTORE)
- Phase 2: Folder Mapping (localized trash using SPECIAL-USE)
- Phase 3: CONDSTORE/QRESYNC (highest risk — modifies core sync loop)
- Phase 4: Connection Pool (per-account reuse)
- Phase 5: IMAP IDLE (push notifications)

## Key Constraints
- No new dependencies (imaplib stdlib only)
- No file > 500 lines
- Backward-compatible schema changes (nullable columns)
- Keep old sync path as fallback, gate CONDSTORE behind feature flag

## Decision
The architect @architect was consulted and produced a detailed plan covering all 10 gaps with file tree, interfaces, flow diagrams, risk analysis, and phased implementation order. The plan was approved and filed as GitHub issue #146.
