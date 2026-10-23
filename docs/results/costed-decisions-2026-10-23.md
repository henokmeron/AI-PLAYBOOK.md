# Costed decisions — weight copy and Blackwell

Date: 2026-10-23. Nothing in this note was purchased. No pod was created. No weight file was copied. No Azure resource was created.

## Already running

| Item | Recorded cost | Decision |
| --- | --- | --- |
| Pod `1jyrnyxpb0n93s`, A100-SXM4-80GB, name `continuous_green_cephalopod` | about $1.80 per hour while it is running | Leave it. Do not click Stop from this session. Do not start a second pod. |
| Global Volume `cmv2p5m0d000007jk9o3931ea` | 126.0 GB stored, $11.34 per month | Leave it. This is the only copy of the weights. |
| Stopped H100 `xx9cjogra5vcwl` | $0 while stopped | Do not start it. |

The GPU charge stops when the owner stops the pod. The volume charge continues.

## Independent weight backup — do not buy

The Qwen weights are about 52 GB, 11 shard files, at `/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654`. They were not re-hashed for this note. Code is on GitHub and in local release archives. Those archives do not contain the weights.

A copy on the same volume is not an independent backup. A real backup needs a second destination the owner names. No destination is named. No second volume, bucket, or disk has an approved monthly price. Creating one would be a new charge on top of $11.34 per month, plus the time to write about 52 GB. That charge is not approved here.

Decision: do not copy the weights. The mandatory board does not require this gate. It stays open and non-mandatory.

## Blackwell — do not buy

`docs/runbooks/REMAINING_GATES.md` records no Blackwell hourly price. This note does not invent one.

What is known:

- The saved A100 runtime is torch `2.13.0+cu126`. The Blackwell lock rejects that build. It asks for compute capability 12 or higher, driver 575 or newer, CUDA 12.9, vLLM `0.32.0+cu129`, and torch `2.13.0+cu129`.
- The start script waits up to 2,700 seconds (45 minutes) for a load. Older cold loads were 7 to 21 minutes. The load that reached health on this A100 took 1 hour 16 minutes. A Blackwell pod would spend its own hourly rate for at least that long before it answers.
- A Blackwell pod beside the running A100 would add that unnamed hourly rate on top of about $1.80 per hour. Replacing the A100 is still a new pod start. Neither is approved.
- The owner has not named the GPU SKU.

Decision: do not start a Blackwell pod, and do not start the stopped H100. The gate stays NO-GO until the owner names the SKU, accepts the hourly price RunPod shows for that SKU, and accepts the load time.
