# Security Policy

## Supported Versions

We release patches for security vulnerabilities. Currently supported versions:

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take the security of Document Intelligence AI seriously. If you believe you have found a security vulnerability, please report it to us as described below.

### Please do NOT:
- Open a public GitHub issue
- Discuss the vulnerability publicly before it has been addressed

### Please DO:
- Email security@document-intelligence.ai with details
- Include steps to reproduce the vulnerability
- Allow us reasonable time to address the issue before public disclosure

### What to expect:
1. **Acknowledgment**: Within 48 hours of your report
2. **Initial Assessment**: Within 5 business days
3. **Regular Updates**: Every 5 business days until resolution
4. **Credit**: Security researchers who report valid vulnerabilities will be acknowledged (unless anonymity is requested)

## Security Measures

### Authentication & Authorization
- API key-based authentication with RBAC
- JWT tokens with short expiration times
- Principle of least privilege access controls

### Data Protection
- Encryption at rest using AES-256
- TLS 1.3 for all data in transit
- Secure key management using HashiCorp Vault
- PII detection and automatic redaction

### Infrastructure Security
- Container scanning in CI/CD pipeline
- Regular dependency updates via Dependabot
- Network isolation and firewall rules
- Intrusion detection and prevention systems

### Compliance
- SOC 2 Type II certified
- GDPR compliant data handling
- HIPAA ready architecture
- Regular third-party security audits

## Security Best Practices for Users

1. **API Keys**
   - Rotate API keys regularly (recommended: every 90 days)
   - Never commit API keys to version control
   - Use environment variables for key storage
   - Implement key scoping for minimal permissions

2. **Network Security**
   - Always use HTTPS endpoints
   - Implement IP allowlisting where possible
   - Use VPN or private connections for sensitive data

3. **Data Handling**
   - Minimize data retention periods
   - Implement data classification policies
   - Regular audit of access logs
   - Use field-level encryption for sensitive data

## Vulnerability Disclosure Timeline

- **0-30 days**: Issue verification and fix development
- **30-60 days**: Testing and staged rollout
- **60-90 days**: Full deployment and monitoring
- **90+ days**: Public disclosure (if applicable)

## Contact

Security Team: security@document-intelligence.ai
PGP Key: [Download Public Key](https://document-intelligence.ai/security.asc)