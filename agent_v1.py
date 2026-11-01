
import subprocess
import sys
from pathlib import Path
from ollama import chat

MODEL = "qwen2.5-coder:1.5b"
MAX_ITERATIONS = 5

code_file = Path("buggy_code.py")
test_file = Path("test_buggy_code.py")


def run_tests():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(test_file)],
        capture_output=True,
        text=True,
        timeout=30
    )

    return result.returncode == 0, result.stdout + result.stderr


def fix_code(code, error):
    response = chat(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a Python debugging assistant. "
                    "Fix the provided code so it passes the tests. "
                    "Return only valid Python code. "
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


def main():
    for iteration in range(1, MAX_ITERATIONS + 1):
        print(f"\n--- Iteration {iteration} ---")

        success, errors = run_tests()

        if success:
            print("SUCCESS: All tests passed!")
            return

        print("Tests failed. Asking LLM for a fix...")

        code = code_file.read_text(encoding="utf-8")
        corrected_code = fix_code(code, errors)

        code_file.write_text(corrected_code, encoding="utf-8")

    success, errors = run_tests()

    if success:
        print("\nSUCCESS: All tests passed!")
    else:
        print("\nFAILED: Maximum iterations reached.")
        print(errors)


if __name__ == "__main__":
    main()
