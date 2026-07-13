# `gg pr manage` — Local PR Management in Neovim

## Overview

`gg pr manage <id>` opens a neovim-based management interface for Azure DevOps
pull requests. It provides a read-only markdown buffer showing PR metadata,
title/description, and reviewers with vote status, along with keymaps for
editing and publishing changes.

## Usage

```bash
gg pr manage <id>
```

## How It Works

1. Fetches PR details from Azure DevOps via `az repos pr show --id <id>`.
2. Creates cache directory at `~/.cache/gg/pr-<id>/` containing:
   - `pr.json` — raw PR data from Azure DevOps
   - `manage.md` — formatted management buffer
   - `manage.lua` — neovim Lua configuration
3. Cleans up stale `summary.md`, `status.txt`, `vote.txt`, `changes.log`, and `threads.log` from previous sessions.
4. Opens `manage.md` in neovim with `manage.lua` loaded.

## Management Buffer Layout

```
id: 12345
status: active                  # metadata header
source: my-branch
target: main
created: user@domain.com
                                # <-- empty line = header boundary
# Title of the PR

Description text goes here.
Multiple lines supported.

# Reviewers

- reviewer1 (required) - **approved**
- reviewer2 (required) - **no vote**
- reviewer3 - **wait for author**

# Threads

- [3213412] (**fixed**) by reviewer@example.com /src/foo.py:12 2026-06-26 12:23
  Comment preview trimmed to one line

# Changes

M  src/foo.py  +5 -3 [0/1 threads]
A  src/bar.py  +10

2 files changed +15 -3

# Policies

- [123] Required Build - **approved**
- [124] Required Tests - **expired**
  Unit tests failed
```

The buffer has two sections:
- **Header** — lines above the first empty line (status, source, target, creator)
- **Content** — everything below the header (title, description, reviewers, threads, changes, policies)

The buffer is:
- Markdown filetype (`vim.bo.filetype = 'markdown'`)
- Non-modifiable (`vim.bo.modifiable = false`)
- Marked modified only when staged summary or status changes exist
- `bufhidden=hide` (hidden instead of unloaded when switching buffers)

## Keymaps

### `A` — PR Action Menu

Pressing `A` anywhere opens `vim.ui.select()` with PR-wide actions:

| Action | Behavior |
|--------|----------|
| `Status: abandoned` | Stage PR status `abandoned` |
| `Status: draft` | Stage PR status `draft` |
| `Status: active` | Stage PR status `active` |
| `Status: complete` | Stage PR status `completed` |
| `Status: auto-complete` | Stage PR status `auto-complete` |
| `Vote: approve` | Stage reviewer vote `10` |
| `Vote: approve with suggestion` | Stage reviewer vote `5` |
| `Vote: reset` | Stage reviewer vote `0` |
| `Vote: wait for author` | Stage reviewer vote `-5` |
| `Vote: reject` | Stage reviewer vote `-10` |
| `Vote: abstain` | Stage removing yourself as reviewer |

Staged status and vote changes are local until `pp` publishes them.

### `gr` / `gt` / `gc` / `gp` — Navigate Sections

These mappings jump to top-level management buffer sections:

| Key | Section |
|-----|---------|
| `gr` | `# Reviewers` |
| `gt` | `# Threads` |
| `gc` | `# Changes` |
| `gp` | `# Policies` |

### `o` — Open Context

Pressing `o` in the content section (title/description/reviewers) calls
`gg pr _fetch-summary <id>` to create/open `summary.md` for editing.

### `r` — Context-Sensitive Reload

Pressing `r` reloads content based on cursor position:

| Cursor in | Behavior |
|-----------|----------|
| `# Changes` section | Asynchronously refetches branches and regenerates `# Changes` only |
| `# Threads` section | Asynchronously refetches `# Threads` only and drops unpublished new thread drafts |
| `# Policies` section | Asynchronously refetches `# Policies` only |
| Anywhere else | Asynchronously reloads PR details and drops pending summary/status edits; threads, changes, and policies follow normal cached/background load behavior |

### `R` — Reload Everything

Pressing `R` asynchronously reloads PR details, drops pending summary/status
edits, then asynchronously refetches threads, changes, and policies.

### `a` — Activate Policy Evaluation

