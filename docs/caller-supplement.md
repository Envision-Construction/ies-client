# Caller inventory supplement

Observed 2026-11-08; remote-tracking refs are local snapshots, not freshly fetched. Other repositories were read only.

## Known callers whose local checkout predates package adoption

- ap-response-bot local HEAD: 2663416166988e0448590158b030ffc157c70478; no package imports in that working tree. Local origin/main: c57ddbb5d448ab1ffe74a30737ae399afc6a4cec.
- gcpay-sync local HEAD: 652858bef7ad58508e408ce82aec8707cd6812eb; private src/gcpay_sync/qbo_client.py:22 silently defaults to Envision. Migrate the private copy or remove its default in a follow-up. Local origin/main: 3021aafa7c37abbde506cec9d81ce0edb073b69a.
- Envision-MCP local HEAD: 95c5da832200b6be8b761801fdb80cf911a8e640. No direct Python imports found in the working tree (including nested worktrees); planning references do not establish a runtime caller.

## Required ap-response-bot change (origin/main snapshot)

| repo:path:line | Change |
|---|---|
| ap-response-bot:src/ap_response_bot/ies_lookup.py:43 | Import remains valid. |
| ap-response-bot:src/ap_response_bot/ies_lookup.py:99 | _qbo_query(sql) MUST pass the confirmed company; thread an explicit company through the lookup API. |
| ap-response-bot:src/ap_response_bot/ies_lookup.py:252 | Remove documentation describing ies-client default entity. |
| ap-response-bot:pyproject.toml:19 | Coordinate unpinned Git dependency upgrade with migration. |
| ap-response-bot:tests/test_ies_lookup.py:3 | Update mocked query assertions to require company. |

## gcpay-sync package callers (origin/main snapshot)

These call sites already pass company. No immediate library API edit required; audit upstream defaults (e.g. qbo_sync.py:1017 graphql_query defaults to envision) so explicit forwarding does not conceal an unconfirmed entity.

| repo:path:line | Change |
|---|---|
| gcpay-sync:src/gcpay_sync/qbo_sync.py:68 | Import or explicit-company call; retain forwarding and validate upstream selection. |
| gcpay-sync:src/gcpay_sync/qbo_sync.py:71 | Import or explicit-company call; retain forwarding and validate upstream selection. |
| gcpay-sync:src/gcpay_sync/qbo_sync.py:775 | Import or explicit-company call; retain forwarding and validate upstream selection. |
| gcpay-sync:src/gcpay_sync/qbo_sync.py:786 | Import or explicit-company call; retain forwarding and validate upstream selection. |
| gcpay-sync:src/gcpay_sync/qbo_sync.py:797 | Import or explicit-company call; retain forwarding and validate upstream selection. |
| gcpay-sync:src/gcpay_sync/qbo_sync.py:813 | Import or explicit-company call; retain forwarding and validate upstream selection. |
| gcpay-sync:src/gcpay_sync/qbo_sync.py:909 | Import or explicit-company call; retain forwarding and validate upstream selection. |
| gcpay-sync:src/gcpay_sync/qbo_sync.py:1028 | Import or explicit-company call; retain forwarding and validate upstream selection. |
| gcpay-sync:src/gcpay_sync/qbo_sync.py:1136 | Import or explicit-company call; retain forwarding and validate upstream selection. |
| gcpay-sync:src/gcpay_sync/qbo_sync.py:1231 | Import or explicit-company call; retain forwarding and validate upstream selection. |
| gcpay-sync:src/gcpay_sync/qbo_sync.py:1310 | Import or explicit-company call; retain forwarding and validate upstream selection. |
| gcpay-sync:src/gcpay_sync/qbo_sync.py:1320 | Import or explicit-company call; retain forwarding and validate upstream selection. |
| gcpay-sync:src/gcpay_sync/qbo_sync.py:1363 | Import or explicit-company call; retain forwarding and validate upstream selection. |
| gcpay-sync:src/gcpay_sync/bill_sync.py:427 | Import or explicit-company call; retain forwarding and validate upstream selection. |
| gcpay-sync:src/gcpay_sync/bill_sync.py:443 | Import or explicit-company call; retain forwarding and validate upstream selection. |
| gcpay-sync:src/gcpay_sync/bill_sync.py:885 | Import or explicit-company call; retain forwarding and validate upstream selection. |
| gcpay-sync:src/gcpay_sync/bill_sync.py:897 | Import or explicit-company call; retain forwarding and validate upstream selection. |
| gcpay-sync:requirements.txt:16 | Coordinate unpinned Git dependency upgrade. |

## Transitive calls in the phase-10 clone

worktrees/gcpay-sync-phase10-clone HEAD: 87a085b483c5a6634c8a4f41bbe7ee70663bcc22. bill_sync imports query/post through qbo_sync at line 80.

| repo:path:line | Change |
|---|---|
| worktrees/gcpay-sync-phase10-clone:src/gcpay_sync/bill_sync.py:387 | Already forwards company; preserve and audit upstream selection. |
| worktrees/gcpay-sync-phase10-clone:src/gcpay_sync/bill_sync.py:403 | Already forwards company; preserve and audit upstream selection. |
| worktrees/gcpay-sync-phase10-clone:src/gcpay_sync/bill_sync.py:782 | Already forwards company; preserve and audit upstream selection. |
| worktrees/gcpay-sync-phase10-clone:src/gcpay_sync/bill_sync.py:789 | Already forwards company; preserve and audit upstream selection. |

## Deployed copies and limits

README identifies qbo-envision-bq-sync and qbo-token-refresher as SCRIPT_B64 consumers. A grep of local source cannot establish which deployed script is running. Root must rebuild embedded copies and verify deployments separately; no live services or credentials were accessed.

The main inventory lists direct imports and call candidates discovered in Python source, including duplicate worktrees/archives. Dynamic imports, runtime-generated code and external deployments cannot be exhaustively proven by grep. Explicitly supplied company variables still require caller-level confirmation; library validation cannot prove user confirmation.

## Retrieval provenance

Greptile docs snapshot 2026-10-04-1791216790212-2be5e8 was used for orientation; it predates the five-entity current source. Codebase-memory ies-client index reports main df8a977458197ef7f4f6f8cf7c79e13bcc4865eb, indexed 2026-11-02, and no recorded gaps on the two client files. It is not this worktree revision (base 5cc848adede8b0ff5ee369a7effada50dd0350e2). Owner-local Git/source and offline tests govern this change; no indexing or other repository writes were performed.

## Upstream silent defaults requiring follow-up

The skill script explicitly forwards COMPANY but still silently initializes it
from an optional CLI argument. Remove that default / require confirmed selection:

- claude-code-memory:global/skills/ies-invoices/scripts/convert_from_estimate.py:256
- The same script is present in ccm-final-validation-publish-20261025,
  ccm-remediation-20261023, ccm-forensic-integration-20261024 and
  workflow-ownership-ccm; inspect their corresponding CLI defaults when updating
  the owner source. Do not blindly edit historical snapshots.

In worktrees/gcpay-sync-phase10-clone, qbo_sync.py defaults company to envision
at lines 707, 718, 729, 740, 841, 952, 976, 1055, 1160, 1233, 1238, 1273, 1300,
1537, 1606, 1653, 1781 and CLI line 1915. bill_sync.py does so at lines 385, 397,
781, 786, 829, 953, 1211 and CLI line 1335. These wrapper defaults need a separate
confirmation-rule follow-up even though calls into ies-client remain compatible.
