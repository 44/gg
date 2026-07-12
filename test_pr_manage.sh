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

echo "=== Test 1: _format_manage_content with sample PR data ==="
python3 -c "
import json, sys
sys.path.insert(0, '$SCRIPT_DIR')
from gg.cmd_pr import _format_manage_content

pr = {
    'pullRequestId': 42,
    'title': 'My test PR',
    'description': 'This is a test description.',
    'sourceRefName': 'refs/heads/feature',
    'targetRefName': 'refs/heads/main',
    'createdBy': {'uniqueName': 'user@example.com'},
    'status': 'active',
    'isDraft': False,
    'autoCompleteSetBy': None,
    'reviewers': [
        {'uniqueName': 'reviewer1', 'vote': 10, 'isRequired': True},
        {'uniqueName': 'reviewer2', 'vote': 0, 'isRequired': True},
        {'uniqueName': 'reviewer3', 'vote': -5, 'isRequired': False},
    ]
}

content = _format_manage_content(pr)
print(content)
print()

# Verify expected content
assert 'id: 42' in content
assert 'source: feature' in content
assert 'target: main' in content
assert 'created: user@example.com' in content
assert '# My test PR' in content
assert 'This is a test description.' in content
assert '# Reviewers' in content
assert 'reviewer1' in content
assert '**approved**' in content
assert 'reviewer2' in content
assert '**no vote**' in content
assert 'reviewer3' in content
assert '**wait for author**' in content
assert '(required)' in content
assert '# Threads' in content
assert '# Changes' in content
print('PASS: _format_manage_content produces correct output')
"

echo ""
echo "=== Test 2: _format_manage_content with draft PR ==="
python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from gg.cmd_pr import _format_manage_content

pr = {
    'pullRequestId': 99,
    'title': 'Draft PR',
    'description': '',
    'sourceRefName': 'refs/heads/wip',
    'targetRefName': 'refs/heads/main',
    'createdBy': {'uniqueName': 'dev@example.com'},
    'status': 'active',
    'isDraft': True,
    'autoCompleteSetBy': None,
    'reviewers': [],
}

content = _format_manage_content(pr)
assert 'draft' in content  # status field shows draft
assert '# Draft PR' in content
print(content)
print()
print('PASS: draft PR format correct')
"

echo ""
echo "=== Test 3: _get_manage_lua produces valid Lua syntax ==="
python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from gg.cmd_pr import _get_manage_lua

lua = _get_manage_lua(42, '/tmp/manage.md', '/tmp/cache')
assert 'pr_id = 42' in lua
assert 'manage_path' in lua
assert 'cache_dir' in lua
assert 'sync_view' in lua
assert 'cc' in lua
assert \"vim.api.nvim_buf_set_keymap(0, 'n', 'A'\" in lua
assert 'pp' in lua
assert \"'o'\" in lua
assert 'ApprovedHL' in lua
assert 'WaitForAuthorHL' in lua
assert 'NoVoteHL' in lua
assert 'BufEnter' in lua
assert '_manage' in lua
assert '_manage-reload' in lua
assert 'open_action_menu' in lua
assert 'open_summary' in lua
assert 'ACTIONS' in lua
assert 'Status: complete' in lua
assert 'Vote: approve' in lua
assert 'Vote: abstain' in lua
assert '_set-status' in lua
assert '_set-vote' in lua
assert 'load_changes' in lua
assert 'jobstart' in lua
assert '_manage-changes' in lua
assert '_manage-diff-open' in lua
assert 'open_changes_diff' in lua
assert 'apply_diff_annotations' in lua
assert 'open_current_item' in lua
assert 'open_thread_by_id' in lua
assert 'open_thread_at_cursor' in lua
assert 'set_current_thread_status' in lua
assert 'load_threads(false)' in lua
assert 'create_new_thread' in lua
assert 'add_current_item' in lua
assert '_manage-thread-new' in lua
assert '_manage-thread-status' in lua
assert 'jump_thread' in lua
assert \"vim.keymap.set('n', ']]'\" in lua
assert \"vim.keymap.set('n', '[[\" in lua
assert \"vim.keymap.set('n', 'o', open_thread_at_cursor\" in lua
assert \"vim.keymap.set('n', 'a', add_thread_at_cursor\" in lua
assert \"callback = add_current_item\" in lua
assert \"callback = open_current_item\" in lua
assert \"vim.api.nvim_buf_set_keymap(0, 'n', 'ca'\" in lua
assert \"set_current_thread_status('active')\" in lua
assert \"vim.api.nvim_buf_set_keymap(0, 'n', 'cf'\" in lua
assert \"set_current_thread_status('fixed')\" in lua
assert \"vim.api.nvim_buf_set_keymap(0, 'n', 'cw'\" in lua
assert \"set_current_thread_status('wontFix')\" in lua
assert \"set_current_thread_status('closed')\" in lua
assert 'load_threads' in lua
assert '_manage-threads' in lua
assert '_manage-thread-open' in lua
assert 'open_current_thread' in lua
assert 'pending_thread_ids' in lua
assert 'pending_thread_status_ids' in lua
assert 'pending_thread_statuses' in lua
assert 'data.reviewer_lines' in lua
assert 'reviewers_lnum - 1, threads_lnum - 1' in lua
assert 'title_lnum, reviewers_lnum, _, threads_lnum = find_section_boundaries()' in lua
assert 'table.insert(markers, \'modified\')' in lua
assert 'table.insert(markers, pending_status)' in lua
assert 'pending_new_threads' in lua
assert 'thread_responses_changed' in lua
assert 'thread_statuses_changed' in lua
assert 'new_threads_changed' in lua
assert 'normalize_threads_data' in lua
assert 'data = normalize_threads_data(data)' in lua
assert 'load_policies' in lua
assert 'local load_policies' in lua
assert 'load_policies = function(force)' in lua
assert 'value == vim.NIL' in lua
assert 'json_table(policy.configuration)' in lua
assert 'policy_is_expired' in lua
assert 'vim.split(err_text' in lua
assert '_manage-policies' in lua
assert '_manage-policy-queue' in lua
assert '_manage-policy-cancel' in lua
assert \"'aq'\" not in lua
assert 'queue_current_policy' in lua
assert 'cancel_current_policy' in lua
assert 'cancel_current_item' in lua
assert 'current_policy_id' in lua
assert 'normalize_thread_file_path' in lua
assert 'refresh_changes_from_cache' in lua
assert 'ChangesModifiedHL' in lua
assert 'ChangesAddedHL' in lua
assert 'ChangesDeletedHL' in lua
assert 'PolicyQueuedHL' in lua
assert 'PolicyRunningHL' in lua
assert 'PolicyRejectedHL' in lua
assert 'PolicyExpiredHL' in lua
assert 'PolicyNotApplicableHL' in lua
assert 'apply_manage_modified' in lua
assert 'manage_has_pending_changes = data.changed or data.status_changed' in lua
assert 'reload_current_section' in lua
assert 'reload_everything' in lua
assert \"jobstart({'gg', 'pr', '_manage-reload'\" in lua
assert \"jobstart({'gg', 'pr', '_manage-policy-queue'\" in lua
assert \"jobstart({'gg', 'pr', '_manage-policy-cancel'\" in lua
assert \"if section == 'policies' then\\n    queue_current_policy()\" in lua
assert \"if current_section() == 'policies' then\\n    cancel_current_policy()\" in lua
assert \"callback = cancel_current_item\" in lua
assert \"elseif section == 'policies' then\\n    load_policies(true)\" in lua
assert \"elseif section == 'threads' then\\n    load_threads(true)\" in lua
assert \"if section == 'changes' then\\n    load_changes(true)\" in lua
assert 'load_changes(true)' in lua
assert 'load_threads(true)' in lua
assert 'load_policies(true)' in lua
assert 'jobstop' in lua
# Verify no unresolved format placeholders
assert '{pr_id}' not in lua
assert '{manage_path}' not in lua
assert '{cache_dir}' not in lua
# Count braces to roughly check balance
opening = lua.count('{')
closing = lua.count('}')
print(f'Braces: {{={opening}  }}={closing}')
print('PASS: Lua code generated correctly')
"

