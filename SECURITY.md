# Security policy

## Reporting a vulnerability

Please report security issues privately, not in a public issue:

1. Go to the repository's **Security** tab.
2. Click **Report a vulnerability** to open a private advisory.

Include what you found, the steps to reproduce it, and the version (**About** in the sidebar). You'll get a
reply as soon as possible, and credit in the release notes once it's fixed, if you'd like.

## Supported versions

Security fixes go into the latest release. Please upgrade before reporting.

## How SSH Manager handles your data

- It stores your server list in a local JSON file and never sends it anywhere.
- It stores only the *path* to each SSH key, never the key itself.
- Connections use your system's OpenSSH client, with its normal host-key checks.
- It has no telemetry, accounts or network services, and it only connects to the servers in your list.
