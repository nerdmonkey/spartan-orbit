<p align="center"><img src="docs/ssf_banner.png" alt="Lazaro - Based on Spartan Serverless Framework"></p>

# Lazaro

## About
Lazaro is a structured serverless framework for building scalable Python applications on **Azure**. Based on the Spartan Serverless Framework, it focuses exclusively on Azure with consistent structure and first-class integrations for serverless functions, event-driven workloads, and cloud-native applications.

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

**Test Logger:**
```bash
python main.py
```

**Run Azure Functions Locally:**
```bash
# Install Azure Functions Core Tools first (if not already installed)
# macOS: brew tap azure/functions && brew install azure-functions-core-tools@4

# Start all functions locally
func start
```

### Deployment to Azure

**Quick Deploy:**
```bash
./deploy-azure.sh
```

**Manual Deploy:**
```bash
# Login to Azure
az login

# Deploy functions
func azure functionapp publish spartan-orbit-micro --python
```

See [AZURE_DEPLOYMENT.md](AZURE_DEPLOYMENT.md) for detailed deployment instructions.

---

## Project Structure

```
spartan-orbit-micro/
├── app/
│   ├── helpers/           # Utility helpers (logger, environment, context, tracer)
│   └── services/          # Business logic services
│       └── logging/       # Logger implementations (azure, file, stream, both)
├── config/                # Configuration files
├── docs/                  # Documentation
├── functions/             # Azure Functions
│   ├── queue/
│   ├── app_configuration/
│   └── key_vault/
├── tests/                 # Test suites
├── host.json             # Azure Functions app configuration
├── local.settings.json   # Local development settings
├── main.py               # Local testing script
└── requirements.txt      # Python dependencies
```

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