echo ""
echo "=== Test 4: _fetch-summary creates summary.md ==="
CACHE_DIR="$TEST_DIR/cache"
mkdir -p "$CACHE_DIR"
# Create fake pr.json
python3 -c "
import json
pr = {'pullRequestId': 1, 'title': 'Original Title', 'description': 'Original desc.'}
with open('$CACHE_DIR/pr.json', 'w') as f:
    json.dump(pr, f)
"
# Test with mock cache
python3 -c "
import json, os, sys
sys.path.insert(0, '$SCRIPT_DIR')
from unittest.mock import patch
from gg.cmd_pr import cmd_pr_fetch_summary

class Args:
    pr_id = 1

with patch('gg.cmd_pr._get_cache_dir', return_value='$CACHE_DIR'):
    result = cmd_pr_fetch_summary(Args())
    assert result == 0

summary_path = os.path.join('$CACHE_DIR', 'summary.md')
assert os.path.isfile(summary_path), 'summary.md should exist'
with open(summary_path) as f:
    content = f.read()
assert 'Original Title' in content
assert 'Original desc.' in content

print('PASS: _fetch-summary creates summary.md')
"

echo ""
echo "=== Test 5: _fetch-summary does not overwrite existing summary.md ==="
python3 -c "
import json, os, sys
sys.path.insert(0, '$SCRIPT_DIR')
from unittest.mock import patch
from gg.cmd_pr import cmd_pr_fetch_summary

class Args:
    pr_id = 1

# Modify summary.md
with open(os.path.join('$CACHE_DIR', 'summary.md'), 'w') as f:
    f.write('Modified Line\n')

with patch('gg.cmd_pr._get_cache_dir', return_value='$CACHE_DIR'):
    result = cmd_pr_fetch_summary(Args())
    assert result == 0

with open(os.path.join('$CACHE_DIR', 'summary.md')) as f:
    content = f.read()
assert content == 'Modified Line\n', 'summary.md should NOT be overwritten'
print('PASS: _fetch-summary does not overwrite existing summary.md')
"

echo ""
echo "=== Test 6: _publish detects no changes ==="
python3 -c "
import json, os, sys
sys.path.insert(0, '$SCRIPT_DIR')
from unittest.mock import patch
from gg.cmd_pr import cmd_pr_publish_data

class Args:
    pr_id = 1

# summary.md has same content as original
with open(os.path.join('$CACHE_DIR', 'summary.md'), 'w') as f:
    f.write('Original Title\nOriginal desc.\n')

import io
sys.stdout = io.StringIO()
with patch('gg.cmd_pr._get_cache_dir', return_value='$CACHE_DIR'):
    result = cmd_pr_publish_data(Args())
output = sys.stdout.getvalue()
sys.stdout = sys.__stdout__

data = json.loads(output)
assert data['status'] == 'no_changes', f'Expected no_changes, got {data}'
print('PASS: _publish detects no changes')
"

echo ""
echo "=== Test 7: _set-status writes status.txt ==="
python3 -c "
import json, os, sys
sys.path.insert(0, '$SCRIPT_DIR')
from unittest.mock import patch
from gg.cmd_pr import cmd_pr_set_status, cmd_pr_set_vote

class Args:
    pr_id = 1
    status = 'draft'

CACHE_DIR2='/tmp/test_pr_manage_status'
os.makedirs(CACHE_DIR2, exist_ok=True)

