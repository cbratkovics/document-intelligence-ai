# Project Structure

## Root Directory

The root directory contains only essential files following enterprise best practices:

```
document-intelligence-ai/
├── README.md              # Project overview and quick start
├── LICENSE                # MIT license
├── CHANGELOG.md          # Version history
├── SECURITY.md           # Security policy (GitHub standard)
├── requirements.txt      # Python dependencies entry point
├── requirements-*.txt    # Modular dependency management
├── pyproject.toml        # Python project configuration
└── .pre-commit-config.yaml  # Code quality automation
```

## Directory Organization

```
├── .github/              # GitHub-specific files
│   ├── workflows/        # CI/CD pipelines
│   ├── ISSUE_TEMPLATE/   # Issue templates
│   ├── CONTRIBUTING.md   # Contribution guidelines
│   └── CODE_OF_CONDUCT.md # Community standards
│
├── src/                  # Source code
│   ├── api/             # REST API implementation
│   ├── core/            # Core functionality
│   ├── rag/             # RAG implementation
│   ├── monitoring/      # Metrics and observability
│   └── utils/           # Utility functions
│
├── tests/               # Test suite
│   ├── test_*.py       # Test modules
│   └── conftest.py     # Test configuration
│
├── docs/                # Documentation
│   ├── api/            # API documentation
│   ├── architecture/   # System design
│   ├── deployment/     # Deployment guides
│   ├── adr/            # Architecture decisions
│   └── internal/       # Internal documentation
│
├── docker/              # Docker configuration
│   ├── Dockerfile      # Optimized multi-stage build
│   └── docker-compose.yml # Service orchestration
│
├── scripts/             # Utility scripts
│   ├── docker/         # Docker-related scripts
│   └── setup/          # Setup and initialization
│
└── data/               # Runtime data (gitignored)
    ├── uploads/        # Document uploads
    ├── models/         # ML model cache
    └── cache/          # Application cache
```

## Key Design Decisions

1. **Minimal Root**: Only essential files in root directory
2. **GitHub Standards**: Community files in `.github/`
3. **Modular Structure**: Clear separation of concerns
4. **Documentation First**: Comprehensive docs/ structure
5. **Docker Isolation**: All Docker files in docker/
6. **Script Organization**: Scripts categorized by purpose