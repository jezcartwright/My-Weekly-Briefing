"""One-shot auth check. Reads GMAIL_SA_JSON env var, builds the service,
lists drafts (read-only), and reports. Used to verify the credential chain
works before relying on it in production. Run via:
    GMAIL_SA_JSON=$(cat /path/to/key.json) python smoke_test_mailer.py
"""
import os
import sys

if not os.environ.get("GMAIL_SA_JSON"):
    print("ERROR: GMAIL_SA_JSON not set", file=sys.stderr)
    sys.exit(1)

try:
    from mailer import list_drafts
    drafts = list_drafts(max_results=3)
    print(f"✓ Auth works. Found {len(drafts)} recent draft(s) in jc@'s inbox.")
    for d in drafts:
        print(f"  draft id: {d.get('id')}")
    sys.exit(0)
except Exception as e:
    import traceback
    print(f"✗ Auth FAILED: {type(e).__name__}: {e}", file=sys.stderr)
    print(traceback.format_exc(), file=sys.stderr)
    print()
    print("Common causes:", file=sys.stderr)
    print("  - Domain-wide delegation not yet propagated (wait 10 min after setup)",
          file=sys.stderr)
    print("  - Service account not granted gmail.send/gmail.compose scopes",
          file=sys.stderr)
    print("  - DELEGATE_USER in mailer.py doesn't match a real Workspace user",
          file=sys.stderr)
    print("  - GMAIL_SA_JSON content malformed or wrong project's key",
          file=sys.stderr)
    sys.exit(1)
