# Contributing to TransitEngine 🚍

Thank you for your interest in contributing to **TransitEngine**! We welcome contributions from the community to make high-performance transit routing more accessible, fast, and feature-complete.

---

## 🧭 How to Contribute

### 1. Branching & Contribution Workflow
To ensure all contributions count towards your GitHub profile activity and history:
1. **Fork the repository** on GitHub.
2. **Clone your fork locally**:
   ```bash
   git clone https://github.com/<your-username>/transit-engine.git
   cd transit-engine
   ```
3. **Install development dependencies**:
   ```bash
   pip install -r requirements-dev.txt
   ```
4. **Create a descriptive feature branch**:
   ```bash
   git checkout -b feature/improved-raptor-pruning
   ```
5. **Make your changes with atomic, semantic commits**:
   ```bash
   git commit -m "feat(core): optimize earliest trip search in RAPTOR route traversal"
   ```
6. **Run linters and test suites**:
   ```bash
   flake8 gateway telemetry
   black --check gateway telemetry
   pytest --cov=gateway --cov=telemetry --cov-report=term-missing
   ```
7. **Push and open a Pull Request**:
   ```bash
   git push origin feature/improved-raptor-pruning
   ```

---

## 📝 Commit Message Conventions

We follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

- `feat:` A new feature or capability
- `fix:` A bug fix
- `docs:` Documentation updates
- `test:` Adding or refactoring tests
- `perf:` Performance improvements
- `refactor:` Code restructuring without functional changes
- `ci:` CI/CD workflow and tooling updates
- `chore:` Maintenance tasks and configuration

---

## 🧪 Testing & Code Quality Guidelines

Before opening a pull request, ensure all tests pass and linters succeed:
- **Run Full Test Suite with Coverage**:
  ```bash
  pytest --cov=gateway --cov=telemetry --cov-report=term-missing
  ```
- **Run Code Formatter & Linters**:
  ```bash
  black gateway telemetry
  flake8 gateway telemetry
  ```
- **GTFS Compiler Validation**:
  ```bash
  python telemetry/gtfs_compiler.py
  ```
- **C++ Build**:
  ```bash
  cmake -B build -S core -DCMAKE_BUILD_TYPE=Release
  cmake --build build --config Release
  ```
