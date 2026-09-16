# Code++ / CodexRelay

## 0. 文档目的

本文档用于指导 Codex 直接完成 Code++ 项目的第一阶段工程实现。

## 当前实现状态（v0.3.0）

第一阶段已经完成，并在不改变 Human-in-the-loop 边界的前提下继续迭代。当前实现还包括：有界单跳关联文件发现、Repository Memory CRUD、纯 stdout/安全输出副本、响应大小限制、Git/上下文漂移检测、显式 rebaseline、任务完成记录、原子状态写入、Git 原生 ignore、围栏感知协议解析，以及更严格的补丁与 Windows 路径防护。本文后文保留原始阶段设计；其中把 memory、imports、stdin/file 等列为“未来”或“后续”的描述，均以当前实现和 CLI 文档为准。

项目目标不是自动化 ChatGPT 网页，也不是绕过任何使用限制，而是构建一个本地 AI Coding 协作层，将：

- 高 token 推理
- 方案设计
- Debug 分析
- Refactor 规划
- 测试设计

与：

- 本地文件读取
- 文件修改
- Shell 执行
- Git 操作
- 编译
- 测试
- 最终验证

分离。

核心理念：

> Planner 负责思考，Executor 负责执行。

在 Web Relay 模式下，Planner 可以是用户手动使用的 ChatGPT Chat；Executor 可以是 Codex。

---

# 1. 项目名称

暂定：

**Code++**

副名称：

**CodexRelay**

建议 Python 包名：

```text
codepp
```

CLI：

```text
codepp
```

仓库名可使用：

```text
codeplusplus
```

或：

```text
codex-relay
```

---

# 2. 核心使用场景

传统 Codex 工作流：

```text
User
 ↓
Codex
 ↓
Explore Repository
 ↓
Reason
 ↓
Plan
 ↓
Edit
 ↓
Run
 ↓
Debug
 ↓
Reason Again
 ↓
Edit Again
 ↓
Verify
```

Code++ 工作流：

```text
User
 ↓
Codex / Code++
 ↓
Minimal Context Selection
 ↓
Context Capsule
 ↓
Planner
 ↓
Structured Response
 ↓
Code++
 ↓
Codex
 ↓
Validate
 ↓
Apply
 ↓
Test
 ↓
Verify
```

主要优化目标：

```text
减少 Codex 在以下环节中的重复推理：

- 项目重新理解
- 长上下文分析
- 多方案比较
- Bug 根因推理
- Refactor 规划
- 测试设计
- 文档分析
```

而将 Codex 更多用于：

```text
- 操作真实仓库
- 检查 Planner 假设
- 应用修改
- 执行命令
- 测试
- 修复真实环境问题
```

---

# 3. 产品原则

必须遵守：

## 3.1 Human-in-the-loop Web Relay

Web 模式必须保持：

```text
Code++ → Clipboard → User → ChatGPT

ChatGPT → User → Clipboard → Code++
```

禁止：

```text
Playwright
Selenium
Puppeteer
Chrome CDP
浏览器 Cookie 提取
Session Token 提取
ChatGPT DOM 抓取
自动发送 Prompt
自动读取 ChatGPT 回答
调用未公开 ChatGPT Web API
```

---

## 3.2 Local-first

所有项目状态默认保存在：

```text
.codepp/
```

不建立远程服务器。

---

## 3.3 Minimal Context

Code++ 不应该默认发送整个 Repository。

优先发送：

```text
Task
Relevant Files
Selected Symbols
Git Diff
Diagnostics
Error Logs
Project Metadata
Relevant Memory
```

---

## 3.4 Diff-first

Planner 返回修改内容时优先：

```text
Unified Diff
```

其次：

```text
Structured Edit
```

再次：

```text
Implementation Plan
```

最后才使用：

```text
Full File
```

---

## 3.5 Executor Must Validate

Planner 不能被视为真实 Repository 的权威。

Codex 在执行前必须：

```text
Validate planner assumptions against repository.
```

---

# 4. 项目范围

第一阶段目标实现一个真正可使用的：

```text
CLI + Protocol + Clipboard Relay + Patch Validation + Skill
```

