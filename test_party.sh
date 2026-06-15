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

# Setup
git init
git config user.email "test@test.com"
git config user.name "Test"

echo "main-1" > main-1.txt
git add main-1.txt
git commit -m "main-1"

echo "main-2" > main-2.txt
git add main-2.txt
git commit -m "main-2"

echo "main-3" > main-3.txt
git add main-3.txt
git commit -m "main-3"

git checkout -b feature1
echo "feature1-1" > feature1-1.txt
git add feature1-1.txt
git commit -m "feature1-1"

echo "feature1-2" > feature1-2.txt
git add feature1-2.txt
git commit -m "feature1-2"

echo "feature1-3" > feature1-3.txt
git add feature1-3.txt
git commit -m "feature1-3"

git checkout main
git checkout -b feature2
echo "feature2-1" > feature2-1.txt
git add feature2-1.txt
git commit -m "feature2-1"

echo "feature2-2" > feature2-2.txt
git add feature2-2.txt
git commit -m "feature2-2"

echo "feature2-3" > feature2-3.txt
git add feature2-3.txt
git commit -m "feature2-3"

git checkout main

echo ""
echo "=== Initial state ==="
echo "Branches:"
git branch -v
echo ""

echo "=== party start ==="
gg party start myparty feature1 feature2

echo ""
echo "=== After party start ==="
echo "Current branch:"
git branch --show-current
echo ""
echo "Worktrees:"
git worktree list
echo ""
echo "party/myparty commits:"
git log --oneline party/myparty
echo ""
echo "Commits unique to party/myparty (not in main,feature1,feature2):"
git log --oneline --no-merges party/myparty ^main ^feature1 ^feature2 || echo "(none)"

echo ""
echo "=== Making changes on party/myparty ==="
echo "work-1" > work-1.txt
git add work-1.txt
git commit -m "work-1"

echo "work-2" > work-2.txt
git add work-2.txt
git commit -m "work-2"

echo ""
echo "=== After making changes ==="
echo "party/myparty commits:"
git log --oneline party/myparty
echo ""
echo "Commits unique to party/myparty:"
git log --oneline --no-merges party/myparty ^main ^feature1 ^feature2 || echo "(none)"

echo ""
echo "=== party sync ==="
gg party sync

echo ""
echo "=== After sync ==="
echo "main commits:"
git log --oneline main
echo ""
echo "party/myparty commits:"
git log --oneline party/myparty
echo ""
echo "Commits unique to party/myparty:"
git log --oneline --no-merges party/myparty ^main ^feature1 ^feature2 || echo "(none)"

echo ""
echo "=== party finish ==="
gg party finish

echo ""
echo "=== Final state ==="
echo "Current branch:"
git branch --show-current
echo ""
echo "main commits:"
git log --oneline main
echo ""
echo "All branches:"
git branch

echo ""
echo "SUCCESS!"
