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

git remote add origin "$TEST_DIR/.git"
git push -u origin main

git checkout -b feature1
echo "feature1-a" > file-a.txt
echo "feature1-b" > file-b.txt
git add file-a.txt file-b.txt
git commit -m "feature1 changes"

git checkout main
git push -u origin feature1

echo ""
echo "=== Running wc (comparing feature1 to main) ==="
output=$(gg wc main...feature1 2>&1) || true

echo "$output"

echo ""
echo "=== Verify output ==="
if echo "$output" | grep -q "file-a.txt"; then
    echo "PASS: output contains file-a.txt"
else
    echo "FAIL: output should contain file-a.txt"
    exit 1
fi

if echo "$output" | grep -q "file-b.txt"; then
    echo "PASS: output contains file-b.txt"
else
    echo "FAIL: output should contain file-b.txt"
    exit 1
fi

echo ""
echo "SUCCESS!"