而不是 Demo。

---

# 5. 第一阶段应该实现的功能

## 5.1 CLI

实现：

```bash
codepp init
codepp doctor
codepp export
codepp import
codepp status
codepp show
codepp list
codepp apply
codepp validate
codepp clean
```

后续可选：

```bash
codepp memory
codepp config
codepp benchmark
```

---

# 6. 推荐项目结构

```text
codeplusplus/
│
├── AGENTS.md
├── README.md
├── LICENSE
├── pyproject.toml
├── CHANGELOG.md
│
├── docs/
│   ├── CODEPP_SPEC.md
│   ├── PROTOCOL.md
│   ├── ARCHITECTURE.md
│   ├── SECURITY.md
│   └── CLI.md
│
├── codepp/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   │
│   ├── core/
│   │   ├── context.py
│   │   ├── project.py
│   │   ├── task.py
│   │   ├── state.py
│   │   └── paths.py
│   │
│   ├── protocol/
│   │   ├── request.py
│   │   ├── response.py
│   │   ├── parser.py
│   │   └── schema.py
│   │
│   ├── relay/
│   │   ├── base.py
│   │   └── clipboard.py
│   │
│   ├── security/
│   │   ├── redact.py
│   │   ├── ignore.py
│   │   └── scanner.py
│   │
│   ├── git/
│   │   ├── diff.py
│   │   ├── repo.py
│   │   └── patch.py
│   │
│   ├── utils/
│   │   ├── text.py
│   │   ├── encoding.py
│   │   ├── ids.py
│   │   └── console.py
│   │
│   └── config.py
│
├── skill/
│   └── codepp-relay/
│       └── SKILL.md
│
├── templates/
│   ├── request.md
│   └── response.md
│
└── tests/
    ├── test_context.py
    ├── test_protocol.py
    ├── test_redact.py
    ├── test_ignore.py
    ├── test_patch.py
    ├── test_task_state.py
    └── test_cli.py
```

不要为了严格遵守这个目录而制造无意义文件。

如果某些模块过小，可以合理合并。

核心要求：

```text
职责清晰
模块不要过度抽象
方便后续扩展 Provider
```

---

# 7. 用户项目中的 `.codepp`

执行：

```bash
codepp init
```

后创建：

```text
.codepp/
├── config.toml
├── inbox/
├── outbox/
├── tasks/
├── cache/
├── memory/
└── logs/
```

同时：

```text
.codeppignore
```

---

# 8. config.toml

示例：

```toml
[project]
name = "auto"

[relay]
provider = "clipboard"

[context]
max_file_bytes = 200000
include_git_diff = true
include_git_status = true
include_project_metadata = true

[security]
redact_secrets = true
respect_gitignore = true
respect_codeppignore = true

[patch]
auto_validate = true
auto_apply = false

[output]
language = "auto"
```

---

# 9. `.codeppignore`

语法尽量兼容 `.gitignore`。

默认建议：

```text
.env
.env.*
*.pem
*.key
*.crt
*.p12
*.pfx

credentials*
secrets*
private/

node_modules/
vendor/
dist/
build/
target/

.git/
.idea/
.vscode/

*.sqlite
*.db

data/
datasets/
```

注意：

`.codeppignore` 只控制 Code++ 上下文收集，不修改 Git 行为。

---

# 10. Task 模型

每一次 Relay 对应一个 Task。

建议 ID：

```text
20260914-191055-a7f3
```

Task 元数据：

```json
{
  "task_id": "20260914-191055-a7f3",
  "status": "PACKED",
  "title": "Fix duplicate login request",
  "created_at": "2026-09-14T19:10:55",
  "updated_at": "2026-09-14T19:10:55",
  "files": [
    "src/pages/Login.tsx",
    "src/api/auth.ts"
  ],
  "request_file": ".codepp/outbox/20260914-191055-a7f3.md",
  "response_file": null
}
```

保存：

```text
.codepp/tasks/<task-id>.json
```

---

# 11. Task 状态机

定义：

```text
NEW

PACKED

WAITING_FOR_RESPONSE

RESPONSE_RECEIVED

VALIDATED

READY_TO_APPLY

APPLIED

VERIFYING

DONE

FAILED
```

