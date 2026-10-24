# Register another Windows computer

The console mints a one-time enrolment code. That code lasts about 10 minutes (`expires_in_seconds` is 600) and works once. On the new computer, `integrations.endpoint_worker enrol` creates a device secret, stores it outside the repo, and exchanges the code for a new device id. `integrations.remote_worker serve` then polls the console with that secret and runs an approved job on this computer only.

The Office PC does not get a shell on the new computer. Mutual control (install apps, print, run commands) is the standing product goal. Today the channel is device-initiated: the new computer's own worker runs the allowlist on itself after a console job is approved for that device id. Enrolment returns `remote_control: false`. Do not mark `second_endpoint_worker_ok`. The worker prints `acceptance_role=not-recorded-as-second-endpoint`. That line is expected.

This path is the Python worker on a computer. It is not a phone enrolment. The registered collectors are the Windows checks. Do not run it on the Office PC (`bead5785f3674aaeb92c189f8c1b5b8c`). Do not run it on BANYA-FAMILY-PL. The worker refuses enrolment on that development PC unless the local fixture label is set, and that fixture does not count.

The console code can also start a TLS device gateway. That gateway is off unless `DEVICE_GATEWAY_ENABLED=1`, and it was not started for this registration. Minting a code stays on the loopback console (`POST /api/devices/enrolment`). The worker still uses the loopback tunnel, or HTTPS with certificate checks. Do not send enrolment to a public HTTP address.

The script does not change printer settings and does not clear a print queue. It does not print the device secret, and it does not write the enrolment code into a file.

## Repeat on each new computer

1. Install Python 3.11 or newer and Git for Windows.
2. Clone current `main` into a folder that itself contains `integrations\endpoint_worker.py`. Do not use the Office PC folder `C:\Users\kokob\src\AI-PLAYBOOK.md`, and do not turn an old zip into a git repo in place.
3. Leave an SSH tunnel open so the pod console is on loopback. The worker refuses plain HTTP to any other host. The Office PC uses `http://127.0.0.1:8080/`. This development PC uses `http://127.0.0.1:18080/` and must not enrol. On the new computer, local port 8080 matches the script default:

```powershell
ssh -N -L 8080:127.0.0.1:8080 -i $env:USERPROFILE\.ssh\id_ed25519 -p 48443 -o BatchMode=yes root@195.26.233.96
```

If 8080 is already taken, pick another local port and pass that origin as `-Console`.

4. In a second window, from the clone:

```powershell
Set-Location <clone>
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\register-device.ps1 -Name "Family Laptop"
```

Replace `Family Laptop` with a new display name. The script refuses `Office PC`, `BANYA-FAMILY-PL`, `not-the-second-endpoint`, and `bead5785f3674aaeb92c189f8c1b5b8c`. The name must be 1 to 40 letters, numbers, spaces, dots, or dashes, and must start with a letter or number.

With no `-Code`, the script prompts for the console operator and password, then calls `POST /api/auth/login` and `POST /api/devices/enrolment`. The operator needs `connectors:manage`. The password and the code stay in memory. To use a code already shown by IT Helpdesk, pass `-Code`. Put the code in that parameter. Use the equals form if you call the worker yourself, because a separate `--code` argument is not how a leading dash must be passed:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\register-device.ps1 -Name "Family Laptop" -Code "<one-time-code>" -Console "http://127.0.0.1:8080"
```

The script then runs, from the clone:

```text
python -m integrations.endpoint_worker enrol --console http://127.0.0.1:8080 --code=<one-time-code> --name "Family Laptop" --token-file <absolute token path>
python -m integrations.remote_worker serve --console http://127.0.0.1:8080 --token-file <absolute token path>
```

The token path is `%LOCALAPPDATA%\AI-PLAYBOOK\device-secret` unless `-TokenFile` is an absolute path outside the clone. The secret file is created before the code is sent. If the console refuses the code, that new file is deleted. An existing secret file is not replaced.

5. Leave the worker window open. `serve` posts a heartbeat and polls about every 5 seconds. It does not pass `--live`, so it does not install software or print. Ctrl+C stops polling. The device stays enrolled. Run the same script again to start the worker. The second run sees the secret file and does not enrol again.

The device list is `GET /api/devices` on the signed-in loopback console. After enrolment the new id appears there with its display name. The Office PC can see that row. It still cannot drive the other computer. A later approved console job for the new device id is what that device's worker can run.

## Same commands without the script

Mint the code in the signed-in console (`POST /api/devices/enrolment` or the IT Helpdesk enrolment button). The button's sample command uses `--name="Office PC"`. Do not use that name for a second computer. On the new computer, within about 10 minutes:

```powershell
Set-Location <clone>
python -m integrations.endpoint_worker enrol --console http://127.0.0.1:8080 --code=<one-time-code> --name "Family Laptop" --token-file="$env:LOCALAPPDATA\AI-PLAYBOOK\device-secret"
python -m integrations.remote_worker serve --console http://127.0.0.1:8080 --token-file="$env:LOCALAPPDATA\AI-PLAYBOOK\device-secret"
```

`--code=<one-time-code>` is one argument. Do not put the code in git, a log, or chat after it has been used. Do not print the token file.