with patch('gg.cmd_pr._get_cache_dir', return_value=CACHE_DIR2):
    import io
    sys.stdout = io.StringIO()
    r = cmd_pr_set_status(Args())
    out = sys.stdout.getvalue()
    sys.stdout = sys.__stdout__
    data = json.loads(out)
    assert data['status'] == 'ok'
    assert data['new_status'] == 'draft'

status_path = os.path.join(CACHE_DIR2, 'status.txt')
assert os.path.isfile(status_path)
with open(status_path) as f:
    assert f.read().strip() == 'draft'
class VoteArgs:
    pr_id = 1
    vote = 'approve'
with patch('gg.cmd_pr._get_cache_dir', return_value=CACHE_DIR2):
    import io
    sys.stdout = io.StringIO()
    r = cmd_pr_set_vote(VoteArgs())
    out = sys.stdout.getvalue()
    sys.stdout = sys.__stdout__
    data = json.loads(out)
    assert data['status'] == 'ok'
    assert data['new_vote'] == 'approve'
vote_path = os.path.join(CACHE_DIR2, 'vote.txt')
assert os.path.isfile(vote_path)
with open(vote_path) as f:
    assert f.read().strip() == 'approve'
print('PASS: _set-status writes status.txt')
"

echo ""
echo "=== Test 8: _manage sync returns status info ==="
python3 -c "
import json, os, sys
sys.path.insert(0, '$SCRIPT_DIR')
from unittest.mock import patch
from gg.cmd_pr import cmd_pr_manage_sync

class Args:
    pr_id = 1

CACHE_DIR3='/tmp/test_pr_manage_sync2'
# Clean up any leftovers
if os.path.isdir(CACHE_DIR3):
    import shutil
    shutil.rmtree(CACHE_DIR3)
os.makedirs(CACHE_DIR3, exist_ok=True)

# Create pr.json with active status
with open(os.path.join(CACHE_DIR3, 'pr.json'), 'w') as f:
    json.dump({
        'pullRequestId': 1,
        'title': 'T',
        'description': 'D',
        'status': 'active',
        'isDraft': False,
        'autoCompleteSetBy': None,
        'reviewers': [{'uniqueName': 'reviewer@example.com', 'vote': 0}],
    }, f)

with patch('gg.cmd_pr._get_cache_dir', return_value=CACHE_DIR3):
    import io
    sys.stdout = io.StringIO()
    r = cmd_pr_manage_sync(Args())
    out = sys.stdout.getvalue()
    sys.stdout = sys.__stdout__
    data = json.loads(out)
    print(f'First call result: {data}')
    assert data['pr_status'] == 'active', f'Expected active, got {data[\"pr_status\"]}'
    assert data['original_status'] == 'active'
    assert data['status_changed'] == False
    assert data['vote_changed'] == False
    assert data['reviewer_lines'] == ['# Reviewers', '', '- reviewer@example.com - **no vote**', '']

# Now create status.txt
with open(os.path.join(CACHE_DIR3, 'status.txt'), 'w') as f:
    f.write('auto-complete')
with open(os.path.join(CACHE_DIR3, 'vote.txt'), 'w') as f:
    f.write('reject')

with patch('gg.cmd_pr._get_cache_dir', return_value=CACHE_DIR3):
    import io
    sys.stdout = io.StringIO()
    r = cmd_pr_manage_sync(Args())
    out = sys.stdout.getvalue()
    sys.stdout = sys.__stdout__
    data = json.loads(out)
    print(f'Second call result: {data}')
    assert data['pr_status'] == 'auto-complete', f'Expected auto-complete, got {data[\"pr_status\"]}'
    assert data['original_status'] == 'active'
    assert data['status_changed'] == True
    assert data['vote_changed'] == True
    assert data['pending_vote'] == 'reject'
    assert data['pending_vote_label'] == 'reject'

print('PASS: _manage sync returns correct status info')
"

echo ""
echo "=== Test 9: _publish applies pending reviewer vote ==="
python3 -c "
import json, os, shutil, sys
sys.path.insert(0, '$SCRIPT_DIR')
from unittest.mock import patch
from gg.cmd_pr import cmd_pr_publish_data

class Args:
    pr_id = 88

class Result:
    returncode = 0
    stderr = ''
    stdout = '{}'

CACHE_DIR_VOTE='$TEST_DIR/vote_cache'
if os.path.isdir(CACHE_DIR_VOTE):
    shutil.rmtree(CACHE_DIR_VOTE)
os.makedirs(CACHE_DIR_VOTE)
with open(os.path.join(CACHE_DIR_VOTE, 'pr.json'), 'w') as f:
    json.dump({
        'pullRequestId': 88,
        'title': 'Vote PR',
        'description': '',
        'status': 'active',
        'isDraft': False,
        'autoCompleteSetBy': None,
        'url': 'https://dev.azure.com/org/proj/_apis/git/repositories/repo/pullRequests/88',
        'reviewers': [{'id': 'user-guid', 'uniqueName': 'me@example.com', 'vote': 0}],
    }, f)
with open(os.path.join(CACHE_DIR_VOTE, 'vote.txt'), 'w') as f:
    f.write('approve')

posted_bodies = []
def fake_run_az(cmd, *args, **kwargs):
    import re
    m = re.search(r'--body @([^ ]+)', cmd)
    if m:
        with open(m.group(1)) as body_file:
            posted_bodies.append(json.load(body_file))
    return Result()

import io
sys.stdout = io.StringIO()
with patch('gg.cmd_pr._get_cache_dir', return_value=CACHE_DIR_VOTE), \
     patch('gg.cmd_pr._get_current_user_email', return_value='me@example.com'), \
     patch('gg.cmd_pr._run_az', side_effect=fake_run_az) as run_az:
    r = cmd_pr_publish_data(Args())
