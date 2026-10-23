# osquery Integration for Diagnostics

## Summary

[osquery](https://osquery.io/) is an open-source endpoint visibility platform that exposes the operating system as a relational database. It provides SQL-based queries for system inventory, processes, services, network connections, file integrity, and more.

**License:** Apache-2.0 or GPL-2.0 (dual-licensed)  
**Maintained by:** Osquery Foundation (Linux Foundation)  
**Current stable:** 5.13.1 (as of 2026-10)  
**Platform support:** Windows, macOS, Linux

## Why osquery

- **Proven:** Used in production by Airbnb, Facebook, Google, Netflix, Uber
- **Standard queries:** Pre-built schema for common diagnostics (services, processes, users, network, disks, registry)
- **No custom collectors:** Replaces our bespoke PowerShell scripts with a maintained query engine
- **Fleet-ready:** Integrates with [Fleet](https://fleetdm.com/) for centralized management (optional)
- **Audit-friendly:** All queries logged; no silent execution

## Dependency Approval

**Status:** Documentation and optional adapter stubs only. No binaries vendored into git.

**Founder approval required before:**
- Downloading osquery MSI/executable into this repository
- Adding osquery as a required dependency for endpoint workers
- Signing up for Fleet Cloud (paid SaaS) or self-hosting Fleet server
- Installing osquery on customer Windows PCs without explicit consent

**Current scope:** Prefer osquery over rebuilding collectors from scratch. Document the integration path. Adapter stubs can be added if Founder approves the dependency.

## Integration Options

### Option 1: Direct osquery Installation (Recommended for simplicity)

**Pros:**
- Single binary (`osqueryd.exe` + `osqueryi.exe`)
- SQL queries instead of PowerShell scripts
- Standard schema for diagnostics

**Cons:**
- Requires installing osquery on the Windows PC
- ~20 MB MSI download from osquery.io
- Customer must consent to installation

**Setup:**
1. Download osquery MSI from https://osquery.io/downloads/official/5.13.1
2. Verify SHA256: `<hash from official page>`
3. Install: `msiexec /i osquery-5.13.1.msi /quiet`
4. Queries run via `osqueryi --json "SELECT * FROM services WHERE start_type='auto'"`

### Option 2: Fleet Integration (Recommended for fleet management)

**Pros:**
- Centralized query management (Fleet server)
- Scheduled queries with result caching
- Web UI for diagnostics
- Multi-tenant device groups

**Cons:**
- Requires Fleet server (self-hosted or Cloud)
- Fleet Cloud is paid ($5/device/month as of 2026-10)
- Self-hosted Fleet needs Docker/K8s + MySQL/Postgres
- Customer must consent to agent + remote query execution

**Setup:**
1. Deploy Fleet server (self-hosted: https://fleetdm.com/docs/deploy/deploy-fleet)
2. Enroll devices with Fleet osquery agent: `fleetctl package --type=msi --fleet-url=<your-fleet> --enroll-secret=<secret>`
3. Create query packs in Fleet UI
4. Poll Fleet API for query results: `GET /api/v1/fleet/queries/{id}/results`

### Option 3: Hybrid (Current PowerShell + Optional osquery)

**Pros:**
- No breaking changes to existing endpoint workers
- osquery used only when available
- Gradual migration path

**Cons:**
- Maintains two diagnostic paths (PowerShell + osquery)
- More complexity in report normalization

**Setup:**
1. Keep existing PowerShell collectors (`windows_repair/providers.py`)
2. Add optional osquery adapter (`integrations/osquery_adapter.py`) that checks if osqueryi.exe exists
3. Prefer osquery when available, fall back to PowerShell

## SQL Query Examples

**Storage diagnostics:**
```sql
SELECT device_id, type, blocks_size, blocks_available, blocks * blocks_size AS total_bytes
FROM mounts
WHERE device_id LIKE 'C:%';
```

**Service status:**
```sql
SELECT name, display_name, status, start_type
FROM services
WHERE start_type IN ('AUTO_START', 'DEMAND_START')
ORDER BY name;
```

**Windows Update status:**
```sql
SELECT * FROM windows_update_history
ORDER BY date DESC
LIMIT 20;
```

**Device inventory (problem devices):**
```sql
SELECT name, manufacturer, class, problem
FROM pnp_device_properties
WHERE problem != 'None';
```

**Network diagnostics:**
```sql
SELECT interface, address, mask, type
FROM interface_addresses
WHERE interface NOT LIKE 'Loopback%';
```

**Print spooler:**
```sql
SELECT name, status, start_type
FROM services
WHERE name = 'Spooler';
```

## Adapter Stub (Founder Approval Pending)

**File:** `integrations/osquery_adapter.py` (not created yet)

```python
"""Optional osquery adapter for diagnostics.

Only enabled when osqueryi.exe is installed and Founder approves dependency.
Falls back to PowerShell collectors when osquery is unavailable.
"""

def osquery_available() -> bool:
    """Check if osqueryi.exe is installed."""
    # Check PATH for osqueryi.exe
    # Return False until Founder approves

def query(sql: str) -> list[dict]:
    """Run osquery SQL and return JSON results."""
    # subprocess.run(["osqueryi", "--json", sql])
    # Parse JSON output
    # Raise if osquery not available

def collect_diagnostics(procedure_id: str) -> dict:
    """Collect diagnostics using osquery instead of PowerShell."""
    # Map procedure_id to SQL query
    # Run query()
    # Normalize result to match existing schema
```

**Normalization:** Map osquery columns to existing `integrations/endpoint.py` report schema. Keep backward compatibility with PowerShell collectors.

## Rollout Plan (Pending Founder Approval)

### Phase 1: Documentation Only (CURRENT)
- Document osquery as preferred diagnostic tool
- No code changes, no binaries
- Founder reviews and approves dependency

### Phase 2: Optional Adapter (After Approval)
- Add `integrations/osquery_adapter.py` with fallback
- Update `integrations/endpoint_worker.py` to prefer osquery
- Test on dev PC with osquery installed
- Ship with graceful degradation (PowerShell fallback)

### Phase 3: Recommended Installation (After Field Test)
- Document osquery MSI installation in endpoint-agent.md
- Add osquery to Scheduled Task setup script
- Customer consent: "Install osquery for faster diagnostics?"
- Monitor adoption via `agent_version` + `osquery_available` in reports

### Phase 4: Fleet Integration (Optional, After Phase 3)
- Deploy self-hosted Fleet server (Docker)
- Enroll endpoints with Fleet osquery agent
- Poll Fleet API for cached query results
- Retire direct osqueryi.exe calls

## Security Considerations

1. **No arbitrary SQL:** Only pre-approved queries from allowlist
2. **Read-only:** osquery cannot modify the system (no INSERT/UPDATE/DELETE)
3. **No secrets:** osquery redacts sensitive registry keys by default
4. **Audit log:** All queries logged to osquery.results.log
5. **Signed binary:** Verify osquery MSI signature before installation
6. **No remote shell:** osquery does not provide command execution (use MeshCentral for remote desktop if needed)

## Comparison: osquery vs PowerShell

| Feature | osquery | PowerShell |
|---------|---------|------------|
| Installation | MSI (~20 MB) | Built-in (Windows) |
| Query language | SQL | PowerShell scripts |
| Maintenance | Upstream project | Our custom scripts |
| Performance | Fast (C++) | Slower (interpreted) |
| Schema | Standard | Custom per script |
| Audit | Built-in logging | Manual logging |
| Fleet support | Yes (Fleet) | No |

## Comparison: Fleet vs Custom Console

| Feature | Fleet | Custom Console |
|---------|-------|----------------|
| Query management | Web UI | Manual |
| Multi-tenant | Yes (device groups) | Yes (tenant_id) |
| Cost | $5/device/month or self-hosted | No SaaS cost |
| API | REST API | Custom /api/devices/* |
| Maintenance | Fleet team | Our team |
| Deployment | Docker/K8s | RunPod/bare metal |

## Decision: osquery or PowerShell?

**Recommend osquery for new deployments:**
- Standard queries reduce maintenance
- Proven in production at scale
- Easier to audit (SQL logs)

**Keep PowerShell fallback for:**
- Endpoints without osquery installed
- Custom diagnostics not covered by osquery schema
- Gradual migration without breaking changes

## Decision: Fleet or Custom Console?

**Recommend custom console (existing /api/devices/*) for now:**
- No Fleet SaaS cost
- Full control over data and queries
- Simpler deployment (no Fleet server)
- Existing tenant isolation works

**Consider Fleet later if:**
- Customer count grows beyond manual query management
- Scheduled query caching becomes necessary
- Web UI for operators is required
- Founder approves Fleet server deployment or SaaS spend

## References

- osquery: https://osquery.io/
- osquery schema: https://osquery.io/schema/5.13.1/
- Fleet: https://fleetdm.com/
- Fleet pricing: https://fleetdm.com/pricing
- osquery license: https://github.com/osquery/osquery/blob/master/LICENSE (Apache-2.0 or GPL-2.0)
- Fleet license: https://github.com/fleetdm/fleet/blob/main/LICENSE (mixed, core is MIT + paid features are proprietary)

## Next Steps

1. **Founder approval:** Review this document and approve osquery as a dependency (or defer)
2. **Adapter implementation:** Add `integrations/osquery_adapter.py` after approval
3. **Test on dev PC:** Install osquery 5.13.1 and verify queries
4. **Document installation:** Update `docs/windows-repair/endpoint-agent.md` with osquery setup
5. **Ship with fallback:** Deploy optional osquery support with PowerShell fallback
6. **Monitor adoption:** Track `osquery_available` field in reports
7. **Fleet evaluation:** Revisit Fleet integration if query management becomes manual burden
