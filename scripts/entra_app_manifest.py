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
)
DRAFT_OPTIONAL = ("Mail.ReadWrite",)
# Not requested on the initial sign-in. Do not add these until a later approval.
NOT_REQUESTED = (
    "Chat.Read",
    "Files.Read",
    "Sites.Read.All",
    "Mail.Send",
    "user_impersonation",
)


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
                "notRequested": list(NOT_REQUESTED),
            },
        ],
        "operator_steps": [
            "Open Entra ID → App registrations while signed in with an account that can edit apps.",
            "Reuse the existing registration when it can hold this redirect and Mail.Read. Do not create a second app.",
            "Do not create or display a client secret.",
            "Set isFallbackPublicClient / Treat application as a public client to Yes.",
            f"In the public client redirect URIs, add {REDIRECT}.",
            "Add delegated User.Read and Mail.Read only. Do not add Mail.Send, Mail.ReadWrite, or the notRequested scopes.",
            "If the app is single-tenant, set MICROSOFT_TENANT to that directory. Do not leave it as common.",
            "Copy the Application (client) ID into MICROSOFT_CLIENT_ID or a private MICROSOFT_CLIENT_ID_FILE.",
            "Do not paste the application id into Git.",
        ],
    }


def main() -> int:
    sys.stdout.write(json.dumps(manifest(), indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
