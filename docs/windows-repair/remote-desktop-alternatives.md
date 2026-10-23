# Remote Desktop Alternatives: Guacamole and RustDesk

## Summary

This document evaluates **Apache Guacamole** and **RustDesk** as alternative remote desktop solutions to **MeshCentral** (currently recommended).

**Current choice:** MeshCentral (Apache-2.0, self-hosted, agent + browser)

**Alternatives documented here:** For reference only; no implementation unless Founder/Director expands scope.

---

## Apache Guacamole

**Description:** Clientless remote desktop gateway (HTML5). Access RDP, VNC, SSH via web browser without installing client software.

**License:** Apache-2.0  
**Maintained by:** Apache Software Foundation  
**Current version:** 1.5.4 (as of 2026-10)  
**Platform support:** Web (HTML5), servers on Linux/Docker

### Architecture

```
[Windows PC with RDP] <---> [Guacamole Server] <---> [Operator Browser (HTML5)]
```

- **guacd:** Backend daemon that proxies RDP/VNC/SSH
- **guacamole-client:** Web app (Tomcat) with HTML5 interface
- **Database:** PostgreSQL or MySQL for user/session management

### Pros

- **Clientless:** No agent install on Windows PC (uses built-in RDP)
- **Multi-protocol:** RDP, VNC, SSH, Telnet in one gateway
- **Browser-based:** Operator accesses via HTTPS URL (no desktop client)
- **Open source:** Apache-2.0, no vendor lock-in
- **Audit logs:** Session recording, connection history

### Cons

- **RDP required:** Windows PC must have RDP enabled (requires Pro/Enterprise, not Home)
- **Network routing:** Guacamole server must reach Windows PC RDP port (3389)
- **No agent features:** No file transfer, no remote diagnostics (RDP only)
- **Deployment complexity:** Requires Tomcat + PostgreSQL + guacd daemon
- **Performance:** HTML5 canvas slower than native RDP client (acceptable for diagnostics, not for gaming)

### Use Case for AI-PLAYBOOK

**Boundary only:** Guacamole provides remote desktop access. It does **NOT** execute repairs or diagnostics automatically.

**Workflow:**
1. Operator logs into Guacamole web UI
2. Selects Windows PC from device list
3. Guacamole proxies RDP connection
4. Operator sees Windows desktop in browser
5. Operator manually troubleshoots (no AI-PLAYBOOK repair automation)

**Separation:** Guacamole is for **remote control**. AI-PLAYBOOK endpoint worker is for **diagnostics + repair proposals**. They are separate systems.

### Deployment

**Option 1: Docker Compose (Recommended)**

```yaml
version: '3'
services:
  guacd:
    image: guacamole/guacd:1.5.4
    restart: unless-stopped
  
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: guacamole
      POSTGRES_PASSWORD: <strong-password>
      POSTGRES_DB: guacamole
    volumes:
      - ./postgres-data:/var/lib/postgresql/data
  
  guacamole:
    image: guacamole/guacamole:1.5.4
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      GUACD_HOSTNAME: guacd
      POSTGRES_HOSTNAME: postgres
      POSTGRES_DATABASE: guacamole
      POSTGRES_USER: guacamole
      POSTGRES_PASSWORD: <strong-password>
```

**Option 2: Kubernetes (Prod)**

- Deploy guacd, PostgreSQL, Guacamole as separate pods
- Use Ingress for HTTPS termination
- Mount PersistentVolumes for database

**Option 3: Cloud (AWS/Azure/GCP)**

- Use managed PostgreSQL (RDS/Cloud SQL)
- Deploy Guacamole in VM or container service (ECS/Cloud Run)
- Use ALB/Load Balancer for HTTPS

### Integration with AI-PLAYBOOK

**None.** Guacamole is a remote desktop gateway. AI-PLAYBOOK diagnostics run via endpoint worker (Python agent), not via RDP session.

**Customer consent:** Operator must record consent before opening RDP session via Guacamole (same as MeshCentral).

**Audit:** Guacamole logs all connections (operator, device, timestamp). Export to AI-PLAYBOOK audit log for compliance.

### Recommendation

**Use Guacamole if:**
- RDP is already enabled on Windows PCs
- Operator prefers browser-based access (no desktop client install)
- Multi-protocol support is needed (RDP + VNC + SSH)

**Prefer MeshCentral if:**
- Agent features are needed (file transfer, remote shell, diagnostics)
- Windows Home edition (RDP not available without upgrade)
- Network routing is complex (MeshCentral agent phones home, no inbound ports)

---

## RustDesk

**Description:** Open-source remote desktop software (alternative to TeamViewer/AnyDesk). Self-hosted or cloud.

**License:** AGPL-3.0 (server), Proprietary (Windows/macOS clients with code-signing)  
**Maintained by:** RustDesk team  
**Current version:** 1.2.3 (as of 2026-10)  
**Platform support:** Windows, macOS, Linux, Android, iOS

### Architecture

```
[Windows PC with RustDesk Client] <---> [RustDesk Server (relay/signaling)] <---> [Operator Desktop Client]
```

- **rustdesk-server:** Relay + signaling server (Rust)
- **rustdesk client:** Desktop app (Windows/macOS) or mobile app
- **P2P:** Clients connect peer-to-peer when possible; relay when NAT/firewall blocks P2P

### Pros