When the cursor is on a policy line in the `# Policies` section, pressing `a`
asynchronously queues that policy evaluation through
`gg pr _manage-policy-queue <id> <policy-id>`. The Lua controller only passes the
visible policy configuration ID; the CLI resolves the cached Azure DevOps
`evaluationId` needed by `az repos pr policy queue`.

### `x` — Cancel Policy Build

When the cursor is on a policy line in the `# Policies` section, pressing `x`
asynchronously cancels the build associated with that policy through
`gg pr _manage-policy-cancel <id> <policy-id>`. The CLI resolves the cached policy
`context.buildId`; press `r` in Policies first if the cache is stale.

When the cursor is in the `# Changes` section, pressing `o` asynchronously calls
`gg pr _manage-diff-open <id>`, opens the generated PR diff, and adds virtual-text
markers at diff lines with visible PR threads.

In the generated diff buffer, `]]` jumps to the next thread marker and `[[`
jumps to the previous thread marker, wrapping within the same buffer. Pressing
`o` on a diff line with thread markers opens the thread draft; if multiple
threads map to the same line, a selector is shown. Pressing `o` elsewhere does
nothing.

When the cursor is on a thread line in the `# Threads` section, pressing `o`
calls `gg pr _manage-thread-open <id> <thread-id>` and opens a persistent thread
draft file from the PR cache. The draft includes thread metadata, an optional diff
hunk, existing comments, and a response section below `<!-- gg-response-start -->`.

Returning to the management buffer marks threads with non-empty draft responses as `[modified]`.

### `ca` / `cf` / `cw` / `cc` — Change Thread Status

When the cursor is on a thread line in the `# Threads` section, these mappings
stage a local thread status change without publishing immediately:

| Key | Thread status |
|-----|---------------|
| `ca` | `active` |
| `cf` | `fixed` |
| `cw` | `wontFix` |
| `cc` | `closed` |

The status is written to the thread draft frontmatter and published by `pp`. If
the draft already has a pending reply, the reply text is preserved.

### `a` — Add Thread Draft

When the cursor is in the `# Threads` section, pressing `a` creates and opens a
new general PR thread draft. The draft is local only until `pp` publishes it.

In the generated diff buffer, pressing `a` on an added line creates a
right-side thread draft, pressing `a` on a deleted line creates a left-side
thread draft, and pressing `a` on a context line creates a right-side thread
draft. Pressing `a` on diff metadata lines does nothing.

### `pp` — Publish All Changes

Pressing `pp` publishes all pending changes:
- Reads `summary.md` for title and description
- Reads `status.txt` for status change
- Reads `vote.txt` for reviewer vote/self-removal change
- Reads thread draft responses from `threads/thread-<id>.md`
- Reads thread status changes from `threads/thread-<id>.md`
- Reads new thread drafts from `threads/new-<id>.md`
- Sends PR metadata/status changes to Azure DevOps, applies staged reviewer
  vote, updates staged thread statuses, and posts each staged thread response
- On success: updates `pr.json`, removes `status.txt`/`vote.txt`, posts thread
  responses and new threads, removes posted thread draft files, refreshes view

Returns one of:
- `{"status": "ok"}` — published successfully
- `{"status": "no_changes"}` — nothing to publish
- `{"status": "error", "message": "..."}` — API error

## Status Management

Five statuses are supported:

| Label | Azure DevOps Mapping |
|-------|---------------------|
| `active` | `isDraft: false` |
| `draft` | `isDraft: true` |
| `abandoned` | `status: abandoned` |
| `completed` | `status: completed` |
| `auto-complete` | `isDraft: false` (sets the flag; actual auto-complete requires a separate API call) |

Status changes are staged via `_set-status` which writes the new label to
`status.txt`. The header line in the management buffer shows pending changes:

```
status: active -> draft [modified]       # [modified] in WarningMsg highlight
```

## Vote Management

Vote changes are staged via `_set-vote` which writes a vote action to
`vote.txt`. The `# Reviewers` header shows pending vote virtual text:

```
# Reviewers [vote: approve]
```

On publish, vote actions map to Azure DevOps reviewer votes: `approve` = `10`,
`approve with suggestion` = `5`, `reset` = `0`, `wait for author` = `-5`,
`reject` = `-10`. `abstain` removes the current user from the reviewer list;
Azure DevOps may reject this if the user is required by policy.

## View Synchronization