out = sys.stdout.getvalue()
sys.stdout = sys.__stdout__
data = json.loads(out)
assert r == 0
assert data['status'] == 'ok'
assert data['updated_vote'] == 'approve'
assert not os.path.exists(os.path.join(CACHE_DIR_VOTE, 'vote.txt'))
cmds = [call.args[0] for call in run_az.call_args_list]
assert any('/reviewers/user-guid?api-version=7.1' in cmd and '--method PUT' in cmd for cmd in cmds), cmds
assert {'vote': 10} in posted_bodies
with open(os.path.join(CACHE_DIR_VOTE, 'pr.json')) as f:
    cached_pr = json.load(f)
assert cached_pr['reviewers'][0]['uniqueName'] == 'me@example.com'
assert cached_pr['reviewers'][0]['vote'] == 10
print('PASS: _publish applies pending reviewer vote')
"

echo ""
echo "=== Test 10: _manage-reload refreshes PR details and drops pending edits ==="
python3 -c "
import json, os, shutil, sys
sys.path.insert(0, '$SCRIPT_DIR')
from unittest.mock import patch
from gg.cmd_pr import cmd_pr_manage_reload

class Args:
    pr_id = 77

class Result:
    returncode = 0
    stderr = ''
    stdout = json.dumps({
        'pullRequestId': 77,
        'title': 'Reloaded title',
        'description': 'Reloaded description',
        'status': 'active',
        'isDraft': False,
        'autoCompleteSetBy': None,
    })

CACHE_DIR4='$TEST_DIR/reload_cache'
if os.path.isdir(CACHE_DIR4):
    shutil.rmtree(CACHE_DIR4)
os.makedirs(CACHE_DIR4)
with open(os.path.join(CACHE_DIR4, 'pr.json'), 'w') as f:
    json.dump({'pullRequestId': 77, 'title': 'Old title'}, f)
with open(os.path.join(CACHE_DIR4, 'summary.md'), 'w') as f:
    f.write('Pending title\\nPending description\\n')
with open(os.path.join(CACHE_DIR4, 'status.txt'), 'w') as f:
    f.write('draft')
with open(os.path.join(CACHE_DIR4, 'vote.txt'), 'w') as f:
    f.write('reject')

import io
sys.stdout = io.StringIO()
with patch('gg.cmd_pr._get_cache_dir', return_value=CACHE_DIR4), patch('gg.cmd_pr._run_az', return_value=Result()):
    result = cmd_pr_manage_reload(Args())
out = sys.stdout.getvalue()
sys.stdout = sys.__stdout__

data = json.loads(out)
assert result == 0
assert data['status'] == 'ok'
assert not os.path.exists(os.path.join(CACHE_DIR4, 'summary.md'))
assert not os.path.exists(os.path.join(CACHE_DIR4, 'status.txt'))
assert not os.path.exists(os.path.join(CACHE_DIR4, 'vote.txt'))
with open(os.path.join(CACHE_DIR4, 'pr.json')) as f:
    pr = json.load(f)
assert pr['title'] == 'Reloaded title'
print('PASS: _manage-reload refreshes PR details and drops pending edits')
"

echo ""
echo ""
echo "=== Test 10: _manage-threads fetches, filters, formats, and caches threads ==="
THREAD_CACHE_DIR="$TEST_DIR/thread_cache"
mkdir -p "$THREAD_CACHE_DIR"
python3 -c "
import json, os, sys
sys.path.insert(0, '$SCRIPT_DIR')
from unittest.mock import patch
from gg.cmd_pr import cmd_pr_manage_threads, _format_manage_content

class Args:
    pr_id = 200

class Result:
    returncode = 0
    stderr = ''
    stdout = json.dumps({
        'value': [
            {
                'id': 11,
                'status': 'active',
                'threadContext': {'filePath': '/src/a.py', 'rightFileStart': {'line': 7}},
                'comments': [
                    {
                        'commentType': 'text',
                        'content': '[comment]: metadata\\nPlease fix &amp; trim this\\nsecond line',
                        'publishedDate': '2026-06-26T12:23:45.000Z',
                        'author': {'uniqueName': 'reviewer@example.com'},
                    },
                ],
            },
            {
                'id': 12,
                'status': 'active',
                'comments': [
                    {'commentType': 'system', 'content': 'Vote changed', 'author': {'uniqueName': 'system'}},
                ],
            },
            {
                'id': 13,
                'status': 'closed',
                'comments': [
                    {'commentType': 'system', 'content': 'Status changed', 'author': {'uniqueName': 'system'}},
                    {
                        'commentType': 'text',
                        'content': 'Resolved but still visible',
                        'publishedDate': '2026-06-27T15:04:00Z',
                        'author': {'uniqueName': 'author@example.com'},
                    },
                ],
            },
            {
                'id': 14,
                'status': 'active',
                'threadContext': {'filePath': '/src/b.py', 'rightFileStart': {'line': 42}},
                'comments': [
                    {
                        'commentType': 'system',
                        'content': '<b>PR Assistant AI Code Review</b> Reliability: Correctness Severity Low It might be better to keep this guard.',
                        'publishedDate': '2026-06-28T10:11:12Z',
                        'author': {'uniqueName': ''},
                    },
                ],
            },
            {
                'id': 15,
                'status': 'fixed',
                'comments': [
                    {'commentType': 'system', 'content': 'Fixed system noise', 'author': {'uniqueName': 'system'}},
                ],
            },
        ],
    })

pr = {
    'pullRequestId': 200,
    'url': 'https://dev.azure.com/org/project/_apis/git/repositories/repo/pullRequests/200',
    'title': 'Thread PR',
    'description': '',
    'sourceRefName': 'refs/heads/feature',
    'targetRefName': 'refs/heads/main',
    'createdBy': {'uniqueName': 'test@test.com'},
    'status': 'active',
    'isDraft': False,
    'autoCompleteSetBy': None,
    'reviewers': [],
}
with open(os.path.join('$THREAD_CACHE_DIR', 'pr.json'), 'w') as f:
    json.dump(pr, f)

