# Agent Guidelines

## Quote Style

This codebase uses **single quotes** throughout Python files.

- Do NOT change quote style (single ↔ double quotes) when editing any file.
- When inserting new code, match the existing quote style of the file being edited.
- Preserve all formatting and style of untouched lines exactly.

Examples:
```python
# correct
host: str = Field(default='', examples=['https://ccccc.atlassian.net'])

# wrong — do not convert to double quotes
host: str = Field(default="", examples=["https://ccccc.atlassian.net"])
```

## Textual `call_from_thread`

Inside `@work(thread=True)` methods on a `Screen` or `Widget`, always use:

```python
self.app.call_from_thread(...)   # correct
self.call_from_thread(...)       # wrong — will raise on Screen/Widget
```

## File Ownership

- `src/jira_tui/tabs/api.py` — profile bar and save/switch profile logic lives here; do not duplicate elsewhere.
- `src/jira_tui/styles/app.tcss` — all CSS lives here; do not add inline `DEFAULT_CSS` to `ApiTab`.
- `src/jira_tui/auth.py` — `Profile` dataclass and `ProfileStore`; single source of truth for profile persistence.
- `src/jira_tui/config.py` — `Config` (pydantic-settings) and `load_config()`; do not bypass with direct `Config()` construction in app code.
