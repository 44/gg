id: 12345
status: active
source: my-branch
target: main
created: email@domain.com
draft: no
auto-complete: no

# Title goes here

<description>

# Reviewers

- <name> (required) - **approved**
- <name> (required) - **no vote**
- <name> - **wait for author**

# Threads

- [3213412] (**fixed**) by <author> <file:line> 2026-06-26 12:23
  Trimmed and sanitized content to fit into one line
- [3213412] (**active**) by <author> 2026-06-26 15:23
  Trimmed and sanitized content to fit into one line

# Changes

M  src/component/main.cpp  +13
M  src/component/component.h  +6 -1
M  tests/integration.cpp  +13

# Policies

- [123] Required Build - **approved**
- [124] Required Tests - **expired**
  Unit tests failed
