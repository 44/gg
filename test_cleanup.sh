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
git merge feature1 --no-edit

git checkout -b feature2
echo "feature2-1" > feature2-1.txt
git add feature2-1.txt
git commit -m "feature2-1"

git checkout main
git merge feature2 --no-edit

git checkout -b feature3
echo "feature3-1" > feature3-1.txt
git add feature3-1.txt
git commit -m "feature3-1"

git checkout main

git checkout -b feature4
echo "feature4-1" > feature4-1.txt
git add feature4-1.txt
git commit -m "feature4-1"

git checkout main

echo ""
echo "=== Initial state ==="
echo "Branches:"
git branch
echo ""

echo "=== Running cleanup dry-run ==="
gg cleanup --dry-run
echo ""

echo "=== Verify branches still exist after dry-run ==="
for branch in feature1 feature2 feature3 feature4; do
    if git rev-parse --verify "$branch" >/dev/null 2>&1; then
        echo "$branch still exists - OK"
    else
        echo "FAIL: $branch should still exist"
        exit 1
    fi
done

echo ""
echo "=== Running cleanup ==="
gg cleanup

echo ""
echo "=== Verify branches after cleanup ==="
echo "feature1 (merged, no ahead commits) - should be deleted:"
if git rev-parse --verify "feature1" >/dev/null 2>&1; then
    echo "FAIL: feature1 should be deleted"
    exit 1
else
    echo "Deleted - OK"
fi

echo "feature2 (merged, no ahead commits) - should be deleted:"
if git rev-parse --verify "feature2" >/dev/null 2>&1; then
    echo "FAIL: feature2 should be deleted"
    exit 1
else
    echo "Deleted - OK"
fi

echo "feature3 (not merged into main) - should remain:"
if git rev-parse --verify "feature3" >/dev/null 2>&1; then
    echo "Exists - OK"
else
    echo "FAIL: feature3 should exist"
    exit 1
fi

echo "feature4 (not merged into main) - should remain:"
if git rev-parse --verify "feature4" >/dev/null 2>&1; then
    echo "Exists - OK"
else
    echo "FAIL: feature4 should exist"
    exit 1
fi

echo ""
echo "=== Current branch should not be deleted ==="
git checkout feature3
gg cleanup
if git rev-parse --verify "feature3" >/dev/null 2>&1; then
    echo "Current branch not deleted - OK"
else
    echo "FAIL: current branch should not be deleted"
    exit 1
fi

echo ""
echo "=== Test with remote branches (should be preserved) ==="
git checkout main
git remote add origin "$TEST_DIR/.git"
git push -u origin main feature3

git checkout feature3
echo "feature3-2" > feature3-2.txt
git add feature3-2.txt
git commit -m "feature3-2"
git push origin feature3

git checkout main
git merge feature3 --no-edit
git push origin main

echo "Branches before cleanup:"
git branch -vv
echo ""

gg cleanup

echo ""
echo "feature3 (has upstream) - should remain:"
if git rev-parse --verify "feature3" >/dev/null 2>&1; then
    echo "Exists - OK"
else
    echo "FAIL: feature3 with upstream should exist"
    exit 1
fi

echo ""
echo "=== Test branch NOT merged but has additional commits on main (should not be deleted) ==="
git checkout -b feature5
echo "feature5-1" > feature5-1.txt
git add feature5-1.txt
git commit -m "feature5-1"

git checkout main
echo "main-2" > main-2.txt
git add main-2.txt
git commit -m "main-2"

echo "Branches before cleanup:"
git branch
echo ""

gg cleanup

echo ""
echo "feature5 (not merged into main) - should remain:"
if git rev-parse --verify "feature5" >/dev/null 2>&1; then
    echo "Exists - OK"
else
    echo "FAIL: feature5 not merged should exist"
    exit 1
fi

echo ""
echo "SUCCESS!"
