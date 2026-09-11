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
3. **Create a descriptive feature branch**:
   ```bash
   git checkout -b feature/improved-raptor-pruning
   ```
4. **Make your changes with atomic, semantic commits**:
   ```bash
   git commit -m "feat(core): optimize earliest trip search in RAPTOR route traversal"
   ```
5. **Run test suite**:
   ```bash
   pytest gateway/test_main.py
   ```
6. **Push and open a Pull Request**:
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
- `ci:` CI/CD workflow updates

---

## 🧪 Testing Guidelines

Before opening a pull request, ensure all tests pass:
- **Python Gateway**: `pytest gateway/test_main.py`
- **GTFS Compiler**: `python telemetry/gtfs_compiler.py`
- **C++ Build**: `cmake -B build -S core && cmake --build build`
