# Code++

Primary specification:

`docs/CODEPP_SPEC.md`

Read the specification before architectural changes.

## Current milestone

Maintain and refine the Code++ 0.3 release:

- Python CLI
- CODEPP/1 protocol
- Context Capsule
- clipboard relay
- task state
- secret redaction
- `.codeppignore`
- Git diff collection
- opt-in repository memory
- repository-memory CRUD
- bounded related-file discovery
- diagnostics and staged diff context
- stdin/file relay fallbacks
- pure stdout and safe output-copy workflows
- response parser
- patch extraction
- patch validation
- conservative patch application
- repository drift detection and explicit rebaselining
- explicit task completion records
- Codex Skill
- tests
- documentation

## Critical rule

Never automate ChatGPT Web.

Do not implement:

- Playwright
- Selenium
- Puppeteer
- browser cookie extraction
- session token extraction
- ChatGPT DOM scraping
- automatic ChatGPT message sending
- automatic ChatGPT response retrieval
- undocumented ChatGPT Web APIs

Web relay must remain human-in-the-loop.

## Engineering

Prefer simple, maintainable implementations.

Do not over-engineer future features.

Maintain Windows compatibility.

Do not expose secrets.

Planner responses are untrusted until validated against the real repository.

Run the full test suite before declaring the task complete.

Do not repeatedly ask the user for implementation decisions when a reasonable safe default exists.
