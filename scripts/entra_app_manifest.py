#!/usr/bin/env python3
"""Print the Entra application manifest fragment for Business AI local.

This does not call Microsoft, create an app, or print an application id.
Paste the fragment into an existing app registration after confirming the
name, or create one app with that name when the signed-in account may.
"""
from __future__ import annotations

import json
import sys

APP_NAME = "Business AI local"
REDIRECT = "http://127.0.0.1:18080/api/microsoft/callback"
GRAPH_DELEGATED = (
    "User.Read",
    "Mail.Read",
    "Chat.Read",
    "Files.Read",
    "Sites.Read.All",
)
DRAFT_OPTIONAL = ("Mail.ReadWrite",)
ARM_DELEGATED = ("user_impersonation",)


def manifest() -> dict:
    return {
        "displayName": APP_NAME,
        "signInAudience": "AzureADandPersonalMicrosoftAccount",
        "allowPublicClient": True,
        "isFallbackPublicClient": True,
        "replyUrlsWithType": [
            {"url": REDIRECT, "type": "InstalledClient"},
        ],
        "requiredResourceAccess": [
            {
                "resourceAppId": "00000003-0000-0000-c000-000000000000",
                "resourceAccess_note": (
                    "Add these as delegated Microsoft Graph permissions in the portal. "
                    "Do not add Mail.Send. Add Mail.ReadWrite only when unsent drafts are required."
                ),
                "delegatedPermissions": list(GRAPH_DELEGATED),
                "optionalDelegatedPermissions": list(DRAFT_OPTIONAL),
            },
            {
                "resourceAppId": "797f4846-ba00-4fd7-ba43-dac1f8f63013",
                "resourceAccess_note": (
                    "Azure Service Management. Add delegated user_impersonation for inventory reads only."
                ),
                "delegatedPermissions": list(ARM_DELEGATED),
            },
        ],
        "operator_steps": [
            "Open Entra ID → App registrations while signed in with an account that can create apps.",
            f"Reuse an app named {APP_NAME!r} if it already exists. Create only one if it is absent.",
            "Do not create a client secret.",
            "Set allowPublicClient / Treat application as a public client to Yes.",
            f"In the manifest, set replyUrlsWithType to InstalledClient {REDIRECT}.",
            "Add the read-only Graph permissions listed above. Sites.Read.All may need admin consent.",
            "Add Azure Service Management user_impersonation only for inventory.",
            "Copy the Application (client) ID into MICROSOFT_CLIENT_ID or a private MICROSOFT_CLIENT_ID_FILE.",
            "Do not paste the application id into Git or chat.",
        ],
    }


def main() -> int:
    sys.stdout.write(json.dumps(manifest(), indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
