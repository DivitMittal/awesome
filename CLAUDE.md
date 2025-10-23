# CLAUDE.md

## Repository Purpose

This is a personal curated list of FLOSS (Free/Libre open-source software) projects, organized by platform (GitHub, sourcehut, etc.). It follows the "awesome list" format.

## Architecture

This is a content-only repository with a single primary file:
- `README.md`: The main awesome list containing categorized projects with descriptions

## Editing Guidelines

### Formatting Standards
The repository uses `.editorconfig` to enforce consistent formatting:
- **Encoding**: UTF-8
- **Line endings**: LF (Unix-style)
- **Indentation**: 4 spaces (not tabs)
- **Trailing whitespace**: Must be trimmed
- **Spelling**: en-US

When adding or editing content, ensure all changes follow these rules.

### Content Structure
- Projects are organized by hosting platform (GitHub, sourcehut)
- Each project entry includes: name (with link), and description
- Use consistent markdown formatting for links: `[project-name](url): description`

### Git Workflow
- Main branch: `master`
- Commit messages follow conventional commits format (see git log):
  - `docs:` for documentation/content changes
  - `feat:` for new features
  - `fix:` for corrections