- **Self-hosted:** No SaaS dependency, full control over relay server
- **Cross-platform:** Windows, macOS, Linux, mobile
- **Fast:** P2P connections when possible (low latency)
- **File transfer:** Built-in file transfer, clipboard sync
- **No RDP required:** Works on Windows Home (does not require Pro/Enterprise)
- **Unattended access:** Can install as service for always-on remote access

### Cons

- **AGPL-3.0 server:** Copyleft license (server code changes must be open-sourced if distributed)
- **Proprietary clients:** Windows/macOS clients are code-signed but not fully open-source
- **Agent install:** Requires RustDesk client install on Windows PC (not clientless)
- **Relay server:** Must deploy and maintain RustDesk relay server
- **No web UI:** Operator needs RustDesk desktop app (not browser-based)

### Use Case for AI-PLAYBOOK

**Boundary only:** RustDesk provides remote desktop access. It does **NOT** execute repairs or diagnostics automatically.

**Workflow:**
1. Install RustDesk client on Windows PC
2. Configure RustDesk to use self-hosted relay server
3. Operator opens RustDesk desktop app
4. Enters Windows PC ID + password
5. RustDesk establishes P2P or relayed connection
6. Operator sees Windows desktop in RustDesk window
7. Operator manually troubleshoots (no AI-PLAYBOOK repair automation)

**Separation:** RustDesk is for **remote control**. AI-PLAYBOOK endpoint worker is for **diagnostics + repair proposals**. They are separate systems.

### Deployment

**Self-hosted RustDesk Server:**

```bash
# Install rustdesk-server (Rust binary)
wget https://github.com/rustdesk/rustdesk-server/releases/download/1.1.10/rustdesk-server-linux-amd64.tar.gz
tar xzf rustdesk-server-linux-amd64.tar.gz
cd rustdesk-server-linux-amd64

# Run relay server (port 21116-21119)
./hbbs -r <your-domain>:21117 -k <encryption-key>
./hbbr

# Configure firewall to allow TCP 21115-21119, UDP 21116
```

**Docker:**

```yaml
version: '3'
services:
  rustdesk-server:
    image: rustdesk/rustdesk-server:latest
    ports:
      - "21115-21119:21115-21119"
      - "21116:21116/udp"
    volumes:
      - ./data:/root
```

### Integration with AI-PLAYBOOK

**None.** RustDesk is a remote desktop client. AI-PLAYBOOK diagnostics run via endpoint worker (Python agent), not via RustDesk session.

**Customer consent:** Operator must record consent before connecting via RustDesk (same as MeshCentral/Guacamole).

**Audit:** RustDesk server logs connections (client ID, timestamp). Export to AI-PLAYBOOK audit log for compliance.

### Recommendation

**Use RustDesk if:**
- Windows Home edition (RDP not available)
- P2P performance is critical (low latency)
- File transfer is frequently needed
- Operator prefers desktop app over browser

**Prefer MeshCentral if:**
- Browser-based access is required (no desktop client install)
- Agent features beyond RDP are needed
- AGPL-3.0 server license is a concern (MeshCentral is Apache-2.0)

---

## Comparison Matrix

| Feature | MeshCentral | Guacamole | RustDesk |
|---------|-------------|-----------|----------|
| **License** | Apache-2.0 | Apache-2.0 | AGPL-3.0 (server), Proprietary (clients) |
| **Client type** | Browser (HTML5) | Browser (HTML5) | Desktop app |
| **Agent install** | Yes (MeshAgent) | No (uses RDP) | Yes (RustDesk client) |
| **Protocol** | Custom + RDP/VNC | RDP/VNC/SSH proxy | Custom P2P |
| **RDP required** | No | Yes (Pro/Enterprise) | No |
| **Self-hosted** | Yes | Yes | Yes |
| **File transfer** | Yes | No (RDP only) | Yes |
| **Session recording** | Yes | Yes | Yes |
| **Maintenance** | Low (single binary) | Medium (Tomcat + DB) | Low (single binary) |
| **Network routing** | Agent phones home | Inbound to RDP | P2P or relay |
| **Performance** | Good | Fair (HTML5 canvas) | Excellent (P2P) |

---

## AI-PLAYBOOK Decision

**Current choice:** **MeshCentral**

**Rationale:**
- Apache-2.0 license (no copyleft)
- Browser-based (no desktop client install)
- Agent features (file transfer, remote shell if needed)
- Works on Windows Home (no RDP required)
- Single binary deployment (easy to self-host)

**Alternatives:**
- **Guacamole:** Use if RDP is already enabled and browser-based access is required (no agent features)
- **RustDesk:** Use if P2P performance is critical and desktop app is acceptable (AGPL-3.0 server)

**Implementation status:** MeshCentral documented in `windows_repair/remote_support.py`. Guacamole and RustDesk are **documentation only** (not implemented).

**Next steps (if Founder expands scope):**
1. Deploy MeshCentral server (self-hosted or Cloud)
2. Enroll Windows PCs with MeshAgent
3. Document customer consent workflow
4. Integrate MeshCentral session logs into AI-PLAYBOOK audit log
5. Train operators on remote desktop access (manual troubleshooting, not automated repair)

---

## References

- MeshCentral: https://meshcentral.com/
- MeshCentral GitHub: https://github.com/Ylianst/MeshCentral (Apache-2.0)
- Guacamole: https://guacamole.apache.org/
- Guacamole GitHub: https://github.com/apache/guacamole-server (Apache-2.0)
- RustDesk: https://rustdesk.com/
- RustDesk GitHub: https://github.com/rustdesk/rustdesk (AGPL-3.0)
