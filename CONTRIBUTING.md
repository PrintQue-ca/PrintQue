# Contributing to PrintQue

Thank you for your interest in contributing to PrintQue! This guide will help you get started with development and testing.

## Table of Contents

- [Development Setup](#development-setup)
- [Running Tests](#running-tests)
- [Code Style](#code-style)
- [Pull Request Process](#pull-request-process)
- [Project Structure](#project-structure)

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

2. Create a Python virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r api/requirements.txt
   pip install -r api/requirements-dev.txt
   ```

4. Run the API server:
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

- Use clear, descriptive commit messages
- Start with a verb (Add, Fix, Update, Remove, etc.)
- Reference issue numbers when applicable

Examples:
```
Add printer status polling interval
Fix order quantity validation bug
Update README with new setup instructions
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

## Project Structure

```
PrintQue/
├── api/                    # Python Flask backend
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
│       └── ci.yml         # GitHub Actions CI
│
└── CONTRIBUTING.md        # This file
```

## Getting Help

- **Issues**: Open a GitHub issue for bugs or feature requests
- **Discussions**: Use GitHub Discussions for questions

## License

By contributing to PrintQue, you agree that your contributions will be licensed under the project's license.
