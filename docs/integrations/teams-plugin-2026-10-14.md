# Teams plugin inspection — 2026-10-14

Cursor had the Teams plugin enabled, but the install did not finish. This file records what was on disk and what the plugin actually is. It is a Cursor development tool. It is not the Microsoft 365 connector for this platform.

## What failed

Cursor's plugin log says:

`Cursor plugin load error teams@837067b75aa20ab58d7b2a2f6c0531e37118c596: spawn git ENOENT`

`git` is not on the Windows PATH in this session (`where.exe git` finds nothing). Cursor tries to clone the plugin with `git` and stops. The same error hit the newer GitHub and Gmail plugin versions. A reload would not succeed until `git` can be started or the files are already in the cache.

Expected cache path:

`C:\Users\henok\.cursor\plugins\cache\cursor-public\teams\837067b75aa20ab58d7b2a2f6c0531e37118c596`

That directory was empty. The files are now copied there from the public repository, plus the empty `.cache-complete` marker used by the other cached plugins. Measured size: **5,796 bytes**, 7 files. No executables and no dependencies.

This chat still cannot call Teams tools. Cursor has not reloaded the plugin host, and the remote server rejects calls that do not carry a Cursor credential.

## Identity

| Item | Value |
| --- | --- |
| Identifier | `teams` |
| Display name | Teams |
| Version | 1.0.0 |
| Source | https://github.com/cursor/plugins path `third_party/teams` |
| Commit Cursor requested | `837067b75aa20ab58d7b2a2f6c0531e37118c596` |
| First commit of this folder | `3f44ff568693588e1f315ac3e397f6d4e2e68474` (2026-09-09) |
| Licence of the plugin files | MIT, copyright 2026 Cursor |
| Minimum Cursor version | 3.19.0 |

The plugin contains a manifest, README, changelog, licence, logo, and `mcp.json`. It contains no Teams implementation.

`mcp.json` points at `https://api.cursor.com/rest-mcp/teams/mcp`. An unauthenticated initialize request returned HTTP 401: `Missing Cursor credential in x-cursor-auth`. The README says Cursor then signs the user in to Microsoft with OAuth, and that reading channel messages needs a work or school account plus tenant admin consent.

## Decision

Do not copy this plugin into the platform and do not call `api.cursor.com` from the product. Customers would depend on Cursor being installed and on Cursor's credential. The platform connector will use Microsoft Graph with the customer's own consent, behind the existing approval and audit rules. That client is not built yet. The catalog entry is `microsoft365` and it refuses every call until an account is connected.