import io
sys.stdout = io.StringIO()
with patch('gg.cmd_pr._get_cache_dir', return_value='$THREAD_CACHE_DIR'), patch('gg.cmd_pr._run_az', return_value=Result()):
    r = cmd_pr_manage_threads(Args())
out = sys.stdout.getvalue()
sys.stdout = sys.__stdout__

data = json.loads(out)
print(f'manage-threads result: {data}')
assert r == 0
assert data['status'] == 'ok'
assert data['total_threads'] == 4
assert [t['id'] for t in data['threads']] == [11, 12, 13, 14]
assert data['threads'][0]['file_path'] == '/src/a.py'
assert data['threads'][0]['location'] == '/src/a.py:7'
assert data['threads'][0]['date'] == '2026-06-26 12:23'
assert data['threads'][0]['preview'] == 'Please fix & trim this second line'
assert data['threads'][1]['preview'] == 'Vote changed'
assert data['threads'][2]['status'] == 'closed'
assert data['threads'][3]['author'] == 'system'
assert data['threads'][3]['preview'].startswith('PR Assistant AI Code Review Reliability: Correctness Severity Low It might be better')

threads_path = os.path.join('$THREAD_CACHE_DIR', 'threads.json')
assert os.path.isfile(threads_path), 'threads.json should exist'
with open(threads_path) as f:
    cached_threads = json.load(f)
assert 'value' in cached_threads, 'threads.json should store raw az thread response'
assert cached_threads['value'][0]['id'] == 11
assert 'threads' not in cached_threads
content = _format_manage_content(pr, '$THREAD_CACHE_DIR')
assert '- [11] (**active**) by reviewer@example.com /src/a.py:7 2026-06-26 12:23' in content, content
assert 'Please fix & trim this second line' in content
assert '- [13] (**closed**) by author@example.com 2026-06-27 15:04' in content, content
assert '- [14] (**active**) by system /src/b.py:42 2026-06-28 10:11' in content, content
assert 'It might be better to keep this g...' in content
assert '- [12] (**active**) by system' in content
assert '[15]' not in content
print('PASS: _manage-threads filters and formats threads')
"

echo ""
echo "=== Test 11: managed thread drafts open, mark modified, and publish ==="
python3 -c "
import json, os, sys
sys.path.insert(0, '$SCRIPT_DIR')
from unittest.mock import patch
from gg.cmd_pr import cmd_pr_manage_thread_open, cmd_pr_manage_thread_new, cmd_pr_manage_thread_status, cmd_pr_manage_sync, cmd_pr_publish_data

diff_for_a = '''diff --git a/src/a.py b/src/a.py
new file mode 100644
index 0000000..1111111
--- /dev/null
+++ b/src/a.py
@@ -0,0 +1,10 @@
+one
+two
+three
'''

class OpenArgs:
    pr_id = 200
    thread_id = 11

class StatusArgs:
    pr_id = 200
    thread_id = 11
    status = 'fixed'

class NewArgs:
    pr_id = 200
    file_path = None
    side = None
    line = None

class NewLocatedArgs:
    pr_id = 200
    file_path = '/src/a.py'
    side = 'right'
    line = 2

import io
sys.stdout = io.StringIO()
with patch('gg.cmd_pr._get_cache_dir', return_value='$THREAD_CACHE_DIR'):
    r = cmd_pr_manage_thread_open(OpenArgs())
out = sys.stdout.getvalue()
sys.stdout = sys.__stdout__
data = json.loads(out)
assert r == 0
assert data['status'] == 'ok'
thread_path = data['path']
assert os.path.isfile(thread_path)
with open(thread_path) as f:
    thread_content = f.read()
assert '<!-- gg-response-start -->' in thread_content
assert 'Please fix &amp; trim this' in thread_content
assert 'diff --git a/src/a.py b/src/a.py' not in thread_content

sys.stdout = io.StringIO()
with patch('gg.cmd_pr._get_cache_dir', return_value='$THREAD_CACHE_DIR'), patch('gg.cmd_pr._get_manage_diff_for_thread', return_value=diff_for_a):
    r = cmd_pr_manage_thread_open(OpenArgs())
out = sys.stdout.getvalue()
sys.stdout = sys.__stdout__
data = json.loads(out)
assert r == 0
assert data['status'] == 'ok'
assert data['path'] == thread_path
with open(thread_path) as f:
    thread_content = f.read()
assert 'diff --git a/src/a.py b/src/a.py' in thread_content

with open(thread_path, 'w') as f:
    f.write(thread_content.replace('Write your response here.', 'Thanks, fixed.'))

sys.stdout = io.StringIO()
with patch('gg.cmd_pr._get_cache_dir', return_value='$THREAD_CACHE_DIR'):
    r = cmd_pr_manage_thread_status(StatusArgs())
out = sys.stdout.getvalue()
sys.stdout = sys.__stdout__
status_data = json.loads(out)
assert r == 0
assert status_data['status'] == 'ok'
with open(thread_path) as f:
    updated_thread_content = f.read()
assert 'status: fixed' in updated_thread_content
assert 'Thanks, fixed.' in updated_thread_content

sys.stdout = io.StringIO()
with patch('gg.cmd_pr._get_cache_dir', return_value='$THREAD_CACHE_DIR'):
    r = cmd_pr_manage_thread_new(NewArgs())
out = sys.stdout.getvalue()
sys.stdout = sys.__stdout__
new_data = json.loads(out)
assert r == 0
assert new_data['status'] == 'ok'
new_thread_path = new_data['path']
assert new_data['draft_id'].startswith('new-')
with open(new_thread_path) as f:
    new_thread_content = f.read()
