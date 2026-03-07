# PR Draft — Showoff Phase 5 (Item C: Process panel pagination/filter polish)

## Title
`feat(gui-showoff): phase5 process panel pagination + contains filter UX polish`

## Summary
This PR implements **Phase 5 / Item C** for the Process panel in local-simple GUI.

### Included
1. **Bounded page navigation for process list**
   - Adds page controls (first/prev/next/last)
   - Adds page size selector (10/20/50)
   - Keeps navigation bounded to valid pages
2. **Filter UX polish**
   - `run_id` filter now supports **contains** matching (case-insensitive)
   - Existing state filter remains available
   - Adds explicit **Clear filters** action
3. **Stop/Retry stability preserved**
   - Existing process detail actions continue to use the same endpoints
   - Selection/detail refresh logic retained after list updates and retry actions

## Why
- Process list grows quickly with retries; unbounded long list is hard to scan.
- Exact run_id matching is too strict for operator workflows.
- Fast reset (`Clear filters`) improves demo and triage ergonomics.

## Scope / Non-Goals
- No backend API contract change required.
- No new mutating endpoints.
- No change to RBAC/audit flow.

## Implementation Notes
- `autodev/gui_mvp_static/app.js`
  - Added process filtering helpers:
    - state filter
    - `run_id contains` filter
  - Added pagination helpers/state:
    - bounded current page
    - page-size normalization
    - page metadata rendering
  - Added `refreshProcessPanel()` to centralize filtered/paged rendering and selection sync.
- `autodev/gui_mvp_static/index.html`
  - Added `Clear filters` button.
  - Added pagination UI controls and page size selector.
- `autodev/gui_mvp_static/styles.css`
  - Added Process pagination layout/button styles.
- `autodev/tests/test_gui_mvp_server.py`
  - Extended static contract coverage for new Process panel controls and pagination/filter functions.

## Suggested PR Body (copy/paste)
```md
## What
- add bounded pagination controls to Process list (first/prev/next/last)
- add page-size selector (10/20/50)
- change run_id filter to contains match (case-insensitive)
- add clear-filters action for Process panel
- preserve stop/retry behavior and process detail flow

## Why
- process history can become long with retries
- exact run_id filtering is too restrictive
- clear-filters improves triage speed during demos

## Validation
- pytest autodev/tests/test_gui_mvp_server.py -q -k "process_panel_static_contract or process_read_endpoints_list_detail_history or stop_and_retry_endpoints_happy_path or retry_endpoint_supports_run_id_target"
- pytest autodev/tests/test_gui_api.py -q -k "trigger_retry_by_run_id_preserves_chain or trigger_start_execute_tracks_process_and_stop_graceful or trigger_stop_forced_kill_fallback"
```

## Manual Verification Checklist
- [ ] Processes tab shows paginated list with bounded nav controls.
- [ ] Page size selector updates visible rows and keeps valid page bounds.
- [ ] `run_id` filter matches partial text (contains), case-insensitive.
- [ ] State filter works with run_id contains filter in combination.
- [ ] `Clear filters` resets state+run_id and returns to page 1.
- [ ] Stop action still works on selected process.
- [ ] Retry action still works on selected process and updates selection to new process.

## Risks / Rollback
- Risk is low and isolated to frontend process-list rendering.
- Rollback by reverting this PR; backend contracts and persisted process state remain unchanged.
