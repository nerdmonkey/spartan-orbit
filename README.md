<p align="center"><img src="docs/ssf_banner.png" alt="Social Card of Spartan"></p>

<h1 align="center">Orbit — Spartan for Azure</h1>

<p align="center">
  <a href="https://github.com/nerdmonkey/spartan-orbit/actions/workflows/lint.yml"><img src="https://github.com/nerdmonkey/spartan-orbit/actions/workflows/lint.yml/badge.svg" alt="Lint"></a>
  <a href="https://github.com/nerdmonkey/spartan-orbit/actions/workflows/tests.yml"><img src="https://github.com/nerdmonkey/spartan-orbit/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
  <a href="https://github.com/nerdmonkey/spartan-orbit/actions/workflows/security.yml"><img src="https://github.com/nerdmonkey/spartan-orbit/actions/workflows/security.yml/badge.svg" alt="Security"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+">
</p>

## About

Orbit is the Azure variant of the Spartan Serverless Framework. Built on the Spartan framework principles, it leverages Azure Functions' Python Programming Model V2 with decorators for clean, maintainable code and seamless Azure integration.

Orbit is versatile and can be used to efficiently develop:

- HTTP-triggered APIs
- Event Grid-triggered, event-driven workloads
- Small or medium-sized ETL pipelines
- Agentic AI (coming soon)

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Testing](#testing)
- [Changelog](#changelog)
- [Contributing](#contributing)
- [Security Vulnerabilities](#security-vulnerabilities)
- [Credits](#credits)
- [License](#license)

## Features

| **Feature Category**           | **Status**                   | **Details**                                                  |
| ------------------------------ | ---------------------------- | ------------------------------------------------------------ |
| **Azure Functions**            | ✅ Excellent                  | Event Grid triggers, HTTP triggers, event-driven functions   |
| **Pydantic Integration**       | ✅ Full Support               | Validation, serialization, EmailStr, type safety             |
| **Architecture Patterns**      | ✅ Robust                     | Service pattern, clean separation of concerns                |
| **Testing Framework**          | ✅ Fully Integrated           | pytest, mocking, coverage tools                              |
| **Code Quality Tools**         | ✅ Complete                   | Black, isort, flake8, mypy, bandit, pre-commit               |
| **Development Workflow**       | ✅ Streamlined                | Poetry, Tox, environment support                             |
| **Cloud-Native Features**      | ✅ Advanced                   | Event Grid, Key Vault, App Configuration, Storage            |
| **Observability & Monitoring** | ✅ Enterprise-Grade           | Azure Monitor, Application Insights, structured logging      |
| **Developer Experience**       | ✅ High                       | Docker, Azure Functions Core Tools, .env support             |
| **Security Best Practices**    | ✅ Strong                     | Hashing, input validation, managed identities                |
| **Scalability Features**       | ✅ Built-in                   | Auto-scaling, pagination, filtering                          |
| **Logging Support**            | ✅ Advanced                   | Factory logger types (file, stream, azure), structured output|
| **Azure Monitor Integration**  | ✅ Fully Integrated           | Application Insights, operation correlation, custom metrics  |
| **Structured Logs**            | ✅ JSON + Metadata            | PII redaction, function source, custom dimensions            |
| **Observability Hooks**        | ✅ Extensible                 | Factory patterns for loggers/tracers, sampling               |
| **Reusability**                | ✅ High                       | Abstract base classes, reusable modules                      |
| **Modular Architecture**       | ✅ Excellent                  | Factory design, reusable services/utilities                  |
| **Configuration Management**   | ✅ Centralized                | Pydantic + .env + environment-detection                      |
| **Multi-Cloud Ready**          | ✅ Extensible                 | Abstraction layers support AWS, Azure, local environments    |
| **Code Consistency**           | ✅ Consistent with minor gaps | Naming conventions, model structures, unified patterns       |

## Requirements

- Python 3.11+
- pip (or [Poetry](https://python-poetry.org/), which the project's tox environments use)
- [`python-spartan`](https://pypi.org/project/python-spartan/) CLI (`pip install python-spartan`)
- [Azure Functions Core Tools v4](https://docs.microsoft.com/azure/azure-functions/functions-run-local) — only needed for local runs and deployment
- [Azurite](https://learn.microsoft.com/azure/storage/common/storage-use-azurite) — local storage emulator required by `func start`
- [Azure CLI](https://learn.microsoft.com/cli/azure/) (`az`) — only needed for deploying to Azure

## Installation

Clone the repo:

```bash
git clone https://github.com/nerdmonkey/spartan-orbit.git
cd spartan-orbit
```

Set up your environment:

<details>
<summary><strong>▶️ For Linux / macOS</strong></summary>

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

</details>

<details>
<summary><strong>🪟 For Windows PowerShell</strong></summary>

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

</details>

<details>
<summary><strong>🪟 For Windows CMD / DOS</strong></summary>

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements-dev.txt
```

</details>

Copy and configure environment variables:

```bash
cp .env.example .env  # Linux/macOS
```

```powershell
copy .env.example .env  # PowerShell
```

```cmd
copy .env.example .env  # CMD
```

## Usage

### Local Development

**Start Azure Functions locally:**

```bash
# Install Azure Functions Core Tools (if not already installed)
# macOS: brew tap azure/functions && brew install azure-functions-core-tools@4
# Windows: npm install -g azure-functions-core-tools@4
# Linux: See https://docs.microsoft.com/azure/azure-functions/functions-run-local

# Start Azurite storage emulator (required)
azurite --silent --location /tmp/azurite --debug /tmp/azurite/debug.log &

# Start all functions
func start
```

**Test functions with Event Grid:**

```bash
# Test queue function
curl -X POST http://localhost:7071/runtime/webhooks/EventGrid?functionName=queue \
  -H "Content-Type: application/json" \
  -H "aeg-event-type: Notification" \
  -d '[{
    "id": "test-1",
    "eventType": "Custom.Queue.MessageReceived",
    "subject": "queue/test",
    "eventTime": "2026-03-17T12:00:00Z",
    "data": {"operation": "enqueue_message", "message": "test"},
    "dataVersion": "1.0"
  }]'

# Test app_configuration function
curl -X POST http://localhost:7071/runtime/webhooks/EventGrid?functionName=app_configuration \
  -H "Content-Type: application/json" \
  -H "aeg-event-type: Notification" \
  -d '[{
    "id": "test-2",
    "eventType": "Custom.Config.Updated",
    "subject": "config/test",
    "eventTime": "2026-03-17T12:00:00Z",
    "data": {"operation": "get_configuration", "config_key": "test-key"},
    "dataVersion": "1.0"
  }]'

# Test key_vault function
curl -X POST http://localhost:7071/runtime/webhooks/EventGrid?functionName=key_vault \
  -H "Content-Type: application/json" \
  -H "aeg-event-type: Notification" \
  -d '[{
    "id": "test-3",
    "eventType": "Microsoft.KeyVault.SecretNewVersionCreated",
    "subject": "vault/secrets/test",
    "eventTime": "2026-03-17T12:00:00Z",
    "data": {"operation": "get_secret", "secret_name": "test-secret"},
    "dataVersion": "1.0"
  }]'
```

### Deployment to Azure

**Deploy with Azure CLI:**

```bash
# Login to Azure
az login

# Create resource group (if needed)
az group create --name spartan-orbit-rg --location eastus

# Create Function App
az functionapp create \
  --resource-group spartan-orbit-rg \
  --consumption-plan-location eastus \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --name spartan-orbit-micro \
  --storage-account <storage-account-name> \
  --os-type Linux

# Deploy functions
func azure functionapp publish spartan-orbit-micro
```

**Configure Event Grid subscriptions:**

```bash
# After deployment, create Event Grid subscriptions for your functions
# See Azure Functions Event Grid documentation for details
```

## Project Structure

```
spartan-orbit-micro/
├── app/
│   ├── exceptions/        # Custom exception types
│   ├── helpers/           # Utility helpers (logger, environment, context, tracer)
│   ├── requests/          # Request/input models
│   ├── responses/         # Response/output models
│   └── services/
│       ├── logging/       # Logger implementations (azure, file, stream, both)
│       └── tracing/       # Distributed tracing implementations
├── config/                # Configuration files
├── docs/                  # Documentation (banner, CONTRIBUTING, CODE_OF_CONDUCT)
├── scripts/               # Release tooling (CHANGELOG promotion, etc.)
├── tests/                 # Test suites
│   ├── unit/             # Unit tests
│   ├── integration/      # Integration tests
│   └── e2e/              # End-to-end tests
├── function_app.py       # Azure Functions app with all function definitions
├── host.json             # Azure Functions app configuration
├── local.settings.json   # Local development settings
├── .funcignore           # Files to exclude from deployment
├── requirements.txt      # Python dependencies
└── pyproject.toml        # Poetry configuration
```

### Azure Functions

All functions are defined in `function_app.py` using Python Programming Model V2 with decorators:

- **`queue`** - Event Grid trigger for Azure Queue Storage/Service Bus operations
- **`app_configuration`** - Event Grid trigger for Azure App Configuration management
- **`key_vault`** - Event Grid trigger for Azure Key Vault secret/key operations

## Testing

Run the unit test suite with coverage:

```bash
source .venv/bin/activate
python -m pytest tests/unit -q --cov=app --cov=config --cov-report=term-missing
```

Alternatively, via tox (installs dependencies through Poetry):

```bash
tox -e coverage
```

## Changelog

Please see [CHANGELOG](CHANGELOG.md) for more information on what has changed recently.

## Contributing

Please see [CONTRIBUTING](./docs/CONTRIBUTING.md) for details.

## Security Vulnerabilities

Please review [our security policy](../../security/policy) on how to report security vulnerabilities.

## Credits

- [Sydel Palinlin](https://github.com/nerdmonkey)
- [All Contributors](../../contributors)

## License

The MIT License (MIT). Please see [License File](LICENSE) for more information.
