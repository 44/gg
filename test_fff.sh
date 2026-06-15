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
git checkout -b feature2
echo "feature2-1" > feature2-1.txt
git add feature2-1.txt
git commit -m "feature2-1"

git checkout main

git remote add origin "$TEST_DIR/.git"

git push -u origin main feature1 feature2

git checkout feature1
echo "feature1-2" > feature1-2.txt
git add feature1-2.txt
git commit -m "feature1-2"

git push origin feature1

git checkout main

echo ""
echo "=== Initial state ==="
echo "Branches:"
git branch -v
echo ""

echo "=== Running fff ==="
gg fff

echo ""
echo "=== After fff ==="
echo "feature1 commits:"
git log --oneline feature1
echo ""

echo "=== Verify fast-forward happened ==="
if git log --oneline main | grep -q "feature1-2"; then
    echo "FAIL: main should not have feature1-2 yet"
    exit 1
fi
echo "Correct: main does not have feature1-2 yet"

echo ""
echo "=== Update origin/main ==="
git checkout main
git merge origin/main --no-edit || git merge origin/main

echo ""
echo "=== Running fff again ==="
gg fff

echo ""
echo "=== After fff ==="
echo "feature1 commits:"
git log --oneline feature1

echo ""
echo "SUCCESS!"
