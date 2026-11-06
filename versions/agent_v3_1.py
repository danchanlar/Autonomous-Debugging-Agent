"""Reconstructed Version 3.1: functional approximation, not original historical source.
Progressive debugging loop.
"""
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
MAX_ITERATIONS = 4
MAX_RETRIES = 1
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


def choose_target(code, failures, history):
    functions = get_functions(code)
    candidates = [name.removeprefix('test_') for name in sorted(failures)
                  if name.removeprefix('test_') in functions]
    if not candidates:
        return None
    # Prioritize the least attempted directly failing function.
    return min(candidates, key=lambda n: sum(h['target'] == n for h in history))


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


def propose(code, target, test_file, baseline, feedback):
    functions = get_functions(code)
    target_source = ast.get_source_segment(code, functions[target])
    dep_source = '\n\n'.join(ast.get_source_segment(code, functions[n])
                            for n in dependencies(code, target)) or 'None'
    tests = relevant_tests(test_file, code, target)
    prompt = (
        f'TARGET FUNCTION:\n{target_source}\n\n'
        f'FUNCTIONS CALLED BY TARGET (READ ONLY):\n{dep_source}\n\n'
        f'RELEVANT TESTS:\n{tests}\n\n'
        f'CURRENT TEST FAILURES:\n{baseline["output"]}\n\n'
        f'FEEDBACK FROM PREVIOUS REJECTED PATCHES:\n{feedback or "None"}\n\n'
        f'Fix the root cause in {target} only. Derive the expected output from the tests. '
        'For arithmetic, verify the expression with the failing input. '
        'For recursion, check the base case and recursive arguments. '
        'Return one complete corrected function, with no explanation.'
    )
    response = chat(model=MODEL, messages=[
        {'role': 'system', 'content': (
            'You fix Python bugs using tests as specifications. '
            'Never return the unchanged target function. '
            'Never change dependency functions, tests, or signatures. '
            'Return ONLY one complete corrected function definition, no markdown.'
        )},
        {'role': 'user', 'content': prompt}
    ], options={'temperature': 0.3})
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
    data = {'version': '3.1', 'model': MODEL, 'experiment': test_name,
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
            target = choose_target(original, before['failures'], history)
            if target is None:
                data['status'] = 'error'
                data['final_errors'] = before['output']
                print('No matching top-level function found.')
                break
            print(f'\nIteration {iteration}/{MAX_ITERATIONS} | Target: {target}')
            feedback = '\n'.join(
                f"{a.get('feedback', '')}; proposal: {a.get('proposed_code', '')}"
                for h in history if h['target'] == target
                for a in h['attempts']
            )[-3000:]
            attempts = []
            accepted = False
            for retry in range(1, MAX_RETRIES + 1):
                print(f'  Patch attempt {retry}/{MAX_RETRIES}')
                proposed = ''
                attempt = {'retry': retry, 'proposed_code': '', 'status': 'rejected'}
                try:
                    proposed = propose(original, target, test_file, before, feedback)
                    attempt['proposed_code'] = proposed
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
                feedback += (f'\nRejected/previous patch:\n{proposed}\n'
                             f'Result: {attempt["feedback"]}\n')
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