assert '<!-- gg-new-thread-comment-start -->' in new_thread_content
assert 'Location: general PR thread' in new_thread_content
with open(new_thread_path, 'w') as f:
    f.write(new_thread_content.replace('Write your comment here.', 'Please consider this.'))

sys.stdout = io.StringIO()
with patch('gg.cmd_pr._get_cache_dir', return_value='$THREAD_CACHE_DIR'):
    r = cmd_pr_manage_thread_new(NewLocatedArgs())
out = sys.stdout.getvalue()
sys.stdout = sys.__stdout__
located_new_data = json.loads(out)
assert r == 0
located_new_thread_path = located_new_data['path']
with open(located_new_thread_path) as f:
    located_new_thread_content = f.read()
assert 'Location: /src/a.py:2 (right)' in located_new_thread_content
with open(located_new_thread_path, 'w') as f:
    f.write(located_new_thread_content.replace('Write your comment here.', 'Please check this line.'))

class SyncArgs:
    pr_id = 200

sys.stdout = io.StringIO()
with patch('gg.cmd_pr._get_cache_dir', return_value='$THREAD_CACHE_DIR'):
    r = cmd_pr_manage_sync(SyncArgs())
out = sys.stdout.getvalue()
sys.stdout = sys.__stdout__
sync_data = json.loads(out)
assert r == 0
assert sync_data['thread_responses_changed'] == True
assert sync_data['thread_statuses_changed'] == True
assert sync_data['pending_thread_ids'] == ['11']
assert sync_data['pending_thread_status_ids'] == ['11']
assert sync_data['pending_thread_statuses'] == {'11': 'fixed'}
assert sync_data['new_threads_changed'] == True
assert {t['id'] for t in sync_data['pending_new_threads']} == {new_data['draft_id'], located_new_data['draft_id']}
assert all(t['has_comment'] for t in sync_data['pending_new_threads'])

class PublishArgs:
    pr_id = 200

class Result:
    returncode = 0
    stderr = ''
    stdout = json.dumps({'status': 'ok'})

posted_bodies = []
def fake_run_az(cmd, *args, **kwargs):
    import re
    m = re.search(r'--body @([^ ]+)', cmd)
    if m:
        with open(m.group(1)) as body_file:
            posted_bodies.append(json.load(body_file))
    return Result()

sys.stdout = io.StringIO()
with patch('gg.cmd_pr._get_cache_dir', return_value='$THREAD_CACHE_DIR'), patch('gg.cmd_pr._run_az', side_effect=fake_run_az) as run_az:
    r = cmd_pr_publish_data(PublishArgs())
out = sys.stdout.getvalue()
sys.stdout = sys.__stdout__
publish_data = json.loads(out)
assert r == 0
assert publish_data['status'] == 'ok'
assert publish_data['posted_threads'] == ['11']
assert publish_data['updated_thread_statuses'] == ['11']
assert set(publish_data['posted_new_threads']) == {new_data['draft_id'], located_new_data['draft_id']}
cmds = [call.args[0] for call in run_az.call_args_list]
assert any('/threads/11/comments?api-version=7.1' in cmd for cmd in cmds)
assert any('/threads/11?api-version=7.1' in cmd and '--method PATCH' in cmd for cmd in cmds)
assert any('/threads?api-version=7.1' in cmd for cmd in cmds)
assert any('az rest --method POST' in cmd for cmd in cmds)
assert any(body == {'status': 'fixed'} for body in posted_bodies)
assert any(body.get('comments', [{}])[0].get('content') == 'Please consider this.' and 'threadContext' not in body for body in posted_bodies)
assert any(
    body.get('comments', [{}])[0].get('content') == 'Please check this line.'
    and body.get('threadContext', {}).get('filePath') == '/src/a.py'
    and body.get('threadContext', {}).get('rightFileStart', {}).get('line') == 2
    for body in posted_bodies
)
assert not os.path.exists(thread_path)
assert not os.path.exists(new_thread_path)
assert not os.path.exists(located_new_thread_path)
assert not os.path.exists(os.path.join('$THREAD_CACHE_DIR', 'threads.json'))
print('PASS: managed thread drafts open, mark modified, and publish')
"

echo ""
echo "=== Test 12: _manage-policies fetches, filters, formats, and caches policies ==="
POLICY_CACHE_DIR="$TEST_DIR/policy_cache"
mkdir -p "$POLICY_CACHE_DIR"
python3 -c "
import json, os, sys
sys.path.insert(0, '$SCRIPT_DIR')
from unittest.mock import patch
from gg.cmd_pr import cmd_pr_manage_policies, _format_manage_content

class Args:
    pr_id = 300

class Result:
    returncode = 0
    stderr = ''
    stdout = json.dumps([
        {
            'evaluationId': 'eval-build',
            'status': 'approved',
            'configuration': {
                'id': 1,
                'isBlocking': True,
                'settings': {'displayName': 'Required Build'},
            },
        },
        {
            'evaluationId': 'eval-tests',
            'status': 'rejected',
            'configuration': {
                'id': 2,
                'isBlocking': True,
                'settings': {'statusName': 'Required Tests'},
            },
            'context': {
                'isExpired': True,
                'buildOutputPreview': {
                    'errors': [{'message': 'Unit tests failed\\nFirst failing test'}],
                },
            },
        },
        {
            'evaluationId': 'eval-optional',
            'status': 'running',
            'configuration': {
                'id': 3,
                'isBlocking': False,
                'settings': {'displayName': 'Optional Build'},
            },
        },
    ])

pr = {
    'pullRequestId': 300,
    'title': 'Policy PR',
    'description': '',
    'sourceRefName': 'refs/heads/feature',
    'targetRefName': 'refs/heads/main',
    'createdBy': {'uniqueName': 'test@test.com'},
    'status': 'active',
    'isDraft': False,
    'autoCompleteSetBy': None,
    'reviewers': [],
}