正常流程：

```text
NEW
 ↓
PACKED
 ↓
WAITING_FOR_RESPONSE
 ↓
RESPONSE_RECEIVED
 ↓
VALIDATED
 ↓
READY_TO_APPLY
 ↓
APPLIED
 ↓
VERIFYING
 ↓
DONE
```

---

# 12. CODEPP/1 Request Protocol

Request 必须是 Markdown。

例如：

```markdown
# CODEPP REQUEST

Protocol: CODEPP/1
Task-ID: 20260914-191055-a7f3

## Task

修复登录按钮重复发送 API 请求的问题。

## Project

Name: demo-app
Language: TypeScript
Framework: React
Package Manager: pnpm

## Repository State

Branch: main

Git Status:

```text
M src/pages/Login.tsx
```

## Relevant Files

### src/pages/Login.tsx

```tsx
...
```

### src/api/auth.ts

```ts
...
```

## Current Diff

```diff
...
```

## Error / Diagnostics

```text
POST /login was triggered twice.
```

## Requirements

Analyze:

1. Root cause
2. Implementation plan
3. Files to modify
4. Unified diff if possible
5. Verification commands
6. Risks
7. Assumptions

## Executor Contract

The downstream executor has access to the real repository.

Do not assume unprovided project facts.

Prefer minimal modifications.

Prefer unified diff.

Finish with a concise `Codex Instruction`.
```

---

# 13. CODEPP/1 Response Protocol

推荐格式：

```markdown
# CODEPP RESPONSE

Protocol: CODEPP/1
Task-ID: 20260914-191055-a7f3

## Diagnosis

...

## Assumptions

...

## Plan

1.
2.
3.

## Files

- src/pages/Login.tsx

## Patch

```diff
...
```

## Verification

```bash
pnpm test
pnpm lint
```

## Risks

...

## Codex Instruction

Validate this plan against the actual repository.
If repository evidence supports it, apply the patch and run verification.
If assumptions are false, adapt minimally rather than redesigning from scratch.
```

---

# 14. Protocol Parser

`codepp import`

必须：

1. 从 Clipboard 获取文本
2. 查找：

```text
Protocol: CODEPP/1
```

3. 解析 Task-ID
4. 检查 Task-ID 是否存在
5. 检查状态是否允许 Import
6. 保存原始 Response
7. 尝试提取：

```text
Diagnosis
Plan
Files
Patch
Verification
Risks
Codex Instruction
```

8. 更新 Task 状态

不要要求所有 Section 都必须存在。

最低要求：

```text
Protocol
Task-ID
```

---

# 15. Context Builder

Context Builder 是核心模块。

输入：

```text
Task Description

Explicit Files

Optional:
selected text
diagnostics
logs
```

输出：

```text
Context Capsule
```

---

# 16. Context Builder 第一阶段

第一阶段不做复杂向量搜索。

支持：

```bash
codepp export "fix login" \
  --files src/Login.tsx src/auth.ts
```

文件由用户或 Codex 明确提供。

---

# 17. 文件读取规则

必须：

```text
检查存在
检查类型
检查大小
检查 ignore
检查 secret
检查 binary
检查 encoding
```

建议默认最大文件：

```text
200 KB
```

超过限制：

```text
[FILE OMITTED: exceeds 200000 bytes]
```

---

# 18. 二进制判断

不要读取：

```text
png
jpg
jpeg
gif
webp
ico
zip
7z
tar
gz
exe
dll
so
dylib
pdf
docx
xlsx
pptx
```

第一阶段可以直接根据：

```text
extension + null byte detection
```

判断。

---

# 19. Secret Redaction

至少检测：

```text
api_key=
apikey=
api-key=
secret=
password=
passwd=
token=
authorization:
bearer
private_key
aws_access_key_id
aws_secret_access_key
```

匹配值替换：

```text
[REDACTED]
```

例如：

```text
OPENAI_API_KEY=sk-abc
```

变成：

```text
OPENAI_API_KEY=[REDACTED]
```

注意：

不要做过度激进匹配。

普通变量：

```text
token_count = 200
```

