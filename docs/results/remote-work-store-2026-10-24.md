# Remote Work Store Persistence

## Overview

The `WorkStore` in `integrations/remote_work.py` now supports optional SQLite persistence, allowing the state of work orders, approvals, audit logs, heartbeats, and enrolled devices to survive service restarts.

## Configuration

### Environment Variable

Set the `REMOTE_WORK_STATE` environment variable to enable persistent storage:

```bash
export REMOTE_WORK_STATE=/path/to/work.db
```

When this environment variable is not set or is empty, the store operates in memory-only mode (the default behavior).

### File Location Advice

**Windows:**
- Recommended: `%ProgramData%\RemoteIT\work.db`
- Example: `C:\ProgramData\RemoteIT\work.db`
- This directory provides appropriate permissions for system services

**Linux:**
- Recommended: `/var/lib/remote-it/work.db`
- Ensure the parent directory exists and has appropriate permissions
- The service user must have read/write access

**Important:** The database file should be located outside the repository to prevent accidental commits and to ensure proper separation of code and data.

## Restart Semantics

### Approval Expiry

Approvals that have passed their TTL (15 minutes by default) are still treated as expired after a restart. The system will refuse to claim or execute orders with expired approvals.

### Interrupted Orders

Orders that were in the `claimed` or `running` state at the time of a restart are automatically marked as `failed` with the error message: `"order was interrupted by restart"`. An audit entry is created for each interrupted order.

These interrupted orders:
- Will not be re-offered by `poll_jobs`
- Cannot be re-claimed
- Cannot be completed
- Remain in the terminal `failed` state

### Audit Integrity

The audit log is append-only and persists across restarts. No audit entries are modified or deleted during normal operations. The complete history of state transitions remains available after a restart.

### Heartbeat Cap

Heartbeats are retained in the database with a cap of 1000 entries per device. When this limit is exceeded, older heartbeats for that device are automatically removed.

## Security

### Secret Redaction

The existing secret redaction mechanism (`_scrub` and `_contains_secret_key`) operates before any data is written to disk. Orders containing secret keys (e.g., `password`, `secret`, `token`, `serial`) are refused and marked as such, with no secret data written to the SQLite file.

### File Permissions

On platforms that support it (Linux, macOS), the database file is created with `0600` permissions (read/write for owner only). This helps protect the contents from unauthorized access.

### WAL Mode

The SQLite database uses Write-Ahead Logging (WAL) mode for improved concurrency and crash recovery. This ensures that the database can handle multiple threads writing to it without corruption.

## Implementation Details

### In-Memory Mode (Default)

When no path is provided, `WorkStore()` operates entirely in memory, as before. No database file is created, and all state is lost on process exit. This mode is used by default and by existing tests.

### SQLite Mode

When a path is provided via `WorkStore(path=...)`, the store:
1. Creates or opens an SQLite database at the specified path
2. Initializes the schema if needed
3. Loads existing state from the database
4. Marks any `claimed` or `running` orders as `failed` with an audit entry
5. Persists all subsequent mutations atomically within the lock

### Thread Safety

Each thread uses its own SQLite connection (via `threading.local()`). All mutations occur within the existing `store._lock`, ensuring that the in-memory state and the database remain synchronized. Each mutation is committed atomically, so a crash mid-change cannot leave a half-approved order.

### Atomic Commits

Every mutation that occurs under `store._lock` commits atomically:
- Creating an order
- Approving an order
- Claiming an order
- Completing an order
- Posting a heartbeat
- Registering an enrolled device

A restart or crash during a mutation will either show the complete change or no change at all.

## Testing

The test suite in `integrations/tests/test_remote_work_store.py` verifies:
- Survive-restart round trip (create, approve, reopen: state and audit intact)
- Expired approval stays unusable after reopen
- Claimed order becomes `failed` after reopen and is not re-offered by poll
- Self-approval still refused after reopen
- Secret never written to disk (binary grep of database file)
- Concurrent writers from threads don't corrupt the store
- In-memory default unchanged (existing `test_remote_work.py` passes untouched)
- File created with `0600` permissions (where supported)
- Audit remains append-only after reopen
- Heartbeat cap enforced per device

## Platform Status

**Windows:** UNVERIFIED

The implementation uses Python's `sqlite3` module and standard library features that are cross-platform. However, file permission enforcement (`0600`) may not be fully supported on all Windows configurations. The core functionality (persistence, restart semantics, secret redaction) should work correctly on Windows, but file permissions may require additional configuration at the filesystem or service level.

## Migration

No migration is required. Existing deployments will continue to use in-memory storage unless the `REMOTE_WORK_STATE` environment variable is explicitly set. Once set, the database file will be created automatically on first use.

To switch from in-memory to persistent storage:
1. Set the `REMOTE_WORK_STATE` environment variable
2. Restart the service
3. Verify the database file was created at the specified path

To switch back to in-memory storage:
1. Unset the `REMOTE_WORK_STATE` environment variable (or set it to an empty string)
2. Restart the service
