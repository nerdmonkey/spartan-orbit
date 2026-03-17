<p align="center"><img src="docs/ssf_banner.png" alt="Orbit - Serverless Framework for Azure"></p>

# Orbit

## About
Orbit is a modern serverless framework for building scalable, event-driven Python applications on **Azure Functions**. Built on the Spartan framework principles, it leverages Python Programming Model V2 with decorators for clean, maintainable code and seamless Azure integration.

---

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

---

## Installation & Usage

1. **Install the Spartan CLI tool:**
```bash
pip install python-spartan
```

2. **Try it out:**
```bash
spartan --help
```

3. **Set up your environment:**

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

4. **Copy and configure environment variables:**

```bash
cp .env.example .env  # Linux/macOS
```

```powershell
copy .env.example .env  # PowerShell
```

```cmd
copy .env.example .env  # CMD
```

---

## Running the Application

### Local Development

**Start Azure Functions Locally:**
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

**Test Functions with Event Grid:**
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

**Configure Event Grid Subscriptions:**
```bash
# After deployment, create Event Grid subscriptions for your functions
# See Azure Functions Event Grid documentation for details
```

---

## Project Structure

```
spartan-orbit-micro/
├── app/
│   ├── helpers/           # Utility helpers (logger, environment, context, tracer)
│   └── services/
│       └── logging/       # Logger implementations (azure, file, stream, both)
├── config/                # Configuration files
├── docs/                  # Documentation
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

---

## Testing

Run the test suite using `pytest`:

```bash
pytest -vv
```

---

## Changelog

Please see [CHANGELOG](CHANGELOG.md) for recent updates.

---

## Contributing

Please see [CONTRIBUTING](./docs/CONTRIBUTING.md) for details on contributing.

---

## Security Vulnerabilities

Please review [our security policy](../../security/policy) for how to report vulnerabilities.

---

## Credits

- [Sydel Palinlin](https://github.com/nerdmonkey)
- [All Contributors](../../contributors)

---

## License

The MIT License (MIT). Please see the [License File](LICENSE) for more information.
