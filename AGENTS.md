# AGENTS.md - gg Project

## Project Overview

gg is a collection of git productivity tools/scripts. It provides:

- **fff (fetch-fast-forward)**: Fetches upstream for all local branches and fast-forwards those that can be fast-forwarded.
- **pff (push-fast-forward)**: Pushes all local branches to their upstream, but only if they can be fast-forwarded.
- **ms (merge-switch)**: Merges specified branch with the default branch of upstream, then switches to it. Merge happens in separate worktree.
- **party**: A mode for working on multiple branches together - see PARTY_DESIGN.md for details.

## Development

### Running the tool

```bash
PYTHONPATH=. python -m gg <command>
```

Or install with `pip install -e .` and run as `gg <command>`.

### Testing

**CRITICAL: Never run tests directly in the project repository.**

This project performs git operations including potentially destructive ones (branch deletion, force pushes, worktree manipulation). Testing in the project repo will break it.

#### Testing Procedure

1. **Always create an isolated test environment** before starting any testing work.

2. **Prepare a testing script** that:
   - Creates a temporary directory using `mktemp -d`
   - Initializes a fresh git repo in that directory
   - Sets up the test scenario (branches, commits, etc.)
   - Runs the gg commands being tested
   - Verifies expected outcomes
   - Cleans up the temp directory on exit using a trap

3. **Testing script template**:

```bash
#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_DIR=$(mktemp -d)

echo "Test directory: $TEST_DIR"

cleanup() {
    cd "$SCRIPT_DIR"
    rm -rf "$TEST_DIR"
}
trap cleanup EXIT

cd "$TEST_DIR"

gg() {
    PYTHONPATH="$SCRIPT_DIR" python -m gg "$@"
}

# Setup test repo
git init
git config user.email "test@test.com"
git config user.name "Test"

# ... setup test scenario ...

# Run tests
gg party start myparty feature1 feature2

# Verify results
echo "party/myparty commits:"
git log --oneline party/myparty

echo "SUCCESS!"
```

4. **Run the test script**:

```bash
chmod +x test_party.sh
./test_party.sh
```

5. **Run all tests**:

```bash
just test
```

5. **Commit testing scripts** - All test scripts must be committed to the repository. They serve as:
   - Examples for creating new test scripts
   - Regression test suite for CI/CD
   - Documentation of expected behavior

#### Test Script Requirements

- Use `set -e` to fail on any error
- Always cleanup with a trap
- Use absolute paths or track the script directory
- Verify expected outcomes with assertions
- Print clear success/failure messages
- Test both positive and negative cases (error handling)

#### Existing Test Scripts

- `test_party.sh` - Comprehensive test for party mode functionality. Use as reference for new tests.
- `test_fff.sh` - Test fetch-fast-forward command
- `test_pff.sh` - Test push-fast-forward command
- `test_ms.sh` - Test merge-switch command
- `test_mb.sh` - Test merge-origin-default-branch command
- `test_wc.sh` - Test wc (word count) command

### Code Style

- Use Python type hints
- Follow existing patterns in the codebase
- Keep functions focused and small