import io
sys.stdout = io.StringIO()
with patch('gg.cmd_pr._get_cache_dir', return_value='$POLICY_CACHE_DIR'), patch('gg.cmd_pr._run_az', return_value=Result()):
    r = cmd_pr_manage_policies(Args())
out = sys.stdout.getvalue()
sys.stdout = sys.__stdout__

data = json.loads(out)
print(f'manage-policies result: {data}')
assert r == 0
assert data['status'] == 'ok'
assert data['total_policies'] == 2
assert [p['id'] for p in data['policies']] == [1, 2]
assert data['policies'][0]['name'] == 'Required Build'
assert data['policies'][1]['name'] == 'Required Tests'
assert data['policies'][1]['errors'] == ['Unit tests failed\\nFirst failing test']

policies_path = os.path.join('$POLICY_CACHE_DIR', 'policies.json')
assert os.path.isfile(policies_path), 'policies.json should exist'
with open(policies_path) as f:
    cached_policies = json.load(f)
assert isinstance(cached_policies, list), 'policies.json should store raw az policy list'
assert cached_policies[0]['evaluationId'] == 'eval-build'
assert cached_policies[0]['configuration']['id'] == 1
content = _format_manage_content(pr, '$POLICY_CACHE_DIR')
assert '# Policies' in content
assert '- [1] Required Build - **approved**' in content, content
assert '- [2] Required Tests - **expired**' in content, content
assert 'Unit tests failed' in content
assert '  Unit tests failed\\n  First failing test' in content
assert 'Optional Build' not in content
print('PASS: _manage-policies filters and formats policies')
"

echo ""
echo "=== Test 13: _manage-policy-queue queues evaluation ==="
python3 -c "
import json, sys
sys.path.insert(0, '$SCRIPT_DIR')
from unittest.mock import patch
from gg.cmd_pr import cmd_pr_manage_policy_cancel, cmd_pr_manage_policy_queue

class Args:
    pr_id = 300
    policy_id = 2

class Result:
    returncode = 0
    stderr = ''
    stdout = json.dumps({'evaluationId': 'eval-tests', 'status': 'queued'})

import io
import os
with open(os.path.join('$POLICY_CACHE_DIR', 'policies.json'), 'w') as f:
    json.dump([
            {
                'evaluationId': 'eval-build',
                'status': 'approved',
                'configuration': {
                    'id': 1,
                    'isBlocking': True,
                    'settings': {'displayName': 'Required Build'},
                },
            },
            {
                'evaluationId': 'eval-tests',
                'status': 'rejected',
                'context': {'buildId': 12345},
                'configuration': {
                    'id': 2,
                    'isBlocking': True,
                    'settings': {'displayName': 'Required Tests'},
                },
            },
        ],
        f)
sys.stdout = io.StringIO()
with patch('gg.cmd_pr._get_cache_dir', return_value='$POLICY_CACHE_DIR'), patch('gg.cmd_pr._run_az', return_value=Result()) as run_az:
    r = cmd_pr_manage_policy_queue(Args())
out = sys.stdout.getvalue()
sys.stdout = sys.__stdout__

data = json.loads(out)
assert r == 0
assert data['status'] == 'ok'
cmd = run_az.call_args.args[0]
assert 'az repos pr policy queue' in cmd
assert '--id 300' in cmd
assert '--evaluation-id eval-tests' in cmd

sys.stdout = io.StringIO()
with patch('gg.cmd_pr._get_cache_dir', return_value='$POLICY_CACHE_DIR'), patch('gg.cmd_pr._run_az', return_value=Result()) as run_az:
    r = cmd_pr_manage_policy_cancel(Args())
out = sys.stdout.getvalue()
sys.stdout = sys.__stdout__

data = json.loads(out)
assert r == 0
assert data['status'] == 'ok'
assert data['build_id'] == 12345
cmd = run_az.call_args.args[0]
assert 'az pipelines build cancel' in cmd
assert '--build-id 12345' in cmd
print('PASS: _manage-policy-queue/cancel maps policy id to evaluation/build id')
"

echo ""
echo "=== Test 14: _manage-changes computes and caches diff stats ==="
# Set up a git repo with actual remote tracking refs
REMOTE_DIR="$TEST_DIR/remote.git"
git init --bare "$REMOTE_DIR"
GIT_DIR="$TEST_DIR/test_repo"
git clone "$REMOTE_DIR" "$GIT_DIR"
cd "$GIT_DIR"
git config user.email "test@test.com"
git config user.name "Test"
echo "initial" > file.txt && git add . && git commit -m "initial"
git push origin main
git checkout -b feature
echo "change" > file.txt && echo "new" > new.txt && git add . && git commit -m "feature work"
git push origin feature
git checkout main

# Create pr.json pointing to these branches
python3 -c "
import json
pr = {
    'pullRequestId': 100,
    'title': 'Test PR',
    'description': 'Test',
    'sourceRefName': 'refs/heads/feature',
    'targetRefName': 'refs/heads/main',
    'createdBy': {'uniqueName': 'test@test.com'},
    'status': 'active',
    'isDraft': False,
    'autoCompleteSetBy': None,
    'reviewers': [],
    'url': 'https://dev.azure.com/org/project/_apis/git/repositories/repo-guid/pullRequests/100',
    'repository': {'id': 'repo-guid'},
}
cache_dir = '$TEST_DIR/cache2'
import os
os.makedirs(cache_dir, exist_ok=True)
with open(os.path.join(cache_dir, 'pr.json'), 'w') as f:
    json.dump(pr, f)

# Run _manage-changes via Python directly
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from unittest.mock import patch
from gg.cmd_pr import cmd_pr_manage_changes, _get_cache_dir

class Args:
    pr_id = 100

class AzResult:
    returncode = 0
    stdout = '{}'
    stderr = ''