On `BufEnter` (returning to the management buffer), `sync_view()` is called automatically:
1. Runs `gg pr _manage <id>`
2. Updates the title/description section (lines between `# Title` and `# Reviewers`)
3. Updates the `# Reviewers` section from refreshed `pr.json`
4. Updates the `status:` header line
5. Adds `[modified]` extmarks:
   - On the title line when title/description differs from `pr.json` (`data.changed == true`)
   - On the status line when status is pending (`data.status_changed == true`)

## Changes Section

The `# Changes` section shows diff stats between `origin/<source>` and
`origin/<target>`, same format as `gg wc`. If a changed file has visible
comment threads, the file line includes `[N/M threads]`, where `N` is active
threads and `M` is all visible threads for that file:

```
# Changes

M  src/foo.py  +5 -3 [1/2 threads]
A  src/bar.py  +10

2 files changed +15 -3
```

### Caching & Background Load

- Stats are cached in `changes.json` in the cache directory
- If `changes.json` exists, stats render immediately when the buffer opens
- Otherwise `[loading]` virtual text appears next to the `# Changes` heading
- `_manage-changes` best-effort marks the PR source branch as an Azure DevOps
  Git ref favorite via `/_apis/git/favorites/refs`, then `git fetch origin
  <source> <target>` and diff computation run in the background
- On completion, `changes.json` is written, the buffer is updated, and the loading marker is removed
- Thread counts are derived from raw `threads.json`; Azure DevOps file paths
  are normalized by removing the leading `/` before matching git diff filenames
- `o` opens `diff.diff` from the cache directory and marks thread locations
  with virtual text like `[thread 123 active] ...`
- Errors are logged to `changes.log` in the cache directory

## Threads Section

The `# Threads` section shows pull request comment threads:

```
# Threads

- [3213412] (**fixed**) by reviewer@example.com /src/foo.py:12 2026-06-26 12:23
  Comment preview trimmed to one line
- [3213413] (**closed**) by author@example.com 2026-06-26 15:23
  Another comment preview
```

All non-system threads are shown, including resolved or closed ones.
System-only threads are shown only while active.

Local new-thread drafts are appended to the section as `(**draft**) [new]`.
Drafts with non-placeholder comments are marked `[modified]` and are published
by `pp`.

### Caching & Background Load

- Raw Azure DevOps thread response is cached in `threads.json` in the cache directory
- If `threads.json` exists, threads render immediately when the buffer opens
- Otherwise `[loading]` virtual text appears next to the `# Threads` heading
- Thread fetching runs in the background via `_manage-threads`
- On completion, `threads.json` is written, the buffer is updated, and the loading marker is removed
- Errors are logged to `threads.log` in the cache directory
- Explicitly reloading the Threads section with `r` drops unpublished `threads/new-*.md` drafts. Existing thread response drafts are preserved.

## Policies Section

The `# Policies` section shows required policies in the same shape as `gg pr show`:

```
# Policies

- [123] Required Build - **approved**
- [124] Required Tests - **expired**
  Unit tests failed
```

Only blocking policies are shown. Rejected policy error previews are shown
below the policy line when Azure DevOps provides them.

### Caching & Background Load

- Raw `az repos pr policy list` output is cached in `policies.json` in the cache directory
- If `policies.json` exists, policies render immediately when the buffer opens
- Otherwise `[loading]` virtual text appears next to the `# Policies` heading
- Policy fetching runs in the background via `_manage-policies`
- On completion, `policies.json` is written, the buffer is updated, and the loading marker is removed
- Errors are logged to `policies.log` in the cache directory

## Highlight Groups

