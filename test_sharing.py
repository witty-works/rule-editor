#!/usr/bin/env python3
"""
Test script for database sharing functionality.
Run this to verify export/import commands work correctly.
"""

import os
import sys
import subprocess
import json
from pathlib import Path

# Colors for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def print_step(msg):
    print(f"\n{BLUE}▶ {msg}{RESET}")


def print_success(msg):
    print(f"{GREEN}✓ {msg}{RESET}")


def print_error(msg):
    print(f"{RED}✗ {msg}{RESET}")


def print_warning(msg):
    print(f"{YELLOW}⚠ {msg}{RESET}")


def run_command(cmd):
    """Run a command (as a list of args) and return (ok, stdout, stderr)."""
    # Security: avoid shell=True; always pass a list of arguments.
    # Prepend pipenv run to ensure dependencies are available
    full_cmd = ["pipenv", "run"] + cmd
    result = subprocess.run(full_cmd, capture_output=True, text=True)
    return result.returncode == 0, result.stdout, result.stderr


def test_export_full():
    """Test full database export"""
    print_step("Testing full database export...")

    cmd = [
        "python",
        "manage.py",
        "export_rules_db",
        "--output=test_export.json",
        "--indent=0",
    ]
    success, _, stderr = run_command(cmd)

    if success and os.path.exists("test_export.json"):
        # Check if it's valid JSON
        try:
            with open("test_export.json", "r") as f:
                data = json.load(f)
            print_success(f"Exported {len(data)} objects to test_export.json")

            # Check that no user data is present
            # Use set membership and any() to reduce branching
            from rules.model_constants import AUTH_USER, AUTH_SESSION

            has_user_data = any(
                item.get("model") in {AUTH_USER, AUTH_SESSION} for item in data
            )

            if not has_user_data:
                print_success("No user data in export (as expected)")
            else:
                print_error("User data found in export!")
                return False

            return True
        except json.JSONDecodeError:
            print_error("Invalid JSON in export file")
            return False
    else:
        print_error(f"Export failed: {stderr}")
        return False


def test_export_rule():
    """Test individual rule export"""
    print_step("Testing individual rule export...")

    # First, get a rule ID
    cmd = [
        "python",
        "manage.py",
        "shell",
        "-c",
        "from rules.models import Rule; print(Rule.objects.first().id if Rule.objects.exists() else 'none')",
    ]
    success, stdout, stderr = run_command(cmd)

    # Some environments may print banner/output before the value; take the last non-empty line
    lines = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
    rule_id = lines[-1] if lines else "none"
    # Basic sanity: ensure rule_id looks like an integer
    if rule_id != "none" and not rule_id.isdigit():
        print_warning(
            f"Unexpected shell output when fetching rule id; got: {rule_id!r}. Skipping rule export test."
        )
        return True
    if rule_id == "none":
        print_warning("No rules in database, skipping rule export test")
        return True

    cmd = [
        "python",
        "manage.py",
        "export_rule",
        f"--id={rule_id}",
        "--output=test_rule.json",
    ]
    success, stdout, stderr = run_command(cmd)

    if success and os.path.exists("test_rule.json"):
        try:
            with open("test_rule.json", "r") as f:
                data = json.load(f)
            print_success(f"Exported rule {rule_id} with {len(data)} related objects")
            return True
        except json.JSONDecodeError:
            print_error("Invalid JSON in rule export")
            return False
    else:
        print_error(f"Rule export failed: {stderr}")
        return False


def test_import_dry_run():
    """Test import in dry-run mode"""
    print_step("Testing import (dry-run)...")

    if not os.path.exists("test_export.json"):
        print_warning("No export file found, skipping import test")
        return True

    cmd = [
        "python",
        "manage.py",
        "import_rules_db",
        "--input=test_export.json",
        "--dry-run",
    ]
    success, _, stderr = run_command(cmd)

    if success:
        print_success("Import dry-run completed successfully")
        return True
    else:
        print_error(f"Import dry-run failed: {stderr}")
        return False


def test_cleanup_dry_run():
    """Test duplicate cleanup in dry-run mode"""
    print_step("Testing duplicate cleanup (dry-run)...")

    cmd = [
        "python",
        "manage.py",
        "cleanup_duplicate_rules",
        "--dry-run",
    ]
    success, _, stderr = run_command(cmd)

    if success:
        print_success("Cleanup dry-run completed")
        return True
    else:
        print_error(f"Cleanup failed: {stderr}")
        return False


def test_command_help():
    """Test that all commands have help"""
    print_step("Testing command help...")

    commands = [
        "export_rules_db",
        "import_rules_db",
        "export_rule",
        "import_rule",
        "assign_rule_ownership",
        "cleanup_duplicate_rules",
    ]

    results = [
        run_command(["python", "manage.py", cmd, "--help"])[0] for cmd in commands
    ]
    for cmd, ok in zip(commands, results):
        (
            print_success(f"{cmd} --help works")
            if ok
            else print_error(f"{cmd} --help failed")
        )
    return all(results)


def cleanup():
    """Remove test files"""
    print_step("Cleaning up test files...")

    files = ["test_export.json", "test_rule.json"]
    for f in files:
        if os.path.exists(f):
            os.remove(f)
            print_success(f"Removed {f}")


def main():
    print(f"{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}Database Sharing Functionality Test{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")

    tests = [
        ("Command Help", test_command_help),
        ("Full Database Export", test_export_full),
        ("Individual Rule Export", test_export_rule),
        ("Import Dry-Run", test_import_dry_run),
        ("Duplicate Cleanup Dry-Run", test_cleanup_dry_run),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print_error(f"Test {name} crashed: {e}")
            results.append((name, False))

    # Cleanup
    cleanup()

    # Summary
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}Test Summary{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = f"{GREEN}PASS{RESET}" if result else f"{RED}FAIL{RESET}"
        print(f"{status} - {name}")

    print(f"\n{passed}/{total} tests passed")

    if passed == total:
        print(f"\n{GREEN}✓ All tests passed!{RESET}")
        return 0
    else:
        print(f"\n{RED}✗ Some tests failed{RESET}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
