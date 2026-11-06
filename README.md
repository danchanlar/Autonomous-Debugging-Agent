# Autonomous Debugging Agent

A **local, test-guided Python debugging agent** built around an iterative **agentic loop**. It runs a `pytest` suite, uses **Qwen2.5-Coder 1.5B** through **Ollama** to propose code repairs, checks candidate patches, and repeats until the tests pass or the attempt budget is exhausted.

The project was developed on Windows 10 with 8 GB RAM, without paid LLM APIs or Docker. It is a **research proof of concept**, not a production-ready or sandboxed repair system.

## How it works

```text
                  Python source + pytest suite
                              |
                         Run pytest
                              |
                   +----------+----------+
                   |                     |
                All pass             Tests fail
                   |                     |
                Success          Diagnose failures
                                         |
                             Select function or method
                                         |
                              Ask local LLM for patch
                                         |
                            Validate structure and tests
                                         |
                                +--------+--------+
                                |                 |
                             Accept             Reject
                                |                 |
                            Retest         Record feedback
                                |                 |
                                +--------+--------+
                                         |
                          Retry while budget remains
                                         |
                               If unsuccessful:
                              restore original code
                              and save execution log
```

The controller, rather than the language model alone, determines whether a patch can be accepted. Checks evolved during development to include AST-based validation, method/function preservation, duplicate and no-op detection, and regression checking. The exact checks depend on the agent version.

## Features

- **Offline-capable local inference** after downloading the Ollama model; no paid API key required.
- **Automated feedback** from `pytest` failures and, in later versions, relevant test source code.
- **Targeted repairs** of individual functions and (from V3.7) class methods.
- **Patch validation** and rejection of invalid, ineffective, or regression-inducing changes.
- **Run-local feedback history** to inform subsequent repair attempts. This is *not* persistent learning across runs.
- **Backups, rollback, unified diffs, and JSON logs** to make repair attempts inspectable.

## Requirements

