# Development Standards

These guidelines define coding conventions and best practices for BimAtlas development.

## General Principles

- Write clear, maintainable code with descriptive names
- Follow existing patterns in the codebase
- Keep functions and components focused on single responsibilities
- Document complex logic with comments

## Python (Backend)

### Code Style

- Follow PEP 8 with line length of 100 characters
- Use `ruff` for linting (already configured in pyproject.toml)
- Import order: stdlib → third-party → local

### Type Hints

- Use type hints for all function signatures
- Use `Any` sparingly; prefer explicit types

### Error Handling

- Use custom exceptions for domain-specific errors
- Log errors with appropriate context
- Never expose sensitive information in error messages

### Testing

- Write unit tests for all new functionality
- Use pytest fixtures for common setup
- Aim for meaningful test coverage over 100% coverage

## Svelte/TypeScript (Frontend)

### Svelte 5 Best Practices

- Use runes (`$state`, `$derived`, `$effect`) for reactivity
- Use `Snippet` for slot-based extensibility patterns
- Co-locate styles with components when practical

### TypeScript

- Enable strict mode
- Avoid `any`; use proper types or generics
- Export types from dedicated `.ts` files

### CSS/Styling

- Use design tokens from `product/style.md`
- Prefer semantic class names
- Keep specificity low

## API Design

- Use GraphQL for data operations (already configured)
- REST endpoints only for specific use cases (file uploads, SSE streams)
- Version APIs when making breaking changes

## Security

- Never commit secrets or credentials
- Use environment variables for sensitive configuration
- Validate all user input
- Use parameterized queries for database operations

## Performance

- Lazy load routes and heavy components
- Use appropriate indexes for database queries
- Minimize bundle size for frontend
