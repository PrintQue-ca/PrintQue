# Contributing to PrintQue

Thank you for your interest in contributing to PrintQue! This guide will help you get started with development and testing.

## Table of Contents

- [Commit Message Format](#commit-message-format) **(IMPORTANT - READ FIRST)**
- [Development Setup](#development-setup)
- [Running Tests](#running-tests)
- [Code Style](#code-style)
- [Pull Request Process](#pull-request-process)
- [Versioning and Releases](#versioning-and-releases)
- [Project Structure](#project-structure)

---

## Commit Message Format

> **This project uses [Conventional Commits](https://www.conventionalcommits.org/) to automate versioning and releases. All commits MUST follow this format.**

### Format

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### Types

| Type | Description | Version Bump |
|------|-------------|--------------|
| `feat` | A new feature | **MINOR** (1.0.0 → 1.1.0) |
| `fix` | A bug fix | **PATCH** (1.0.0 → 1.0.1) |
| `perf` | Performance improvement | **PATCH** |
| `docs` | Documentation only | None |
| `style` | Formatting, whitespace | None |
| `refactor` | Code restructuring | None |
| `test` | Adding/updating tests | None |
| `build` | Build system changes | None |
| `ci` | CI configuration | None |
| `chore` | Maintenance tasks | None |
| `revert` | Revert a commit | Depends |

### Breaking Changes

For breaking changes that require a **MAJOR** version bump (1.0.0 → 2.0.0):

```bash
# Option 1: Add ! after the type
feat!: remove deprecated printer API

# Option 2: Add BREAKING CHANGE footer
feat: redesign order system

BREAKING CHANGE: Order IDs are now UUIDs instead of integers
```

### Examples

```bash
# Good - triggers minor version bump
feat: add printer grouping support

# Good - triggers patch version bump  
fix: resolve order queue deadlock issue

# Good - with scope
feat(api): add batch order creation endpoint

# Good - with body for context
fix: prevent duplicate print jobs

The job scheduler was not checking for existing jobs before
queueing, causing duplicate prints on network reconnection.

# Good - breaking change
feat!: migrate to new authentication system

BREAKING CHANGE: API tokens from v1 are no longer valid.
Users must regenerate tokens.

# BAD - missing type
added new feature

# BAD - wrong format
Feature: add printer support

# BAD - not lowercase
Feat: add something
```

### Using Commitizen (Recommended)

Don't want to remember the format? Use the interactive commit helper:

```bash
# From the project root
npm run commit
```

This launches an interactive prompt that guides you through creating a properly formatted commit:

```
? Select the type of change you're committing: (Use arrow keys)
❯ feat:     A new feature
  fix:      A bug fix
  docs:     Documentation only changes
  style:    Changes that don't affect the meaning of the code
  refactor: A code change that neither fixes a bug nor adds a feature
  perf:     A code change that improves performance
  test:     Adding missing tests

? What is the scope of this change (e.g. component or file name)? (press enter to skip)
? Write a short, imperative tense description of the change:
? Provide a longer description of the change: (press enter to skip)
? Are there any breaking changes? (y/N)
? Does this change affect any open issues? (y/N)
```

### Enforcement

Commit messages are **automatically validated** at two levels:

1. **Local (commit-msg hook)**: Commitlint validates format before allowing the commit
2. **CI (pull requests)**: GitHub Actions validates all commits in the PR

If your commit is rejected:
```bash
# Amend the last commit message
git commit --amend -m "feat: correct commit message"

# Or for older commits, use interactive rebase
git rebase -i HEAD~3

# Or just use Commitizen next time!
npm run commit
```

---

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- Git

### Backend Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/PrintQue.git
   cd PrintQue
   ```

2. Install root dependencies (commit tooling):
   ```bash
   npm install
   ```

3. Create a Python virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

4. Install Python dependencies:
   ```bash
   pip install -r api/requirements.txt
   pip install -r api/requirements-dev.txt
   ```

5. Run the API server:
   ```bash
   cd api
   python app.py
   ```

### Frontend Setup

1. Install Node.js dependencies:
   ```bash
   cd app
   npm install
   ```

2. Run the development server:
   ```bash
   npm run dev
   ```

The frontend will be available at http://localhost:3000 and will proxy API requests to http://localhost:5000.

## Running Tests

### Backend Tests (pytest)

Run all backend tests:
```bash
cd api
pytest
```

Run with coverage report:
```bash
pytest --cov=. --cov-report=html
```

Run specific test file:
```bash
pytest tests/test_routes/test_orders.py
```

Run tests matching a pattern:
```bash
pytest -k "test_create"
```

### Frontend Tests (Vitest)

Run all frontend tests:
```bash
cd app
npm run test
```

Run tests in watch mode (for development):
```bash
npm run test:watch
```

Run with coverage:
```bash
npm run test:coverage
```

### Linting

Python (using ruff):
```bash
pip install ruff
ruff check api/
```

TypeScript:
```bash
cd app
npx tsc --noEmit
```

## Code Style

### Python

- Follow PEP 8 guidelines
- Use type hints where possible
- Document functions with docstrings
- Use `ruff` for linting

### TypeScript/React

- Use TypeScript for all new code
- Follow the existing component patterns
- Use functional components with hooks
- Export types from `types/index.ts`

### Commit Messages

**You MUST use Conventional Commits format.** See [Commit Message Format](#commit-message-format) at the top of this document.

**Recommended**: Use Commitizen for guided commits:
```bash
npm run commit
```

Or write commits manually:
```bash
feat: add printer status polling interval
fix: resolve order quantity validation bug
docs: update README with new setup instructions
fix(api): handle null printer response
```

Reference issue numbers in the body or footer:
```bash
fix: resolve printer connection timeout

Closes #123
```

## Pull Request Process

1. **Fork the repository** and create your branch from `main` or `opensource-release`.

2. **Write tests** for any new functionality or bug fixes.

3. **Run all tests** locally to ensure they pass:
   ```bash
   # Backend
   cd api && pytest
   
   # Frontend
   cd app && npm run test
   ```

4. **Update documentation** if you're changing any public APIs.

5. **Create a Pull Request** with:
   - Clear description of the changes
   - Link to any related issues
   - Screenshots for UI changes

6. **Wait for CI** - All tests must pass before merging.

7. **Address review feedback** - Make any requested changes.

## Versioning and Releases

PrintQue uses **automated semantic versioning** based on your commit messages. You don't need to manually update version numbers.

### How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│  Your Commit                                                    │
│  feat: add printer grouping                                     │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  Merge to main                                                  │
│  CI analyzes commits since last release                         │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  Automatic Version Bump                                         │
│  1.2.0 → 1.3.0 (feat = minor bump)                              │
│  Creates tag: v1.3.0                                            │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  Release Build                                                  │
│  • Windows (.exe)                                               │
│  • macOS (.app)                                                 │
│  • Linux (binary)                                               │
│  → GitHub Release with all artifacts                            │
└─────────────────────────────────────────────────────────────────┘
```

### Version Bump Rules

| Commits in PR | Version Change |
|--------------|----------------|
| Only `fix:`, `perf:` | 1.2.3 → 1.2.4 (PATCH) |
| Any `feat:` | 1.2.3 → 1.3.0 (MINOR) |
| Any `feat!:` or `BREAKING CHANGE` | 1.2.3 → 2.0.0 (MAJOR) |
| Only `docs:`, `chore:`, etc. | No release |

### Version Location

The version is maintained in a single source file:
- **Source**: `api/__version__.py`
- **Auto-synced to**: `pyproject.toml`, build artifacts

Do NOT manually edit version numbers. The CI handles this automatically.

### Creating a Release (Maintainers)

Releases happen automatically when commits are merged to `main`. If you need a manual release:

```bash
# Ensure you have the latest main
git checkout main
git pull

# Create and push a tag manually (rare)
git tag v1.2.3
git push origin v1.2.3
```

## Project Structure

```
PrintQue/
├── api/                    # Python Flask backend
│   ├── __version__.py     # VERSION SOURCE OF TRUTH
│   ├── app.py             # Main application entry point
│   ├── routes/            # API route handlers
│   │   ├── orders.py
│   │   ├── printers.py
│   │   └── system.py
│   ├── services/          # Business logic
│   │   ├── state.py       # State management
│   │   ├── printer_manager.py
│   │   └── bambu_handler.py
│   ├── utils/             # Utilities
│   └── tests/             # Backend tests
│       ├── conftest.py    # pytest fixtures
│       ├── test_routes/
│       └── test_services/
│
├── app/                   # React frontend
│   ├── src/
│   │   ├── components/    # React components
│   │   ├── hooks/         # Custom React hooks
│   │   ├── lib/           # Utilities (API client, etc.)
│   │   ├── routes/        # TanStack Router pages
│   │   ├── types/         # TypeScript type definitions
│   │   └── __tests__/     # Frontend tests
│   ├── package.json
│   └── vite.config.ts
│
├── .github/
│   └── workflows/
│       ├── ci.yml         # Lint and test
│       ├── commitlint.yml # PR commit validation
│       ├── version-bump.yml # Auto version bumping
│       └── release.yml    # Multi-platform builds
│
├── .husky/
│   ├── pre-commit         # Lint staged files
│   └── commit-msg         # Validate commit format
│
├── scripts/               # Build and run scripts
│   ├── build.py           # Cross-platform build script (use this)
│   ├── run_app.py         # Dev launcher
│   └── ...
├── package.json           # Root package (commit tooling)
├── commitlint.config.js   # Commit message rules
├── pyproject.toml         # Python project config
└── CONTRIBUTING.md        # This file
```

## Getting Help

- **Issues**: Open a GitHub issue for bugs or feature requests
- **Discussions**: Use GitHub Discussions for questions

## License

By contributing to PrintQue, you agree that your contributions will be licensed under the project's license.