- Python **3.11** (documented experimental environment: Python 3.11.2)
- [Ollama](https://ollama.com/) and model `qwen2.5-coder:1.5b`
- Python packages: `ollama` and `pytest` (documented experiment checks used pytest 9.2.0)
- Windows 10 was used for development; commands below use PowerShell/Windows paths.

**Security:** There is **no execution sandbox**. The agent runs tests and potentially modified Python code on the host. Use only trusted, controlled examples; do not run it against untrusted repositories.

## Installation (Windows)

Install Ollama and Python 3.11, then run:

```powershell
ollama pull qwen2.5-coder:1.5b
ollama list

# From the project directory:
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install ollama pytest
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pytest --version
```

You do **not** need to activate the virtual environment. Explicitly using `.venv\Scripts\python.exe` also avoids a documented setup issue in which system Python 3.14 did not have `pytest` installed. Ensure Ollama is running and the requested model is available before starting an experiment.

## Project layout

The exact repository layout may vary between development snapshots. The documented experiment-based layout is conceptually:

```text
debugging-agent/
├── agent.py                 # Active agent implementation
├── tests/
│   ├── test1_.../           # Multiple logical errors
│   ├── test2_.../           # Edge cases
│   ├── test3_.../           # Recursion
│   ├── test4_.../           # Interacting functions
│   ├── test5_.../           # Binary search
│   └── test6_.../           # Stateful class
├── backups/                 # Timestamped source backups (if configured)
├── logs/                    # JSON execution logs (if configured)
└── README.md
```

Earlier milestones used `agent_v1.py`, `agent_v2.py`, or `agent_v3.py`, and a simple top-level `buggy_code.py`/`test_buggy_code.py` example. The main experiment commands below assume your checkout has the active `agent.py` with `test1`–`test6` selectors.

## Running the six experiments

From the project root, run one experiment at a time:

```powershell
.\.venv\Scripts\python.exe agent.py test1
.\.venv\Scripts\python.exe agent.py test2
.\.venv\Scripts\python.exe agent.py test3
.\.venv\Scripts\python.exe agent.py test4
.\.venv\Scripts\python.exe agent.py test5
.\.venv\Scripts\python.exe agent.py test6
```

To inspect the original failures before repair, use `pytest` on the experiment's test directory or test file, for example:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test6_Stateful_class
```

**Important:** Start every trial from its *original intentionally buggy source*. A successful repair modifies that source, while an unsuccessful run may restore it automatically. Check the terminal output and JSON log to confirm the final state. Do not assume a previous successful run is still a valid baseline for another evaluation.

## Development history

| Version | Main development |
| --- | --- |
| **V1** | Basic test → LLM proposal → apply → retest loop. |
| **V2** | Backup, rollback, syntax validation, JSON logging. |
| **V3** | Feedback within a run, rejection of unchanged/duplicate proposals, diffs and expanded logs. |
| **V3.1** | Shorter pytest error output and revised prompting. |
| **V3.2** | Function-by-function repairs and stricter AST/output checks. |
| **V3.3** | Test-guided repair prompts, improved target selection and regression checks. |
| **V3.4** | Dependency-aware analysis and prompting. |
| **V3.5** | Multiple patch retries within an iteration and rejection-specific feedback. |
| **V3.6** | Structured diagnosis, adaptive retry behavior and up to seven iterations with three attempts each in the recorded configuration. |
| **V3.7** | Class-aware AST targeting and method-level patching (`BankAccount`). |

These are **development milestones**, not results from a controlled comparison in which every version was evaluated on every experiment.

## Experimental results

The following summarizes **documented runs**, often using different agent revisions. Results for failed runs may refer to the best intermediate state **before rollback**.

| Experiment | Task | Best documented outcome | Version |
| --- | --- | --- | --- |
| **1 — Logical errors** | Fix average, maximum, and parity functions | Success; three affected functions repaired | V3 |
| **2 — Edge cases** | Handle empty input, zero divisor, clamp bounds | **3/3 tests passed** | V3 |
| **3 — Recursion** | Fix factorial, Fibonacci, recursive sum | **3/3 passed** on the second V3.3 run; earlier runs failed | V3.3 |
| **4 — Interacting functions** | Correct subtotal, discount, and tax calculations | **Failed**; best recorded intermediate result **2/3** before rollback | V3.3–V3.6 investigated |
| **5 — Binary search** | Correct search-bound updates | **6/6 passed**, first patch attempt | Modified V3.6 |
| **6 — Stateful class** | Correct `BankAccount.deposit()` and `withdraw()` | **5/5 passed**, three iterations | V3.7 |

**How to interpret 5/6:** At least one successful completion was recorded for **five of the six selected scenarios**, across different versions and attempts. **83.3% is historical scenario coverage, not a measured repair success rate for V3.7** or a general prediction of performance.

### What we learned

**Experiment 1:** Three independent logic errors were corrected, but an early successful patch also added unnecessary `test_*` functions into the implementation file. This exposed the need to constrain edits, not merely check that tests pass.

**Experiment 2:** The agent corrected handling of empty lists, division by zero, and out-of-range values. Explicit edge-case tests gave effective repair feedback for these examples.

**Experiment 3:** Recursion was much harder. V3, V3.1, and V3.2 reached only 1/3 tests in documented runs. V3.3 first reached 2/3 and then 3/3 on a repeat run, demonstrating both the potential of test-guided prompts and outcome variability.

**Experiment 4:** Repairing functions with dependencies remained unresolved. The model repeatedly proposed incorrect or unchanged code even after dependency-aware prompts and more retries. The controller's rollback preserved the original code after unsuccessful runs.

**Experiment 5:** A modified V3.6 implementation repaired a binary-search direction error on its first proposed patch. Because the agent script was modified for this experiment, its result is not strictly comparable to other V3.6 runs.

**Experiment 6:** V3.6 initially could not select methods inside a class (`No matching top-level function found`). V3.7 added class-method support, repaired the account operations, and rejected a patch that would have caused regressions before eventually passing all five tests.

## Limitations

- **No sandbox:** Python code and tests execute directly on the host.
- **Test-suite dependence:** Passing existing assertions does not prove correctness on unseen inputs.
- **Small, selected study:** Six synthetic scenarios do not establish general reliability.
- **Non-identical evaluation conditions:** Different versions, retries, and (for Test 5) a modified script were used.
- **Model behavior:** The 1.5B model can repeat unsuccessful patches, return invalid output, or struggle with interacting functions.
- **Scope:** The documented agent is not a general multi-file repository repair tool or a persistent-learning system.

## Next steps

1. Freeze a single agent version and evaluate it repeatedly on the same six tasks **and unseen tasks**, resetting the source for each run.
2. Record full-suite success, elapsed time, iteration and patch-attempt counts, rejected proposals, regressions, and rollback frequency.
3. Improve diagnosis and target selection for interacting functions.
4. Add properly restricted execution isolation **before** experimenting on untrusted code.
5. Explore multi-file repair and (separately evaluated) persistent feedback memory.

## Documentation

The project technical report covers the architecture, development environment, version evolution, individual experiment failures and code fixes, selected screenshots, comparative findings, and evaluation limitations. Add the report PDF and/or LaTeX source to the repository and link them here once their final paths are known.

## References

- [Qwen2.5-Coder Technical Report](https://arxiv.org/abs/2409.12186)
- [Ollama documentation](https://docs.ollama.com/)
- [pytest documentation](https://docs.pytest.org/en/stable/)
- [Python `ast` documentation](https://docs.python.org/3/library/ast.html)
- [SWE-bench: Can Language Models Resolve Real-World GitHub Issues?](https://arxiv.org/abs/2310.06770)

---

*This repository documents an evolving prototype and selected experimental observations. All published results should be interpreted in light of their stated experimental conditions.*