az_commands = []
az_bodies = []
def fake_run_az(cmd, *args, **kwargs):
    import re
    az_commands.append(cmd)
    m = re.search(r'--body @([^ ]+)', cmd)
    if m:
        with open(m.group(1)) as body_file:
            az_bodies.append(json.load(body_file))
    return AzResult()

# Mock _get_cache_dir to use our test cache
original_get_cache_dir = _get_cache_dir
with patch('gg.cmd_pr._get_cache_dir', return_value=cache_dir), patch('gg.cmd_pr._run_az', side_effect=fake_run_az):

    # Temporarily change to the git repo dir so git diff works
    import os
    orig_cwd = os.getcwd()
    os.chdir('$GIT_DIR')

    import io
    sys.stdout = io.StringIO()
    r = cmd_pr_manage_changes(Args())
    out = sys.stdout.getvalue()
    sys.stdout = sys.__stdout__

    os.chdir(orig_cwd)

    data = json.loads(out)
    print(f'manage-changes result: {data}')
    assert data['status'] == 'ok', f'Expected ok, got {data}'
    assert data['total_files'] == 2, f'Expected 2 files, got {data[\"total_files\"]}'
    assert data['total_added'] == 2, f'Expected 2 added, got {data[\"total_added\"]}'
    assert any('/_apis/git/favorites/refs?api-version=7.1' in cmd for cmd in az_commands), az_commands
    assert any(body == {'name': 'refs/heads/feature', 'repositoryId': 'repo-guid', 'type': 'ref'} for body in az_bodies), az_bodies

    # Verify changes.json was written
    changes_path = os.path.join(cache_dir, 'changes.json')
    assert os.path.isfile(changes_path), 'changes.json should exist'
    with open(changes_path) as f:
        cached = json.load(f)
    assert cached['total_files'] == 2
    assert cached['files'][0]['filename'] == 'file.txt'
    assert cached['files'][1]['filename'] == 'new.txt'

    # Test that _format_manage_content includes changes and file thread counts when caches exist.
    with open(os.path.join(cache_dir, 'threads.json'), 'w') as f:
        json.dump({
            'value': [
                {
                    'id': 21,
                    'status': 'active',
                    'threadContext': {'filePath': '/file.txt', 'rightFileStart': {'line': 1}},
                    'comments': [{'commentType': 'text', 'content': 'Please review this line', 'author': {'uniqueName': 'reviewer@example.com'}}],
                },
                {
                    'id': 22,
                    'status': 'fixed',
                    'threadContext': {'filePath': '/file.txt', 'rightFileStart': {'line': 2}},
                    'comments': [{'commentType': 'text', 'content': 'Already fixed', 'author': {'uniqueName': 'reviewer@example.com'}}],
                },
                {
                    'id': 23,
                    'status': 'closed',
                    'threadContext': {'filePath': '/new.txt', 'rightFileStart': {'line': 1}},
                    'comments': [{'commentType': 'text', 'content': 'Closed comment', 'author': {'uniqueName': 'reviewer@example.com'}}],
                },
                {
                    'id': 24,
                    'status': 'active',
                    'threadContext': {'filePath': '/unchanged.txt', 'rightFileStart': {'line': 1}},
                    'comments': [{'commentType': 'text', 'content': 'Not in diff', 'author': {'uniqueName': 'reviewer@example.com'}}],
                },
            ],
        }, f)

    from gg.cmd_pr import _format_manage_content
    content = _format_manage_content(pr, cache_dir)
    assert 'M  file.txt  +1 -1 [1/2 threads]' in content, f'Expected thread counts for file.txt in content, got:\\n{content}'
    assert 'A  new.txt  +1 [0/1 threads]' in content, f'Expected thread counts for new.txt in content, got:\\n{content}'
    assert 'unchanged.txt' in content
    assert 'unchanged.txt  +' not in content
    assert '2 files changed' in content
    assert '2 files changed +2 -1\\n\\n# Policies' in content, f'Expected blank line before Policies, got:\\n{content}'

    from gg.cmd_pr import cmd_pr_manage_diff_open
    sys.stdout = io.StringIO()
    os.chdir('$GIT_DIR')
    try:
        r = cmd_pr_manage_diff_open(Args())
    finally:
        os.chdir(orig_cwd)
    out = sys.stdout.getvalue()
    sys.stdout = sys.__stdout__
    diff_data = json.loads(out)
    assert r == 0
    assert diff_data['status'] == 'ok'
    assert os.path.isfile(diff_data['path'])
    with open(diff_data['path']) as f:
        diff_lines = f.read().splitlines()
    by_id = {str(a['thread_id']): a for a in diff_data['annotations']}
    assert '21' in by_id, f'Expected file.txt annotation, got {diff_data}'
    assert '23' in by_id, f'Expected new.txt annotation, got {diff_data}'
    assert '24' not in by_id, f'Unexpected annotation for unchanged file: {diff_data}'
    assert diff_lines[by_id['21']['diff_line'] - 1] == '+change'
    assert by_id['21']['file_path'] == 'file.txt'
    assert by_id['21']['preview'] == 'Please review this line'
    line_map = diff_data['line_map']
    added_line = next(line for line, loc in line_map.items() if loc['file_path'] == '/file.txt' and loc['line'] == 1 and loc['side'] == 'right')
    deleted_line = next(line for line, loc in line_map.items() if loc['file_path'] == '/file.txt' and loc['line'] == 1 and loc['side'] == 'left')
    new_file_line = next(line for line, loc in line_map.items() if loc['file_path'] == '/new.txt' and loc['line'] == 1 and loc['side'] == 'right')
    assert diff_lines[int(added_line) - 1] == '+change'
    assert diff_lines[int(deleted_line) - 1] == '-initial'
    assert diff_lines[int(new_file_line) - 1] == '+new'

print('PASS: _manage-changes computes and caches diff stats')
"

echo ""
echo "=== All tests PASSED ==="