| Highlight | Matches | Color |
|-----------|---------|-------|
| `ApprovedHL` | `**approved**` | Green (`#00ff00`) |
| `WaitForAuthorHL` | `**wait for author**` | Red (`#ff0000`) |
| `NoVoteHL` | `**no vote**` | Grey (`#808080`) |
| `ChangesModifiedHL` | `M` file marker in Changes section | Yellow (`#ffff00`) |
| `ChangesAddedHL` | `A` file marker in Changes section | Green (`#00ff00`) |
| `ChangesDeletedHL` | `D` file marker in Changes section | Red (`#ff0000`) |
| `ChangesAddHL` | `+<N>` in Changes section | Green (`#00ff00`) |
| `ChangesDelHL` | `-<N>` in Changes section | Red (`#ff0000`) |
| `ThreadFixedHL` | `**fixed**` in Threads section | Green (`#00ff00`) |
| `ThreadActiveHL` | `**active**` in Threads section | Yellow (`#ffff00`) |
| `DiffThreadHL` | Non-active thread virtual text in diff buffers | Cyan (`#00ffff`) |
| `PolicyQueuedHL` | `**queued**` in Policies section | Yellow (`#ffff00`) |
| `PolicyRunningHL` | `**running**` in Policies section | Yellow (`#ffff00`) |
| `PolicyRejectedHL` | `**rejected**` in Policies section | Red (`#ff0000`) |
| `PolicyExpiredHL` | `**expired**` in Policies section | Red (`#ff0000`) |
| `PolicyNotApplicableHL` | `**notApplicable**` in Policies section | Grey (`#808080`) |

Defined once on first load (`vim.g.gg_pr_manage_init`). Reviewer and thread
status highlights are applied via `matchadd`. `ChangesAddHL`/`ChangesDelHL` are
applied via extmarks.

## Internal Commands

These are called by the Lua code, not intended for direct use:

### `gg pr _manage <id>` (sync)

Reads `pr.json` and optional `summary.md`/`status.txt`/`vote.txt`, returns JSON:

```json
{
  "status": "ok",
  "title": "Current title",
  "description_lines": ["line1", "line2"],
  "changed": false,
  "pr_status": "draft",
  "original_status": "active",
  "status_changed": true,
  "vote_changed": true,
  "pending_vote": "approve",
  "pending_vote_label": "approve"
}
```

### `gg pr _fetch-summary <id>`

Creates `summary.md` in the cache directory if it doesn't exist (seeded with
current title and description). Returns JSON:

```json
{"status": "ok", "path": "/path/to/summary.md", "created": true}
```

### `gg pr _manage-reload <id>`

Fetches current PR details, writes `pr.json`, and drops pending
`summary.md`/`status.txt`/`vote.txt` edits. Returns:

```json
{"status": "ok"}
```

### `gg pr _set-status <id> <status>`

Validates the status label and writes it to `status.txt`. Returns:

```json
{"status": "ok", "new_status": "draft"}
```

### `gg pr _set-vote <id> <vote-action>`

Validates the vote action and writes it to `vote.txt`. Valid actions are
`approve`, `approve with suggestion`, `reset`, `wait for author`, `reject`, and
`abstain`. Returns:

```json
{"status": "ok", "new_vote": "approve"}
```

### `gg pr _publish <id>`

Reads `summary.md`, `status.txt`, and `vote.txt`, compares against original
values in `pr.json`, and sends changes to Azure DevOps. Returns:

```json
{"status": "ok"}
```

### `gg pr _manage-changes <id>`

Best-effort marks the PR source branch as an Azure DevOps Git ref favorite,
fetches `origin/<source>` and `origin/<target>`, computes diff stats (`git diff
--name-status` and `--numstat`), writes `changes.json`, and returns JSON:

```json
{
  "status": "ok",
  "files": [{"status": "M", "filename": "src/foo.py", "added": 5, "deleted": 3}],
  "total_files": 2,
  "total_added": 15,
  "total_deleted": 3
}
```

Logs all operations to `changes.log` in the cache directory. Called
asynchronously from neovim PR management buffer via `jobstart`.

### `gg pr _manage-diff-open <id>`

Generates `diff.diff` in the PR cache directory from
`origin/<target>...origin/<source>` and returns thread annotation locations for
visible threads whose Azure DevOps line context maps to a diff line. Also
returns a `line_map` used by the diff-buffer `a` keymap to create located
thread drafts.

```json
{"status": "ok", "path": "/path/to/diff.diff", "annotations": [{"thread_id": 123, "diff_line": 42}], "line_map": {"42": {"file_path": "/src/foo.py", "side": "right", "line": 10}}}
```

### `gg pr _manage-threads <id>`

Fetches pull request threads from Azure DevOps, optionally drops unpublished new thread drafts, writes raw thread response to
`threads.json`, and returns a filtered display payload:

```json
{
  "status": "ok",
  "threads": [
    {
      "id": 3213412,
      "status": "fixed",
      "author": "reviewer@example.com",
      "date": "2026-06-26 12:23",
      "file_path": "/src/foo.py",
      "location": "/src/foo.py:12",
      "preview": "Comment preview trimmed to one line"
    }
  ],
  "total_threads": 1
}
```