不应被错误隐藏。

---

# 20. Git 信息

如果 Repository 是 Git Repo：

获取：

```text
git status --short
git branch --show-current
git diff
git diff --cached
```

但第一阶段 Request 默认只加入：

```text
branch
status
git diff
```

`git diff --cached` 可做配置选项。

---

# 21. Clipboard

跨平台支持：

Windows：

优先：

```text
pyperclip
```

macOS：

```text
pbcopy / pbpaste
```

Linux：

```text
xclip / xsel / wl-copy / wl-paste
```

为了降低复杂度，第一版可以依赖：

```text
pyperclip
```

但需要友好报错。

---

# 22. CLI 详细设计

## codepp init

行为：

```text
检测项目根目录
创建 .codepp
创建 config
创建 .codeppignore
创建目录
```

输出：

```text
Code++ initialized.

Project:
C:\project

Created:
.codepp/config.toml
.codepp/inbox
.codepp/outbox
.codepp/tasks
.codeppignore
```

不要覆盖已有配置。

---

# 23. codepp doctor

检查：

```text
Python version
Repository
Git availability
Clipboard support
Config validity
Directory permissions
```

例如：

```text
Code++ Doctor

[OK] Python 3.12
[OK] Git repository
[OK] Git executable
[OK] Clipboard
[OK] Config
[OK] .codepp directory

Code++ is ready.
```

---

# 24. codepp export

支持：

```bash
codepp export "任务"

codepp export "任务" --files a.py b.py

codepp export "任务" --no-diff

codepp export "任务" --copy

codepp export "任务" --print
```

默认：

```text
save + clipboard
```

过程：

```text
Locate project
 ↓
Create task
 ↓
Read files
 ↓
Apply ignore
 ↓
Secret scan
 ↓
Collect git metadata
 ↓
Build request
 ↓
Save outbox
 ↓
Copy clipboard
 ↓
Update state
```

---

# 25. codepp import

支持：

```bash
codepp import
```

默认从 Clipboard。

后续可支持：

```bash
codepp import --file response.md
```

行为：

```text
Read
 ↓
Parse
 ↓
Validate protocol
 ↓
Find task
 ↓
Save inbox
 ↓
Extract patch
 ↓
Validate patch
 ↓
Update status
```

---

# 26. codepp status

无参数：

显示最近 Task。

例如：

```text
Task:
20260914-191055-a7f3

Title:
Fix duplicate login request

Status:
RESPONSE_RECEIVED

Files:
2

Patch:
Detected

Patch validation:
Passed

Next:
codepp apply 20260914-191055-a7f3
```

支持：

```bash
codepp status TASK_ID
```

---

# 27. codepp list

例如：

```text
TASK ID                      STATUS              TITLE
20260914-191055-a7f3        RESPONSE_RECEIVED   Fix duplicate login
20260914-183401-91de        DONE                Refactor API client
```

默认显示最近 20 个。

---

# 28. codepp show

支持：

```bash
codepp show TASK_ID
```

显示：

```text
metadata
request
response summary
patch
verification
```

可选：

```bash
codepp show TASK_ID --request
codepp show TASK_ID --response
codepp show TASK_ID --patch
```

---

# 29. Patch Extraction

从 Response 中寻找：

```markdown
## Patch
```

下的：

```diff
```

代码块。

保存：

```text
.codepp/tasks/<id>.patch
```

---

# 30. Patch Validation

执行：

```bash
git apply --check
```

但必须：

```text
先确认 Repository 是 Git
```

结果：

```text
VALID

INVALID
```

如果 invalid：

保存错误。

---

# 31. codepp validate

例如：

```bash
codepp validate TASK_ID
```

执行：

```text
Protocol validation
Task validation
Patch validation
```

输出：

```text
Protocol: OK
Task: OK
Patch: OK

Ready to apply.
```

---

# 32. codepp apply

必须非常保守。

默认：

```bash
codepp apply TASK_ID
```

行为：

1. 确认 Patch 存在
2. `git apply --check`
3. 检查 Workspace 状态
4. 显示将修改的文件
5. 应用 Patch

第一阶段可以要求：

```text
--yes
```

跳过提示。

