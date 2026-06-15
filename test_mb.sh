#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_DIR=$(mktemp -d)

echo "Test directory: $TEST_DIR"
echo ""

cleanup() {
    cd "$SCRIPT_DIR"
    rm -rf "$TEST_DIR"
}
trap cleanup EXIT

cd "$TEST_DIR"

gg() {
    PYTHONPATH="$SCRIPT_DIR" python -m gg "$@"
}

git init
git config user.email "test@test.com"
git config user.name "Test"

echo "main-1" > main-1.txt
git add main-1.txt
git commit -m "main-1"

echo "main-2" > main-2.txt
git add main-2.txt
git commit -m "main-2"

git checkout -b feature1
echo "feature1-1" > feature1-1.txt
git add feature1-1.txt
git commit -m "feature1-1"

git checkout main

git remote add origin "$TEST_DIR/.git"
git push -u origin main feature1

echo ""
echo "=== Initial state ==="
echo "Branches:"
git branch -v
echo ""

echo "=== Update origin/main ==="
echo "main-3" > main-3.txt
git add main-3.txt
git commit -m "main-3"
git push origin main

git checkout main

echo ""
echo "=== Running mb feature1 ==="
gg mb feature1

echo ""
echo "=== After mb ==="
echo "Current branch:"
git branch --show-current
echo ""
echo "Worktrees:"
git worktree list
echo ""

echo "=== Verify merge happened ==="
if git log --oneline feature1 | grep -q "main-3"; then
    echo "PASS: feature1 has merged origin/main"
else
    echo "FAIL: feature1 should have origin/main merged"
    exit 1
fi

echo ""
echo "SUCCESS!"
