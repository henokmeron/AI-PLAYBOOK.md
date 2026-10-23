# Office PC: clone main, then report once

This PC cannot write the Office PC disk. Run the commands there, in a second PowerShell window. Leave the tunnel window open. The website on that laptop is `http://127.0.0.1:8080/`. Do not enrol again. Do not run `reset-password`. Do not use the parent folder `C:\Users\kokob\src\AI-PLAYBOOK.md`. That folder has no `integrations` directory and no `.git`. Do not `git pull` inside `AI-PLAYBOOK.md-main`.

The report command reads the device secret already stored on that laptop. Do not print the secret, and do not paste it into chat.

Commit `e8f966534a7f7d5b8409793bbdbede19596a0e78` is the one that keeps boot time, free memory, and CPU in the startup summary. A clone of current `main` contains it. The old downloaded folder does not.

```powershell
$dest = "C:\Users\kokob\src\AI-PLAYBOOK-clone"
if (Test-Path $dest) { throw "C:\Users\kokob\src\AI-PLAYBOOK-clone already exists. Do not copy over it." }
git clone --branch main --single-branch https://github.com/henokmeron/AI-PLAYBOOK.md.git $dest
Set-Location $dest
if (-not (Test-Path ".\integrations\endpoint_worker.py")) { throw "Stop. This folder does not contain integrations." }
git rev-parse HEAD
git merge-base --is-ancestor e8f966534a7f7d5b8409793bbdbede19596a0e78 HEAD
if ($LASTEXITCODE -ne 0) { throw "Stop. This clone does not contain the startup-summary commit." }
python -m integrations.endpoint_worker report --console http://127.0.0.1:8080 --token-file="$env:LOCALAPPDATA\AI-PLAYBOOK\device-secret"
```

Later updates, from that same clone only:

```powershell
Set-Location C:\Users\kokob\src\AI-PLAYBOOK-clone
git pull --ff-only origin main
python -m integrations.endpoint_worker report --console http://127.0.0.1:8080 --token-file="$env:LOCALAPPDATA\AI-PLAYBOOK\device-secret"
```

If `git` is not installed, stop and install Git for Windows. Do not turn the old zip folder into a repository. A downloaded zip of `main` is acceptable only when the folder you `Set-Location` into itself contains `integrations\endpoint_worker.py`. Then run only the `python -m integrations.endpoint_worker report` line above.

The worker will still print `acceptance_role=not-recorded-as-second-endpoint`. That line is expected. It means the worker does not mark the acceptance gate. The new report should include boot time, free memory, and CPU in the startup summary.
