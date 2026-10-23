#!/usr/bin/env python3
"""Privacy-safe mailbox verification CLI entrypoint.

This script provides a command-line interface to verify mailbox access
without exposing personal data. It can use live credentials when configured
or synthetic fixtures for testing.

Usage:
    # Live verification (requires MICROSOFT_CLIENT_ID)
    python3 -m integrations.verify_mailbox --positive "project-alpha-2024"
    python3 -m integrations.verify_mailbox --negative "nonexistent-uuid-12345"
    
    # Synthetic fixture testing (no credentials needed)
    python3 -m integrations.verify_mailbox --synthetic
    
    # Full verification suite
    python3 -m integrations.verify_mailbox --all --positive "my-phrase" --negative "no-match"

Exit codes:
    0 - All verifications passed
    1 - One or more verifications failed
    2 - Configuration error (missing credentials or invalid phrases)
    3 - Not configured (MICROSOFT_CLIENT_ID missing)

Privacy guarantee: Records ONLY status codes, counts, and boolean indicators.
Never logs subject lines, bodies, senders, or other personal data.
"""
import argparse
import json
import os
import sys
from pathlib import Path

# Support both direct execution and module execution
if __package__:
    from .mail_verification import MailboxVerificationHarness
    from .microsoft_oauth import MicrosoftOAuth, client_id_source
else:
    from mail_verification import MailboxVerificationHarness
    from microsoft_oauth import MicrosoftOAuth, client_id_source


def main() -> int:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Privacy-safe mailbox verification",
        epilog="Records ONLY: status, counts, match indicators. Never logs personal data."
    )
    
    parser.add_argument(
        "--positive",
        metavar="PHRASE",
        help="Distinctive phrase for positive match test (NOT generic words like 'the')"
    )
    parser.add_argument(
        "--negative",
        metavar="PHRASE",
        help="Phrase that should NOT match (e.g., random UUID)"
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Run synthetic fixture tests (no credentials needed)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all verification types (requires --positive and --negative)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/mailbox-verification-results.json"),
        help="Output path for results (default: /tmp/mailbox-verification-results.json)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output, only show summary"
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.all and (not args.positive or not args.negative):
        print("ERROR: --all requires both --positive and --negative phrases", file=sys.stderr)
        return 2
    
    if not args.positive and not args.negative and not args.synthetic and not args.all:
        parser.print_help()
        return 2
    
    # Check configuration
    source = client_id_source(os.environ)
    if not source and (args.positive or args.negative or args.all):
        print("ERROR: Microsoft 365 is NOT CONFIGURED", file=sys.stderr)
        print("Set MICROSOFT_CLIENT_ID or MICROSOFT_CLIENT_ID_FILE environment variable", file=sys.stderr)
        print("Synthetic fixtures can run without credentials (use --synthetic)", file=sys.stderr)
        return 3
    
    # Initialize OAuth and harness
    oauth = None
    if source:
        oauth = MicrosoftOAuth.from_env()
        if not args.quiet:
            print(f"Configuration: {source} present")
            if oauth.bundle:
                print(f"Connected: {oauth.bundle.account}")
            else:
                print("Connected: No (sign-in required)")
    
    harness = MailboxVerificationHarness(oauth=oauth, result_path=args.output)
    
    # Run verifications
    failed = False
    
    try:
        if args.synthetic or args.all:
            if not args.quiet:
                print("\n=== Synthetic Fixture Tests ===")
            
            # Test with results
            result1 = harness.verify_with_synthetic_fixture({
                "http_status": 200,
                "value": [{"id": "msg-1"}, {"id": "msg-2"}],
            })
            if not args.quiet:
                print(f"  With results: {_format_result(result1)}")
            if not result1.success:
                failed = True
            
            # Test empty results
            result2 = harness.verify_with_synthetic_fixture({
                "http_status": 200,
                "value": [],
            })
            if not args.quiet:
                print(f"  Empty result: {_format_result(result2)}")
            if not result2.success:
                failed = True
        
        if args.positive or args.all:
            if not args.quiet:
                print("\n=== Positive Match Verification ===")
            
            result = harness.verify_positive_match(args.positive)
            if not args.quiet:
                print(f"  Search phrase: (provided by owner)")
                print(f"  Result: {_format_result(result)}")
            
            if not result.success:
                print(f"ERROR: Positive match verification FAILED: {result.error_type}", file=sys.stderr)
                failed = True
            elif not result.expected_match_found:
                print(f"WARNING: Positive match found 0 results (expected > 0)", file=sys.stderr)
                print("  Check that the phrase matches messages in the mailbox", file=sys.stderr)
        
        if args.negative or args.all:
            if not args.quiet:
                print("\n=== Negative Match Verification ===")
            
            result = harness.verify_negative_match(args.negative)
            if not args.quiet:
                print(f"  Unmatched phrase: (provided by owner)")
                print(f"  Result: {_format_result(result)}")
            
            if not result.success:
                print(f"ERROR: Negative match verification FAILED: {result.error_type}", file=sys.stderr)
                failed = True
            elif not result.expected_match_found:
                print(f"SUCCESS: Negative match returned 0 results (correct)", file=sys.stderr)
    
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    
    except Exception as exc:
        print(f"ERROR: Unexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    
    # Print summary
    if not args.quiet:
        print("\n=== Summary ===")
    
    summary = harness.summary()
    print(f"Total tests: {summary['total_tests']}")
    print(f"Successful: {summary['successful_tests']}")
    print(f"Positive matches: {summary['positive_matches_verified']}")
    print(f"Negative matches: {summary['negative_matches_verified']}")
    print(f"Synthetic fixtures: {summary['synthetic_fixtures']}")
    print(f"Live mailbox verified: {'YES' if summary['live_mailbox_verified'] else 'NO'}")
    
    if args.output.exists():
        print(f"\nResults saved to: {args.output}")
        if not args.quiet:
            print("(Privacy-safe: contains only status, counts, boolean indicators)")
    
    return 0 if not failed else 1


def _format_result(result) -> str:
    """Format a verification result for display."""
    if result.success:
        status = f"SUCCESS (HTTP {result.http_status})"
        details = f"count={result.result_count}, match={result.expected_match_found}"
        return f"{status} - {details}"
    else:
        return f"FAILED ({result.error_type})"


if __name__ == "__main__":
    sys.exit(main())
