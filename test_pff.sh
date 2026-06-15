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

git checkout -b feature1
echo "feature1-1" > feature1-1.txt
git add feature1-1.txt
git commit -m "feature1-1"

git checkout main

git remote add origin "$TEST_DIR/.git"

git push -u origin main feature1

echo ""
echo "=== Initial state ==="
echo "feature1 commits:"
git log --oneline feature1
echo ""

echo "=== Making local commits on feature1 ==="
git checkout feature1
echo "feature1-2" > feature1-2.txt
git add feature1-2.txt
git commit -m "feature1-2"

echo ""
echo "=== feature1 is ahead of origin/feature1 ==="
echo "ahead/behind:"
git rev-list --left-right --count feature1...origin/feature1

echo ""
echo "=== Running pff ==="
gg pff

echo ""
echo "=== After pff ==="
echo "origin/feature1 commits:"
git log --oneline origin/feature1

echo ""
echo "=== Verify push happened ==="
if git log --oneline origin/feature1 | grep -q "feature1-2"; then
    echo "PASS: origin/feature1 has feature1-2"
else
    echo "FAIL: origin/feature1 should have feature1-2"
    exit 1
fi

echo ""
echo "SUCCESS!"
