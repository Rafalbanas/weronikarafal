# Contributing to the Project

Welcome! We appreciate your interest in contributing to this project. Small Pull Requests (PRs) are highly welcomed and encouraged.

## Getting Started
- Refer to [README.md](README.md) for local setup instructions.
- For reporting sensitive security vulnerabilities, please refer to [SECURITY.md](SECURITY.md).

## Development Guidelines
- **Data Privacy:** Always use dummy guests and a separate local database for development.
- **Security:** NEVER send codes, passwords, media, or SQLite files to issues or PRs.
- **Project Constraints:** Maintain support for PL+EN (Polish/English), both themes, mobile view (320px), keyboard & no-JS support, CSRF protection, and permissions.
- **Environment:** Node.js is required for running tests but is not needed for production runtime.

## Testing and Validation
Run the following commands to verify your changes:
- Unittests: `.venv/bin/python -m unittest discover -s tests -v`
- Site Check: `.venv/bin/python scripts/check_site.py`
- Compilation Check: `.venv/bin/python -m compileall -q app.py manage.py wedding scripts deploy tests`
- Shell Syntax: `bash -n deploy/ssh-command.sh`
- Whitespace check: `git diff --check`

## Pull Request Requirements
Every PR should include:
- A clear description of the goal and changes.
- Summary of tests performed.
- Synthetic screenshots for changes affecting the UI.

## Deployment and Dependencies
- Do not touch production environments.
- Merges to the `main` branch may trigger deployment.
- This repository does not configure Dependabot automerge. Updates to dependencies must follow the procedure outlined in [docs/automation.md](docs/automation.md) and [deploy/README.md](deploy/README.md).

## License
Contributions are governed by the MIT license, as specified in [LICENSE](LICENSE).

Thank you for your contribution!
