
import ast
import difflib
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


def propose_fix(code, errors, history):
    previous_attempts = []

    for attempt in history:
        previous_attempts.append(
            f"Attempt {attempt['iteration']}:\n"
            f"Status: {attempt['status']}\n"
            f"Proposed code:\n{attempt['proposed_code']}\n"
            f"Feedback: {attempt['feedback']}"
        )

    memory = "\n\n".join(previous_attempts)

    response = chat(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a Python debugging assistant. "
                    "Fix the code using the test errors and previous feedback. "
                    "Do not repeat failed solutions. "
                    "Preserve the existing function names and interfaces. "
                    "Return only complete valid Python code. "
                    "No markdown or explanations."
                )
            },
            {
                "role": "user",
                "content": (
                    f"Current code:\n{code}\n\n"
                    f"Test errors:\n{errors}\n\n"
                    f"Previous attempts:\n{memory}\n\n"
                    "Return the complete corrected Python file."
                )
            }
        ]
    )

    corrected = response.message.content.strip()

    if corrected.startswith("```"):
        corrected = corrected.split("\n", 1)[1]
        corrected = corrected.rsplit("```", 1)[0].strip()

    return corrected


def validate_patch(original, proposed, previous_codes):
    if not proposed:
        return False, "Empty response"

    try:
        ast.parse(proposed)
    except SyntaxError as error:
        return False, f"Syntax error: {error}"

    if proposed.strip() == original.strip():
        return False, "No changes proposed"

    if proposed.strip() in previous_codes:
        return False, "Repeated previous solution"

    return True, "Patch accepted"


def show_diff(original, proposed):
    diff = difflib.unified_diff(
        original.splitlines(),
        proposed.splitlines(),
        fromfile="original",
        tofile="proposed",
        lineterm=""
    )

    return "\n".join(diff)


def save_log(log_file, data):
    log_file.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def main():
    BACKUP_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    backup_file = BACKUP_DIR / f"buggy_code_{timestamp}.py"
    log_file = LOG_DIR / f"run_{timestamp}.json"

    shutil.copy2(CODE_FILE, backup_file)

    print(f"Backup created: {backup_file.name}")

    history = []
    previous_codes = set()

    log_data = {
        "model": MODEL,
        "timestamp": timestamp,
        "max_iterations": MAX_ITERATIONS,
        "status": "running",
        "history": history
    }

    save_log(log_file, log_data)

    try:
        for iteration in range(1, MAX_ITERATIONS + 1):
            print(f"\n--- Iteration {iteration} ---")

            success, errors = run_tests()

            if success:
                log_data["status"] = "success"
                print("SUCCESS: All tests passed!")
                save_log(log_file, log_data)
                return

            print("Tests failed. Asking LLM for a fix...")

            original = CODE_FILE.read_text(encoding="utf-8")
            proposed = propose_fix(original, errors, history)

            valid, feedback = validate_patch(
                original, proposed, previous_codes
            )

            attempt = {
                "iteration": iteration,
                "status": "rejected" if not valid else "applied",
                "feedback": feedback,
                "test_errors": errors,
                "original_code": original,
                "proposed_code": proposed
            }

            if valid:
                diff = show_diff(original, proposed)

                print("\nProposed changes:")
                print(diff)

                CODE_FILE.write_text(proposed, encoding="utf-8")
                previous_codes.add(proposed.strip())

                attempt["diff"] = diff
                print("Patch applied.")
            else:
                print(f"Patch rejected: {feedback}")

            history.append(attempt)
            save_log(log_file, log_data)

        success, errors = run_tests()

        if success:
            log_data["status"] = "success"
            print("\nSUCCESS: All tests passed!")
            return

        log_data["status"] = "failed"
        log_data["final_errors"] = errors
        print("\nFAILED: Maximum iterations reached.")

    except Exception as error:
        log_data["status"] = "error"
        log_data["error"] = str(error)
        print(f"\nAgent error: {error}")

    finally:
        if log_data["status"] != "success":
            shutil.copy2(backup_file, CODE_FILE)
            log_data["rollback"] = True
            print("Original code restored.")
        else:
            log_data["rollback"] = False

        save_log(log_file, log_data)
        print(f"Log saved: {log_file.name}")


if __name__ == "__main__":
    main()