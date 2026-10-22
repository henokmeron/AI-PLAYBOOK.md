"""Read-only GitHub origin and branch-tip check.

This does not commit, fetch, push, or change git config. A matching SHA is
not a deployment and it does not start the pod.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ops.release.package import ReleaseError, git_output

EXPECTED_ORIGIN = "https://github.com/henokmeron/AI-PLAYBOOK.md.git"
TRACKED_REFS = (
    "refs/heads/main",
    "refs/heads/feature/qwen-a100-start-hardening",
    "refs/heads/feature/qwen3.5-27b-integration",
)
FORCE_FLAGS = {"--force", "-f", "--force-with-lease", "--force-if-includes"}


class ParityError(RuntimeError):
    """The check failed. Nothing was written."""


def parse_remote_v(text: str) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if "\t" not in line:
            raise ParityError("remote -v line has no tab")
        name, rest = line.split("\t", 1)
        if rest.endswith(" (fetch)"):
            rows.append((name, rest[: -len(" (fetch)")], "fetch"))
        elif rest.endswith(" (push)"):
            rows.append((name, rest[: -len(" (push)")], "push"))
        else:
            raise ParityError("remote -v line is missing fetch or push")
    return rows


def require_origin(text: str) -> None:
    rows = parse_remote_v(text)
    fetch = [url for name, url, kind in rows if name == "origin" and kind == "fetch"]
    push = [url for name, url, kind in rows if name == "origin" and kind == "push"]
    if fetch != [EXPECTED_ORIGIN] or push != [EXPECTED_ORIGIN]:
        raise ParityError(
            "origin is not https://github.com/henokmeron/AI-PLAYBOOK.md.git. Nothing was changed."
        )


def parse_ls_remote(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            raise ParityError("ls-remote line is not sha and ref")
        sha, ref = parts
        if len(sha) != 40 or any(char not in "0123456789abcdef" for char in sha):
            raise ParityError("ls-remote sha is not 40 hex characters")
        found[ref] = sha
    return found


def require_matching_refs(found: dict[str, str]) -> str:
    missing = [ref for ref in TRACKED_REFS if ref not in found]
    if missing:
        raise ParityError("ls-remote is missing " + ", ".join(missing))
    shas = {found[ref] for ref in TRACKED_REFS}
    if len(shas) != 1:
        raise ParityError("published branch tips differ. Nothing was changed.")
    sha = next(iter(shas))
    if "HEAD" in found and found["HEAD"] != sha:
        raise ParityError("HEAD does not match the published branch tips")
    return sha


def refuse_force(args: list[str]) -> None:
    for arg in args:
        if arg in FORCE_FLAGS or (arg.startswith("+") and not arg.startswith("++")):
            raise ParityError("force push is refused. Nothing was changed.")


def check_repo(repo: Path, *, ls_remote: bool = False) -> str:
    """Return ``origin-ok`` or the shared published SHA.

    ``ls_remote`` contacts GitHub. It does not update the local checkout.
    """
    try:
        require_origin(git_output(repo, "remote", "-v"))
        if not ls_remote:
            return "origin-ok"
        text = git_output(repo, "ls-remote", "origin", "HEAD", *TRACKED_REFS)
    except ReleaseError as exc:
        raise ParityError(str(exc)) from exc
    return require_matching_refs(parse_ls_remote(text))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check origin and published branch tips.")
    parser.add_argument("--repo", default="")
    parser.add_argument("--ls-remote", action="store_true")
    args = parser.parse_args(argv)
    repo = Path(args.repo) if args.repo else Path(__file__).resolve().parents[1]
    try:
        result = check_repo(repo, ls_remote=args.ls_remote)
    except ParityError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if result == "origin-ok":
        print("origin-ok")
        print("ls-remote was not run")
    else:
        print(f"sha={result}")
        print("refs=main,feature/qwen-a100-start-hardening,feature/qwen3.5-27b-integration")
    print("a matching sha is not a deployment")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
