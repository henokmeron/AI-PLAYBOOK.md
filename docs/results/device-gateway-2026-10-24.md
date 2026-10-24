# Device Gateway for Windows Endpoints

**Date:** 2026-10-24  
**Feature:** TLS Device Gateway  
**Status:** Code complete, Windows behavior UNVERIFIED

## Overview

The device gateway is a separate TLS-enabled HTTP server that allows real Windows laptops on other machines to reach device-side API endpoints without exposing the operator console. The console itself remains loopback-only.

## What It Does

The device gateway:
- Runs as a second HTTP server alongside the operator console
- Terminates TLS connections with a configurable certificate
- Serves ONLY device-side routes (enrollment, heartbeat, remote-work polling, repair jobs)
- Returns 404 for all operator/console routes including `/api/remote-work/orders` and `/api/remote-work/approve`
- Enforces per-client-IP rate limiting (default 60 requests/minute)
- Limits request bodies to 64 KiB (keeping existing per-route caps)
- Is OFF by default and requires explicit configuration

## Device-Side Routes Available on Gateway

The following routes are accessible through the gateway:

**Remote Work (device endpoints):**
- `/api/remote-work/poll` - Device polls for pending jobs
- `/api/remote-work/claim` - Device claims a specific job
- `/api/remote-work/complete` - Device reports job completion
- `/api/remote-work/heartbeat` - Device check-in

**Device Enrollment:**
- `/api/devices/enroll` - Device enrollment with one-time code
- `/api/devices/report` - Device status reporting

**Repair Device (device endpoints):**
- `/api/repair/device/jobs` - Fetch pending repair jobs
- `/api/repair/device/check-in` - Device repair check-in
- `/api/repair/device/result` - Submit repair job results

## Operator Routes NOT on Gateway

These routes remain operator-only on the loopback console:
- `/api/remote-work/orders` - Create work orders (operator action)
- `/api/remote-work/approve` - Approve work orders (operator action)
- `/api/devices` - List all devices (operator view)
- `/api/devices/revoke` - Revoke device credentials (operator action)
- `/api/repair/device/enrol` - Create device enrollment (operator action)
- `/api/repair/device/issue` - Issue repair job (operator action)
- `/api/repair/device/revoke` - Revoke repair device (operator action)
- All other console, auth, ops, and UI routes

## Environment Variables

### Required Configuration

```bash
# Enable the gateway (OFF by default)
export DEVICE_GATEWAY_ENABLED=1

# Gateway bind address (must be set explicitly, e.g., 0.0.0.0)
export DEVICE_GATEWAY_HOST=0.0.0.0

# TLS certificate path (required)
export DEVICE_GATEWAY_CERT=/path/to/cert.pem

# TLS private key path (required)
export DEVICE_GATEWAY_KEY=/path/to/key.pem
```

### Optional Configuration

```bash
# Gateway port (default: 8443)
export DEVICE_GATEWAY_PORT=8443

# Rate limit per client IP in requests/minute (default: 60)
export DEVICE_GATEWAY_RATE_LIMIT=60
```

## TLS Requirements

- Minimum TLS version: 1.2
- The gateway terminates TLS itself using Python's `ssl.SSLContext`
- Certificate and key must exist and be readable
- Self-signed certificates are acceptable for testing
- Production deployments should use properly signed certificates

## Security Model

### Transport Security

Device-side handlers now accept requests that are:
- **Loopback** (127.0.0.1 or ::1) over plain HTTP (for local testing), OR
- **Through the TLS gateway** (any remote IP, but only over verified TLS)

Non-loopback plain HTTP requests to device routes are refused with 403.

### Authentication

Device routes still require valid device bearer tokens in the `Authorization` header. The gateway does not bypass authentication checks.

### Rate Limiting

The gateway enforces a configurable per-client-IP rate limit (default 60 requests/minute) to prevent abuse.

## How to Run on Office PC Test

### 1. Generate or Obtain TLS Certificate

For testing with a self-signed certificate:

```bash
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout gateway-key.pem -out gateway-cert.pem \
  -days 365 -subj "/CN=your-hostname"
```

For production, use a certificate from a trusted CA.

### 2. Configure Environment

