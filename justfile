# format justfile and list recipes
[private]
default:
    just --fmt --unstable 2> /dev/null
    just --list --unsorted

[group("Jira")]
@jira_tui *args:
    uv run -m jira_tui {{ args }}
