import ast
import difflib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from ollama import chat

MODEL = 'qwen2.5-coder:1.5b'
MAX_ITERATIONS = 7
MAX_RETRIES = 3
PROJECT_DIR = Path(__file__).resolve().parent
EXPERIMENTS = {
    'test1': 'test1_Multiple_logical_errors',
    'test2': 'test2_Edge_cases',
    'test3': 'test3_Recursion',
    'test4': 'test4_Multiple_interacting_functions',
    'test5': 'test5_Algorithmic_bug',
    'test6': 'test6_Stateful_class',
}


def run_tests(test_file, experiment_dir):
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pytest', '-q', '--tb=line', '--no-header', str(test_file)],
            cwd=experiment_dir, capture_output=True, text=True, timeout=30
        )
        output = result.stdout + result.stderr
        failures = set(re.findall(r'FAILED\s+\S+::(test_\w+)', output))
        return {'success': result.returncode == 0, 'returncode': result.returncode,
                'failures': failures, 'output': output}
    except subprocess.TimeoutExpired:
        return {'success': False, 'returncode': -1, 'failures': set(),
                'output': 'Tests timed out after 30 seconds.'}


def get_functions(code):
    return {n.name: n for n in ast.parse(code).body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def dependencies(code, target):
    functions = get_functions(code)
    if target not in functions:
        return []
    result = []
    for node in ast.walk(functions[target]):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id
            if name in functions and name != target and name not in result:
                result.append(name)
    return result


def relevant_tests(test_file, code, target):
    source = test_file.read_text(encoding='utf-8')
    names = {target, *dependencies(code, target)}
    selected = []
    for node in ast.parse(source).body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not node.name.startswith('test_'):
            continue
        referenced = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        if referenced & names or node.name == f'test_{target}':
            selected.append(ast.get_source_segment(source, node))
    return '\n\n'.join(x for x in selected if x)


def choose_target(code, failures, history, test_file):
    functions = get_functions(code)
    test_tree = ast.parse(test_file.read_text(encoding='utf-8'))
    candidates = set()

    for node in test_tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in failures:
            continue

        # Preserve the original name-based matching when available.
        named_target = node.name.removeprefix('test_')
        if named_target in functions:
            candidates.add(named_target)

        # Also recognize calls inside tests with descriptive names,
        # e.g. test_first_element() -> binary_search().
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                if child.func.id in functions:
                    candidates.add(child.func.id)

    if not candidates:
        return None

    # Repair leaf functions first, before their callers.
    return min(candidates, key=lambda n: (
        len(dependencies(code, n)),
        sum(h['target'] == n for h in history), n))


def failure_evidence(test_file, code, target, baseline):
    tests = relevant_tests(test_file, code, target)
    direct = []
    for node in ast.parse(test_file.read_text(encoding='utf-8')).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == f'test_{target}':
            direct.append(ast.get_source_segment(test_file.read_text(encoding='utf-8'), node))
    lines = [line.strip() for line in baseline['output'].splitlines()
             if line.lstrip().startswith(('E   ', 'FAILED '))]
    return ("DIRECT TARGET TESTS (primary specification):\n" +
            ('\n'.join(direct) if direct else tests) +
            "\n\nFAILURE EVIDENCE:\n" + '\n'.join(lines[:18]))


def clean_response(text):
    text = text.strip()
    match = re.search(r'```(?:python)?\s*\n(.*?)```', text, re.I | re.S)
    return match.group(1).strip() if match else text


def build_patch(original, proposed, target):
    functions = get_functions(original)
    if target not in functions:
        raise ValueError('Target function not found')
    old = functions[target]
    proposed_tree = ast.parse(proposed)
    if len(proposed_tree.body) != 1 or not isinstance(proposed_tree.body[0], type(old)):
        raise ValueError('Return exactly one function definition')
    new = proposed_tree.body[0]
    if new.name != target:
        raise ValueError('Wrong function name')
    if ast.dump(new.args, include_attributes=False) != ast.dump(old.args, include_attributes=False):
        raise ValueError('Function signature changed')
    if ast.dump(new, include_attributes=False) == ast.dump(old, include_attributes=False):
        raise ValueError('No logical changes proposed')
    if old.decorator_list or new.decorator_list:
        if ast.dump(ast.Module(body=old.decorator_list, type_ignores=[]), include_attributes=False) != ast.dump(
                ast.Module(body=new.decorator_list, type_ignores=[]), include_attributes=False):
            raise ValueError('Decorators changed')
    lines = original.splitlines(keepends=True)
    start = min([old.lineno] + [d.lineno for d in old.decorator_list]) - 1
    patched = ''.join(lines[:start]) + proposed.strip() + '\n' + ''.join(lines[old.end_lineno:])
    ast.parse(patched)
    return patched


def evaluate(before, after):
    if after['returncode'] not in (0, 1):
        return False, 'Test execution/collection error'
    if after['success']:
        return True, 'All tests passed'
    if not before['failures'] or not after['failures']:
        return False, 'Unable to compare failing tests'
    regressions = after['failures'] - before['failures']
    if regressions:
        return False, f'Regressions: {sorted(regressions)}'
    if len(after['failures']) < len(before['failures']):
        return True, 'Fewer failing tests'
    return False, 'No reduction in failing tests'


def propose(code, target, test_file, baseline, feedback, retry):
    functions = get_functions(code)
    target_source = ast.get_source_segment(code, functions[target])
    dep_source = '\n\n'.join(ast.get_source_segment(code, functions[n])
                            for n in dependencies(code, target)) or 'None'
    evidence = failure_evidence(test_file, code, target, baseline)
    prompt = (
        f'Fix ONLY this function: {target}\n\n'
        f'CURRENT FUNCTION:\n{target_source}\n\n'
        f'CALLED FUNCTIONS (do not edit):\n{dep_source}\n\n'
        f'{evidence}\n\n'
        f'PREVIOUS REJECTED ATTEMPTS (do not repeat):\n{feedback[-2200:] or "None"}\n\n'
        'First infer the expected behavior from the direct unit tests. '
        'Pay attention to boundary cases, arithmetic operators and slicing. '
        'A patch identical to the original will be rejected. '
        'Do not change any other function. Output ONLY the complete corrected Python function.'
    )
    response = chat(model=MODEL, messages=[
        {'role': 'system', 'content': (
            'You are a Python bug fixer. Tests define expected behavior. '
            'Identify the incorrect expression and change it. '
            'Never return unchanged code or a previously rejected patch. '
            'Return exactly one complete function, no explanation or markdown.'
        )},
        {'role': 'user', 'content': prompt}
    ], options={'temperature': [0.15, 0.45, 0.7][(retry - 1) % 3]})
    return clean_response(response.message.content)


def save_log(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in EXPERIMENTS:
        print('Usage: python agent.py test1')
        sys.exit(1)
    test_name = sys.argv[1]
    directory = PROJECT_DIR / 'tests' / EXPERIMENTS[test_name]
    code_file = directory / 'buggy_code.py'
    test_file = directory / 'test_buggy_code.py'
    if not code_file.is_file() or not test_file.is_file():
        print('Experiment files not found.')
        sys.exit(1)
    backup_dir = PROJECT_DIR / 'backups' / test_name
    log_dir = PROJECT_DIR / 'logs' / test_name
    backup_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup = backup_dir / f'buggy_code_{stamp}.py'
    log_file = log_dir / f'run_{stamp}.json'
    shutil.copy2(code_file, backup)
    history = []
    data = {'version': '3.6', 'model': MODEL, 'experiment': test_name,
            'max_iterations': MAX_ITERATIONS, 'max_retries': MAX_RETRIES,
            'status': 'running', 'history': history}
    save_log(log_file, data)
    print(f'Experiment: {test_name} | Model: {MODEL}')
    try:
        for iteration in range(1, MAX_ITERATIONS + 1):
            before = run_tests(test_file, directory)
            if before['success']:
                data['status'] = 'success'
                print('SUCCESS: All tests passed!')
                break
            if before['returncode'] not in (0, 1) or not before['failures']:
                data['status'] = 'error'
                data['final_errors'] = before['output']
                print('Cannot identify test failures.')
                break
            original = code_file.read_text(encoding='utf-8')
            target = choose_target(original, before['failures'], history, test_file)
            if target is None:
                data['status'] = 'error'
                data['final_errors'] = before['output']
                print('No matching top-level function found.')
                break
            print(f'\nIteration {iteration}/{MAX_ITERATIONS} | Target: {target}')
            feedback = '\n'.join(
                f"{a.get('feedback', '')}; proposal: {a.get('proposed_code', '')}"
                for h in history if h['target'] == target for a in h['attempts']
            )[-2200:]
            seen = {a.get('proposed_code', '').strip()
                    for h in history for a in h['attempts'] if h['target'] == target}
            attempts = []
            accepted = False
            for retry in range(1, MAX_RETRIES + 1):
                print(f'  Patch attempt {retry}/{MAX_RETRIES}')
                proposed = ''
                attempt = {'retry': retry, 'proposed_code': '', 'status': 'rejected'}
                try:
                    proposed = propose(original, target, test_file, before, feedback, retry)
                    attempt['proposed_code'] = proposed
                    if proposed.strip() in seen:
                        raise ValueError('Repeated previously rejected proposal')
                    seen.add(proposed.strip())
                    patched = build_patch(original, proposed, target)
                    code_file.write_text(patched, encoding='utf-8')
                    after = run_tests(test_file, directory)
                    ok, reason = evaluate(before, after)
                    attempt['post_patch_errors'] = after['output']
                    attempt['diff'] = '\n'.join(difflib.unified_diff(
                        original.splitlines(), patched.splitlines(),
                        fromfile='original', tofile='patched', lineterm=''))
                    if ok:
                        attempt['status'] = 'applied'
                        attempt['feedback'] = reason
                        accepted = True
                        print(f'  Accepted: {reason}')
                        if after['success']:
                            data['status'] = 'success'
                    else:
                        attempt['feedback'] = reason
                        code_file.write_text(original, encoding='utf-8')
                        print(f'  Rejected: {reason}')
                except (SyntaxError, ValueError) as error:
                    attempt['feedback'] = str(error)
                    code_file.write_text(original, encoding='utf-8')
                    print(f'  Rejected: {error}')
                except Exception:
                    code_file.write_text(original, encoding='utf-8')
                    raise
                attempts.append(attempt)
                feedback += (f'\nRejected patch:\n{proposed}\n'
                             f'Result: {attempt["feedback"]}\n')
                feedback = feedback[-2200:]
                if accepted:
                    break
            history.append({'iteration': iteration, 'target': target,
                            'dependencies': dependencies(original, target),
                            'status': 'applied' if accepted else 'rejected',
                            'attempts': attempts})
            save_log(log_file, data)
            if data['status'] == 'success':
                print('\nSUCCESS: All tests passed!')
                break
        if data['status'] == 'running':
            final = run_tests(test_file, directory)
            data['status'] = 'success' if final['success'] else 'failed'
            data['final_errors'] = final['output']
            if final['success']:
                print('SUCCESS: All tests passed!')
            else:
                print(final['output'])
                print('FAILED: Maximum iterations reached.')
    except Exception as error:
        data['status'] = 'error'
        data['error'] = str(error)
        print(f'Agent error: {error}')
    finally:
        if data['status'] != 'success':
            shutil.copy2(backup, code_file)
            data['rollback'] = True
            print('Original code restored.')
        else:
            data['rollback'] = False
        save_log(log_file, data)
        print(f'Log saved: {log_file.name}')


if __name__ == '__main__':
    main()
