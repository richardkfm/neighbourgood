# Contributing to NeighbourGood

First, thank you for considering contributing to NeighbourGood! It's people like you that make NeighbourGood such a great tool. We welcome contributions from everyone: code, documentation, design, bug reports, and feature ideas.

## Code of Conduct

Please note that this project is released with a [Contributor Code of Conduct](CODE_OF_CONDUCT.md). By participating in this project you agree to abide by its terms.

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check the issue list as you might find out that you don't need to create one. When you are creating a bug report, please include as many details as possible:

- **Use a clear and descriptive title** that identifies the problem
- **Describe the exact steps which reproduce the problem** with as much detail as possible
- **Provide specific examples to demonstrate the steps** (include links, filenames, or code snippets)
- **Describe the behavior you observed** and what you expected to see instead
- **Include relevant screenshots or recordings** if applicable
- **Include your environment details** (OS, browser, Python version, etc.)

### Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. When creating an enhancement suggestion, please include:

- **Use a clear and descriptive title** that identifies the suggestion
- **Provide a step-by-step description of the suggested enhancement** with as many details as possible
- **Explain why this enhancement would be useful** to most NeighbourGood users
- **List some other platforms or applications where this feature exists** if applicable

### Pull Requests

- Fill in the required template (see `.github/pull_request_template.md`)
- Follow the Python and JavaScript coding standards (see below)
- Document new code with comments and docstrings
- End all files with a newline
- Avoid platform-specific code

## Development Setup

### Prerequisites

- Python 3.12+
- Node.js 18+
- PostgreSQL 16 (for production-like testing) or SQLite (for local dev)
- Git

### Local Development

1. Fork and clone the repository:
   ```bash
   git clone https://github.com/YOUR-USERNAME/neighbourgood.git
   cd neighbourgood
   ```

2. Set up the development environment:
   ```bash
   cp .env.example .env
   echo "NG_SECRET_KEY=$(openssl rand -hex 32)" >> .env
   ```

3. **Backend** — Set up in a separate terminal:
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   NG_DEBUG=true uvicorn app.main:app --reload --port 8300
   ```

4. **Frontend** — Set up in another terminal:
   ```bash
   cd frontend
   npm install
   npm run dev     # Vite dev server on :5173; /api proxy → :8300
   ```

5. **Database** — For Docker-based testing:
   ```bash
   docker compose up --build
   # Frontend: http://localhost:3800
   # Backend API: http://localhost:8300/docs
   ```

### Running Tests

```bash
# Backend tests (all 198+ tests)
cd backend
pytest

# Specific test file
pytest tests/test_auth.py -v

# With coverage
pytest --cov=app tests/
```

### Type Checking

```bash
cd frontend
npm run check        # svelte-check + TypeScript
```

## Coding Standards

### Python (Backend)

We follow [PEP 8](https://pep8.org/) with these guidelines:

- Use type hints for all function parameters and return types
- Maximum line length: 100 characters (except for long URLs)
- Use **SQLAlchemy 2.0 style**: `Mapped[type]` + `mapped_column()` (never `Column()`)
- All Pydantic schemas must include `max_length` on string fields
- All foreign key columns must have `index=True` for performance
- Use `response_model=` on all route decorators
- Import order: stdlib, third-party, local (separated by blank lines)

**Example:**
```python
from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column

class Resource(Base):
    __tablename__ = "resources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    community_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("communities.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

### TypeScript/Svelte (Frontend)

- Use TypeScript — no bare `.js` files in routes
- Use CSS custom properties for theming — never hardcode hex colors
- Prefer `const` over `let` over `var`
- Use kebab-case for CSS classes
- Use camelCase for JavaScript variables and functions
- Maximum line length: 100 characters
- Use the `api()` wrapper from `$lib/api` for all fetch calls

**Example:**
```typescript
import { api } from '$lib/api';
import type { Resource } from '$lib/types';

let resources: Resource[] = [];

async function loadResources() {
  resources = await api<Resource[]>('/resources', { auth: true });
}
```

## Git Workflow

1. Create a feature branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Commit with clear, descriptive messages (present tense, explain *why*):
   ```bash
   git commit -m "Add skill context to messages for better conversation context"
   ```

3. Push to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```

4. Create a Pull Request with a clear title and description

### Commit Message Guidelines

- Use present tense: "Add feature" not "Added feature"
- Use imperative mood: "Move cursor to..." not "Moves cursor to..."
- Limit first line to 50 characters
- Reference issues and PRs liberally after the first line
- Example:
  ```
  Add reputation rebalancing for clearer tier progression

  - Updated point allocations for different activities
  - Adjusted tier breakpoints to reflect engagement
  - Added /users/me/reputation endpoint for current user

  Fixes #50
  ```

## Documentation

- Keep README.md up to date with major changes
- Update CHANGELOG.md for all user-facing changes
- Add docstrings to new functions (follow existing patterns)
- Update docs/api.md if adding new routes
- Keep CLAUDE.md updated with new conventions or processes

## Security

Please report security vulnerabilities to **security@neighbourgood.community** instead of the issue tracker. See [SECURITY.md](SECURITY.md) for details.

## Additional Notes

### Project Structure

Refer to `CLAUDE.md` for:
- Full repository structure and file organization
- Model naming conventions and patterns
- Schema validation rules
- Backend service organization
- Frontend store and routing patterns

### Questions?

- Check existing issues and PRs for similar questions
- Read CLAUDE.md for comprehensive developer documentation
- Ask in discussions or open an issue to start a conversation

## Recognition

Contributors will be recognized in:
- The CHANGELOG.md for significant contributions
- GitHub's contributors page
- NeighbourGood community updates

Thank you for contributing! 🎉