但 Codex 调用时需要可脚本化：

```bash
codepp apply TASK_ID --yes
```

---

# 33. Patch Safety

禁止 Patch 修改：

```text
.git/
.codepp/
```

除非未来显式支持。

如果 Patch 目标包括：

```text
.env
credentials
secret files
```

默认拒绝。

---

# 34. Verification Commands

Response 中：

```markdown
## Verification

```bash
pytest
ruff check .
```
```

Parser 可以提取 Commands。

但第一阶段：

**不要自动执行 Planner 返回的任意 Shell。**

因为 Planner 输出不能自动信任。

只保存。

Codex 可读取后决定执行。

---

# 35. 为什么不自动跑 Verification

因为 Response 可能包含：

```bash
rm -rf
curl
wget
sudo
```

所以第一阶段：

```text
planner commands = suggestions only
```

Executor 负责判断。

---

# 36. Skill

项目必须提供：

```text
skill/codepp-relay/SKILL.md
```

目标：

让 Codex 知道什么时候使用 Code++。

建议内容：

```markdown
---
name: codepp-relay
description: Delegate reasoning-heavy coding analysis through Code++ while keeping repository execution local.
---

# Code++ Relay Skill

Use Code++ when substantial reasoning can be separated from repository execution.

Good candidates:

- architecture design
- root-cause analysis
- complex debugging
- multi-file refactoring strategy
- algorithm design
- performance reasoning
- code review
- test strategy

Do not relay:

- simple known edits
- running commands
- formatting
- git status
- trivial renames

## Workflow

1. Inspect only enough repository context to locate relevant files.
2. Avoid solving the whole problem before relay.
3. Export a minimal Code++ request.
4. Tell the user the request is copied and ready for Chat.
5. When the response is imported, validate it against the repository.
6. Apply only valid modifications.
7. Run appropriate tests.
8. Adapt when repository facts contradict planner assumptions.

## Web Safety

Never automate ChatGPT Web.

Never extract cookies, session tokens, DOM responses, or undocumented web APIs.

Web relay remains user-mediated.
```

---

# 37. Codex 与 Code++ 的协作原则

Codex 使用 Code++ 后，禁止这种行为：

```text
先自己深入分析 10 分钟
↓
再 Relay
```

这样没有意义。

应该：

```text
识别问题需要复杂推理
 ↓
快速定位 relevant context
 ↓
Relay
```

---

# 38. Relay 适用评分

可以在 Skill 中增加简单判断。

例如：

```text
+2 architecture decision
+2 complex bug
+2 algorithm design
+2 refactoring strategy
+1 > 5 files
+1 multiple solution comparison
+1 extensive reasoning requested

-2 trivial edit
-2 known single-file change
-2 command execution only
-2 formatting only
```

如果：

```text
score >= 3
```

考虑 Relay。

但不要在程序中强制实现。

先作为 Codex 行为指南。

---

# 39. Repository Memory

第一阶段创建目录：

```text
.codepp/memory/
```

但不做自动生成。

用户可以手动放：

```text
architecture.md
conventions.md
commands.md
decisions.md
```

export 支持：

```bash
--memory
```

未来加入。

第一阶段默认不加入 Request，避免 Context 膨胀。

---

# 40. Project Metadata

自动检测：

Python：

```text
pyproject.toml
requirements.txt
setup.py
```

Node：

```text
package.json
pnpm-lock.yaml
yarn.lock
package-lock.json
```

Rust：

```text
Cargo.toml
```

Go：

```text
go.mod
```

Java：

```text
pom.xml
build.gradle
```

只用于生成简短 Project Metadata。

不要把整个配置文件加入 Request。

---

# 41. 可读输出

CLI 不需要花哨 TUI。

可以使用：

```text
rich
```

但如果为了减少依赖，可以使用标准 print。

建议：

```text
rich
pyperclip
```

作为主要外部依赖。

---

# 42. Python 版本

最低：

```text
Python 3.11
```

优先兼容：

```text
3.11
3.12
3.13
```

---

# 43. pyproject.toml

推荐：

