
import ast
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from ollama import chat

MODEL = "qwen2.5-coder:1.5b"
MAX_ITERATIONS = 5

PROJECT_DIR = Path(__file__).resolve().parent
CODE_FILE = PROJECT_DIR / "buggy_code.py"
TEST_FILE = PROJECT_DIR / "test_buggy_code.py"

BACKUP_DIR = PROJECT_DIR / "backups"
LOG_DIR = PROJECT_DIR / "logs"


def run_tests():
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(TEST_FILE)],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0, result.stdout + result.stderr

    except subprocess.TimeoutExpired:
        return False, "Tests timed out after 30 seconds."


def fix_code(code, error):
    response = chat(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a Python debugging assistant. "
                    "Fix the provided code so it passes the tests. "
                    "Return only complete valid Python code. "
                    "Do not include markdown or explanations."
                )
            },
            {
                "role": "user",
                "content": (
                    f"Code:\n{code}\n\n"
                    f"Test errors:\n{error}\n\n"
                    "Return the corrected complete code."
                )
            }
        ]
    )

    corrected = response.message.content.strip()

    if corrected.startswith("```"):
        corrected = corrected.split("\n", 1)[1]
        corrected = corrected.rsplit("```", 1)[0].strip()

    return corrected


def save_log(log_file, history):
    log_file.write_text(
        json.dumps(history, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def main():
    BACKUP_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    backup_file = BACKUP_DIR / f"buggy_code_{timestamp}.py"
    log_file = LOG_DIR / f"run_{timestamp}.json"

    shutil.copy2(CODE_FILE, backup_file)

    print(f"Backup created: {backup_file.name}")

    history = []

    for iteration in range(1, MAX_ITERATIONS + 1):
        print(f"\n--- Iteration {iteration} ---")

        success, errors = run_tests()

        if success:
            print("SUCCESS: All tests passed!")
            save_log(log_file, history)
            return

        print("Tests failed. Asking LLM for a fix...")

        code = CODE_FILE.read_text(encoding="utf-8")

        try:
            corrected = fix_code(code, errors)
            ast.parse(corrected)

        except SyntaxError as e:
            print("Generated code has invalid syntax.")

            history.append({
                "iteration": iteration,
                "status": "syntax_error",
                "error": str(e)
            })

            save_log(log_file, history)
            continue

        except Exception as e:
            print(f"LLM error: {e}")
            break

        CODE_FILE.write_text(corrected, encoding="utf-8")

        history.append({
            "iteration": iteration,
            "status": "fix_applied",
            "test_errors": errors,
            "original_code": code,
            "corrected_code": corrected
        })

        save_log(log_file, history)

    success, errors = run_tests()

    if success:
        print("\nSUCCESS: All tests passed!")
        save_log(log_file, history)
        return

    print("\nFAILED: Restoring original code.")

    shutil.copy2(backup_file, CODE_FILE)

    history.append({
        "status": "rollback",
        "reason": "Tests did not pass"
    })

    save_log(log_file, history)

    print("Original code restored.")


if __name__ == "__main__":
    main()
