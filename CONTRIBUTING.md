# Contributing to Document Intelligence AI

We appreciate your interest in contributing to Document Intelligence AI. This document provides guidelines and instructions for contributing to the project.

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Getting Started](#getting-started)
3. [Development Process](#development-process)
4. [Contribution Guidelines](#contribution-guidelines)
5. [Commit Standards](#commit-standards)
6. [Testing Requirements](#testing-requirements)
7. [Documentation](#documentation)
8. [Review Process](#review-process)

## Code of Conduct

Please read and follow our [Code of Conduct](CODE_OF_CONDUCT.md) to maintain a welcoming and inclusive community.

## Getting Started

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- Git
- Pre-commit hooks

### Development Setup

1. Fork the repository and clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/document-intelligence-ai.git
   cd document-intelligence-ai
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install development dependencies:
   ```bash
   pip install -r requirements-dev.txt
   pre-commit install
   ```

4. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. Run tests to verify setup:
   ```bash
   pytest tests/ -v
   ```

## Development Process

### Branch Naming Convention

- `feature/` - New features (e.g., `feature/add-pdf-ocr`)
- `fix/` - Bug fixes (e.g., `fix/memory-leak-in-search`)
- `docs/` - Documentation updates (e.g., `docs/update-api-guide`)
- `refactor/` - Code refactoring (e.g., `refactor/optimize-embeddings`)
- `test/` - Test additions or fixes (e.g., `test/add-integration-tests`)

### Workflow

1. Create a new branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes following our coding standards

3. Run tests and linting:
   ```bash
   pytest tests/ -v
   black src/ tests/
   isort src/ tests/
   flake8 src/ tests/
   mypy src/
   ```

4. Commit your changes using conventional commits

5. Push to your fork and create a pull request

## Contribution Guidelines

### Code Style

- Follow PEP 8 guidelines
- Use Black for code formatting (configured in `pyproject.toml`)
- Use isort for import ordering
- Maximum line length: 88 characters
- Use type hints for all function signatures

### Docstring Standards

We follow Google-style docstrings:

```python
def process_document(file_path: str, chunk_size: int = 1000) -> List[Document]:
    """Process a document and return chunks.
    
    Args:
        file_path: Path to the document file.
        chunk_size: Size of each chunk in characters.
        
    Returns:
        List of Document objects containing chunks.
        
    Raises:
        FileNotFoundError: If the file doesn't exist.
        ValueError: If chunk_size is invalid.
    """
```

### Testing Standards

- Write tests for all new functionality
- Maintain or improve code coverage (minimum 85%)
- Use pytest fixtures for reusable test components
- Include both unit and integration tests
- Mock external dependencies appropriately

### Performance Considerations

- Profile code for performance-critical paths
- Avoid premature optimization
- Document any performance trade-offs
- Include benchmarks for significant changes

## Commit Standards

We follow the Conventional Commits specification:

### Format
```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `test`: Test additions or corrections
- `build`: Build system changes
- `ci`: CI/CD changes
- `chore`: Maintenance tasks

### Examples
```
feat(api): add batch document upload endpoint

- Implement multipart upload for multiple files
- Add progress tracking via websockets
- Limit batch size to 50 files

Closes #123
```

## Testing Requirements

### Unit Tests
- Test individual functions and classes
- Mock external dependencies
- Aim for 100% coverage of business logic

### Integration Tests
- Test API endpoints end-to-end
- Test database operations
- Verify external service integrations

### Performance Tests
- Benchmark critical operations
- Test under load conditions
- Monitor memory usage

### Running Tests
```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=src --cov-report=html

# Run specific test file
pytest tests/test_api.py -v

# Run tests matching pattern
pytest tests/ -k "search" -v
```

## Documentation

### Code Documentation
- Add docstrings to all public functions and classes
- Update relevant documentation when changing functionality
- Include usage examples in docstrings

### API Documentation
- Update OpenAPI schemas for API changes
- Add request/response examples
- Document error cases and status codes

### Architecture Documentation
- Update ADRs (Architecture Decision Records) for significant changes
- Keep system diagrams current
- Document integration patterns

## Review Process

### Pull Request Requirements

1. **Description**: Clear explanation of changes and motivation
2. **Testing**: All tests pass and coverage maintained
3. **Documentation**: Updated as needed
4. **Code Quality**: Passes all linting checks
5. **Review**: At least one approval from maintainers

### Review Checklist

- [ ] Code follows project style guidelines
- [ ] Tests are included and passing
- [ ] Documentation is updated
- [ ] No security vulnerabilities introduced
- [ ] Performance impact is acceptable
- [ ] Breaking changes are documented

### Response Times

- Initial review: Within 2 business days
- Follow-up reviews: Within 1 business day
- Merge decision: Within 5 business days

## Questions and Support

- GitHub Issues: Bug reports and feature requests
- Discussions: General questions and ideas
- Email: contributors@document-intelligence.ai

Thank you for contributing to Document Intelligence AI!