```toml
[project]
name = "codepp"
version = "0.1.0"
requires-python = ">=3.11"

dependencies = [
    "pyperclip>=1.9"
]

[project.scripts]
codepp = "codepp.cli:main"
```

如果使用 Typer：

```text
typer
```

也可以。

第一阶段优先：

```text
argparse
```

减少依赖。

---

# 44. 错误处理

错误输出必须面向普通开发者。

不要：

```text
KeyError: ...
```

优先：

```text
Error: no Code++ project was found.

Run:

    codepp init
```

---

# 45. Windows 支持

用户主要可能在 Windows 使用。

特别注意：

```text
Path
CRLF
PowerShell
Clipboard
UTF-8
```

不要假定 `/bin/bash` 存在。

---

# 46. Encoding

默认：

```text
UTF-8
```

读取失败时：

```text
尝试 utf-8-sig
```

不要做复杂编码猜测。

---

# 47. Logging

日志：

```text
.codepp/logs/codepp.log
```

记录：

```text
timestamp
command
task id
status
warning
error
```

禁止记录：

```text
完整 Secret
完整 clipboard response
敏感文件内容
```

---

# 48. Security

至少防止：

## Secret leakage

通过：

```text
ignore
redact
scanner
```

## Path traversal

用户指定：

```text
../../secret
```

应该检查是否允许。

默认只允许 Repository 内文件。

---

# 49. Symlink

第一阶段：

解析真实路径。

如果 Symlink 指向 Repository 外：

默认拒绝。

---

# 50. Tests

最低测试：

## Context

- 正常读取
- 文件不存在
- 大文件
- Binary
- ignored

## Redaction

- API key
- password
- bearer
- false positive

## Protocol

- valid request
- valid response
- missing task id
- wrong protocol

## Task

- creation
- state transitions
- persistence

## Patch

- extraction
- valid patch
- invalid patch

## CLI

- init
- export
- import

---

# 51. Integration Test

创建临时 Git Repo。

流程：

```text
git init
 ↓
create app.py
 ↓
commit
 ↓
modify app.py
 ↓
codepp init
 ↓
codepp export
 ↓
simulate response
 ↓
codepp import
 ↓
codepp validate
```

必须至少有一个完整 Integration Test。

---

# 52. README

README 至少包含：

```text
What is Code++
Why it exists
Architecture
Install
Quick Start
CLI
Code++ Protocol
Codex Skill
Security
Limitations
Roadmap
```

---

# 53. README Quick Start

理想：

```bash
pip install -e .

codepp init

codepp export "Fix duplicate login request" \
  --files src/Login.tsx src/auth.ts
```

然后：

```text
Paste the clipboard content into ChatGPT.
```

回答后：

```bash
codepp import

codepp status
```

Codex：

```text
Read the latest Code++ task.
Validate it against the repository and implement it.
```

---

# 54. `AGENTS.md`

项目根目录必须创建：

```markdown
# Code++

Read `docs/CODEPP_SPEC.md` before making architectural changes.

## Goal

Code++ separates reasoning from local execution.

## Current scope

CLI + clipboard relay + protocol + patch validation + Codex skill.

## Critical safety rule

Never automate ChatGPT Web.

Do not implement:

- browser automation
- cookie extraction
- session extraction
- DOM scraping
- undocumented ChatGPT web API access

## Engineering principles

Prefer simple code.

Avoid premature abstraction.

Add tests for core behavior.

Keep Windows compatibility.

Do not expose secrets.

Validate planner output before applying it.
```

---

# 55. 未来 Provider 架构

第一阶段只实现：

```text
ClipboardProvider
```

但接口可以预留：

```python
class RelayProvider:
    def send(self, request: str) -> None:
        ...

    def receive(self) -> str:
        ...
```

不要实现：

```text
OpenAIProvider
AnthropicProvider
LocalProvider
```

但结构允许未来增加。

---

# 56. 为什么预留 Provider

未来架构：

```text
                Code++
                   │
        ┌──────────┼───────────┐
        │          │           │
        ▼          ▼           ▼
    Clipboard   Official API   Local
```

Code++ 本身不应该依赖某一个 Planner。

---

# 57. 未来 VS Code Extension

第一阶段不实现。

未来功能：

