# gg

## Commands

### fetch-fast-forward (fff)

Fetches upstream for all local branches, goes through them and fast-forwards those that can be fast-forwarded.

### push-fast-forward (pff)

Pushes all local branches to their upstream, but only if they can be fast-forwarded.

### merge-switch (ms)

Merges specified branch with the default branch of upstream, then switches to it. Merge happens
in separate worktree, if it fails user can fix it there and run `ms --continue` to continue the process.

## Party mode

When working in repo on multiple machines, in team - there is a problem when you are working on some
functionality but also rely on changes from others (or from yourself on another machine). In this
case it would be useful to have several branches merged together in the main worktree, keep working
using regular git commands (like commit). I envision following workflow:

### Start party

`party start <new> [<branch1> <branch2> ...]`

Current branch becomes party-default branch, other branches are merged into the merged view in order.

### Add branch to party

`party add <branch>`

### Set party-default branch

`party default <branch>`

### Move commit from "merged" view to particular branch

`party move <commit> <branch>`

### Refreshing party

`party sync` - rebuilds the "merged" view, so it reflects the current state of branches. If there are commits in
"merged" view - they are moved to party-default branch.

### View party status

`party status` - shows involed branches and commits on them

### Finish party

`party finish` - finishes the party, effectivey syncs party, so that all commits are moved, checks out
party-default branch and removes the "merged" view.

### Notes

It should be possible to have several parties at the same time, but only one is active (checked out).

Party is represented by a real local branch, and isolated worktree is used to synthetize it - e.g. `party-sync`
would checkout first branch of party into worktree, then merge branches in order there and at the end would
check it out in main worktree (temp branch can be used in isolated worktree).