Logs all operations to `threads.log` in the cache directory. Called
asynchronously from neovim PR management buffer via `jobstart`.

### `gg pr _manage-thread-open <id> <thread-id>`

Reads raw `threads.json`, finds the requested thread, and creates or opens
`threads/thread-<thread-id>.md` in the PR cache directory. The file is not
overwritten if it already exists, preserving draft responses.

```json
{"status": "ok", "path": "/path/to/thread-123.md", "created": true}
```

### `gg pr _manage-thread-status <id> <thread-id> <status>`

Stages a thread status change by updating the local thread draft frontmatter.
Valid statuses are `active`, `fixed`, `wontFix`, and `closed`. Existing draft
response text is preserved.

```json
{"status": "ok", "path": "/path/to/thread-123.md", "thread_status": "fixed"}
```

### `gg pr _manage-thread-new <id>`

Creates a new local thread draft under `threads/new-<draft-id>.md`. Without
location arguments, the draft is a general PR thread. With `--file-path`,
`--side`, and `--line`, the draft is tied to a diff location and published with
matching Azure DevOps `threadContext`.

```json
{"status": "ok", "path": "/path/to/new-abc123.md", "draft_id": "new-abc123"}
```

### `gg pr _manage-policies <id>`

Fetches pull request policies from Azure DevOps, writes raw `az repos pr policy
list` output to `policies.json`, and returns a filtered display payload:

```json
{
  "status": "ok",
  "policies": [
    {
      "id": 123,
      "name": "Required Build",
      "status": "approved",
      "errors": []
    }
  ],
  "total_policies": 1
}
```

Logs all operations to `policies.log` in the cache directory. Called
asynchronously from neovim PR management buffer via `jobstart`.

### `gg pr _manage-policy-queue <id> <policy-id>`

Reads raw `policies.json`, resolves the visible policy configuration ID to
Azure DevOps `evaluationId`, and queues the policy evaluation. It does not
refresh policies; if the cache is missing or stale, use `r` in the `# Policies`
section first.

```json
{"status": "ok"}
```

### `gg pr _manage-policy-cancel <id> <policy-id>`

Reads raw `policies.json`, resolves the visible policy configuration ID to the
cached policy `context.buildId`, and cancels that Azure Pipelines build. It
does not refresh policies; if the cache is missing or stale, use `r` in the `#
Policies` section first.

```json
{"status": "ok", "build_id": 12345}
```

## Architecture

```
                    neovim                         Python
┌─────────────────────────────┐    ┌──────────────────────────────┐
│  manage.md (read-only)     │    │  cmd_pr_manage               │
│  - metadata header          │◄───│  - fetch PR via az          │
│  - title + description      │    │  - write pr.json            │
│  - reviewers with votes     │    │  - write manage.md          │
│  - threads                  │    │  - generate manage.lua      │
│  - changes with diff stats  │    │  - open nvim                │
│  - policies                 │    │                              │
│  Lua keymaps:               │    │                              │
│  - A → action menu          │    │  cmd_pr_manage_sync         │
│  - o → edit summary.md      │    │  - read pr.json             │
│  - r/R → reload             │───►│  cmd_pr_manage_reload       │
│  - pp → publish changes     │───►│  - read summary.md          │
│                             │    │  - compare & return JSON    │
│  BufEnter → sync_view()     │    │                              │
│    → load_threads()         │───►│  cmd_pr_manage_threads      │
│    → load_changes()         │───►│  cmd_pr_manage_changes      │
│    → load_policies()        │───►│  cmd_pr_manage_policies     │
│      (async via jobstart)   │    │  - git fetch origin         │
│                             │    │  - git diff --name-status   │
│                             │    │  - git diff --numstat       │
│                             │    │  - write changes.json       │
│                             │    │  - write changes.log        │
└─────────────────────────────┘    └──────────────────────────────┘
```

The Lua layer is purely a view — all file I/O and state reconciliation is
handled by Python `gg` helpers. The Lua code calls `gg pr _<subcommand>` via
`vim.fn.system()` for short synchronous calls or `vim.fn.jobstart()` for
background work such as loading threads, changes, policies, and queueing policy
evaluations.