```text
Code++: Export Context
Code++: Import Response
Code++: Show Current Task
Code++: Apply Patch
```

Extension 调用 CLI 即可。

避免重复实现核心逻辑。

---

# 58. 未来 Context Selector

V0.1：

```text
explicit files
```

V0.2：

可以加入：

```text
imports
references
tests
symbols
dependency graph
```

但不要在本阶段做复杂 embedding / vector DB。

---

# 59. 未来 Repository Memory

可以生成：

```text
architecture.md
commands.md
conventions.md
decisions.md
```

目标：

减少模型重复理解 Repository。

---

# 60. 未来 Benchmark

未来增加：

```bash
codepp benchmark
```

记录：

```text
task
duration
relay count
Codex interactions
first-pass success
tests
manual interventions
```

重点不是承诺省多少额度，而是测量：

```text
Quota
Quality
Time
```

---

# 61. 第一阶段明确不做

不要实现：

```text
ChatGPT Web 自动化
Browser automation
自动网页读取
Cookie/session
Reverse engineered Web APIs
Full autonomous Planner
Vector DB
Embeddings
VS Code extension
GUI
Cloud backend
User accounts
Telemetry
Database server
Docker requirement
复杂 plugin system
```

---

# 62. 第一阶段完成标准

只有同时满足以下条件才算完成：

## Install

```bash
pip install -e .
```

成功。

## Init

```bash
codepp init
```

成功。

## Export

```bash
codepp export "test task" --files README.md
```

成功。

并：

```text
创建 Task
创建 Request
复制 Clipboard
```

## Import

模拟 CODEPP RESPONSE 后：

```bash
codepp import
```

成功。

## Status

```bash
codepp status
```

显示正确状态。

## Patch

包含合法 Patch 的 Response：

```text
能够提取
能够 git apply --check
```

## Tests

```bash
pytest
```

全部通过。

---

# 63. Codex 实施顺序

严格推荐：

## Phase 1

建立：

```text
pyproject
package
CLI
paths
config
```

## Phase 2

实现：

```text
task model
state
storage
```

## Phase 3

实现：

```text
ignore
file reader
redaction
context
git metadata
```

## Phase 4

实现：

```text
CODEPP/1 request
export
clipboard
```

此时完成第一次真实：

```text
codepp export
```

## Phase 5

实现：

```text
response parser
import
task matching
```

## Phase 6

实现：

```text
patch extraction
patch validation
apply
```

## Phase 7

实现：

```text
doctor
status
list
show
```

## Phase 8

实现：

```text
tests
integration test
```

## Phase 9

完善：

```text
README
docs
SKILL.md
AGENTS.md
```

---

# 64. Codex 开发行为要求

Codex 不要每完成一个小模块就停下来询问用户。

除非：

```text
存在不可解决的关键冲突
```

否则自行采用合理方案。

本文档中存在小范围实现细节缺失时：

```text
选择最简单、最安全、最容易维护的实现。
```

---

# 65. 完成后必须自行验证

Codex 完成开发后执行：

```text
python version
pip install -e .
pytest
codepp doctor
codepp init
codepp export
codepp import
codepp status
```

并创建一个 Temporary Git Repository 做一次完整 Relay 测试。

---

# 66. 最终交付报告

完成后输出：

## Implemented

列出已实现。

## Architecture

说明核心模块。

## Tests

说明：

```text
多少测试
是否通过
```

## Manual validation

说明实际执行了哪些 CLI。

## Limitations

当前版本已知限制。

## Next recommended milestone

只推荐下一阶段，不直接实现下一阶段。

---

# 67. 项目定位

不要将 Code++ 定义成：

> Codex limit bypass.

应定义成：

> A reasoning orchestration layer for AI coding agents.

或者：

> Separate thinking from execution.

Code++ 的价值应该即使在额度规则未来改变后依然成立。

---

# 68. 最终原则

整个项目始终围绕一句话：

> Use coding agents for the work that actually requires coding agents.

Planner：

```text
Think
Analyze
Design
Review
```

Executor：

```text
Inspect
Modify
Run
Test
Verify
```

Code++：

```text
Connect them efficiently.
```