```bash
# Gateway configuration
export DEVICE_GATEWAY_ENABLED=1
export DEVICE_GATEWAY_HOST=0.0.0.0
export DEVICE_GATEWAY_PORT=8443
export DEVICE_GATEWAY_CERT=/path/to/gateway-cert.pem
export DEVICE_GATEWAY_KEY=/path/to/gateway-key.pem

# Console remains on loopback
export WEB_HOST=127.0.0.1
export WEB_PORT=8080

# Other required config (gateway URL, API keys, etc.)
export PLATFORM_GATEWAY_URL=http://127.0.0.1:8010
export PLATFORM_API_KEY_FILE=/path/to/api.key
# ... other environment variables as needed
```

### 3. Start the Server

```bash
cd /workspace/web
python3 server.py
```

You should see output like:

```
Local web UI listening on http://127.0.0.1:8080
Device gateway listening on https://0.0.0.0:8443
Gateway target: http://127.0.0.1:8010
...
```

### 4. Test from Windows Laptop

From the Windows endpoint agent on another machine:

```powershell
# Point the agent to the gateway
$env:CONSOLE_URL = "https://office-pc-hostname:8443"

# Run the agent (with appropriate bearer token configuration)
python endpoint_agent.py
```

## Architecture

```
┌─────────────────┐
│ Operator Browser│
│  (localhost)    │
└────────┬────────┘
         │ HTTP
         │ 127.0.0.1:8080
         v
┌─────────────────────────────┐
│  Console WebServer          │
│  - Operator UI              │
│  - Work order creation      │
│  - Device management        │
│  - All console routes       │
└─────────────────────────────┘
         │
         │ Shares state
         v
┌─────────────────────────────┐     HTTPS (TLS 1.2+)
│  Device Gateway Server      │◄────────────────────┐
│  - Device routes only       │                     │
│  - TLS termination          │                     │
│  - Rate limiting            │                     │
│  - 0.0.0.0:8443            │                     │
└─────────────────────────────┘                     │
                                                    │
                                    ┌───────────────┴──────────┐
                                    │ Windows Endpoint Agents  │
                                    │ (Remote machines)        │
                                    └──────────────────────────┘
```

## Implementation Details

### Shared State

Both servers share the same:
- Device registry
- Remote work store
- Repair device store
- Operator authentication (console only)

### Handler Reuse

The gateway reuses existing handler methods from `web/server.py`. It creates temporary handler instances that:
- Use the gateway's request/client information
- Are marked with `_is_gateway_request = True`
- Share the console server's state

### Transport Check

Device-side handlers use `_loopback_or_gateway()` which checks:
1. Is the client IP loopback? (127.0.0.1 or ::1)
2. OR is `_is_gateway_request` set to True?

Routes using `_device_bearer()` already had the right logic (loopback or TLS).

## Testing

Tests cover:
- Gateway is off by default
- Gateway refuses to start without cert/key
- Operator routes return 404 on gateway
- Device routes require bearer token even on gateway
- Plain HTTP to gateway port fails
- Non-loopback plain HTTP to console device routes still returns 403
- Rate limiting works per-client-IP
- Existing web/ test suite remains green

Run tests:

```bash
cd /workspace
python -m pytest web/test_device_gateway.py -v
python -m pytest web/ -v  # Full suite
```

## IMPORTANT: Windows Behavior UNVERIFIED

This implementation:
- ✅ Has been tested in unit/integration tests with self-signed certificates
- ✅ Correctly routes and filters requests based on tests
- ✅ Enforces TLS, authentication, and rate limiting
- ❌ Has NOT been tested with actual Windows endpoint agents
- ❌ Has NOT been verified on a real Office PC deployment
- ❌ Certificate handling on Windows may have platform-specific issues

**Before production use:**
1. Test with real Windows agents on separate machines
2. Verify certificate trust chain works on Windows
3. Check firewall and network configuration
4. Monitor rate limiting thresholds under real load
5. Validate TLS handshake with Windows HTTP clients

## Files Changed

- `web/device_gateway.py` - New module implementing the TLS gateway server
- `web/server.py` - Added `_loopback_or_gateway()` check, updated device-side handlers, integrated gateway in `main()`
- `web/test_device_gateway.py` - Comprehensive test suite
- `docs/results/device-gateway-2026-10-24.md` - This documentation

## References

- Original task specification: Windows Endpoint lane, e3251b5a or later
- Transport security model: `_device_bearer()` in `web/server.py`
- Device routes: See `DEVICE_ROUTES` in `web/device_gateway.py`
