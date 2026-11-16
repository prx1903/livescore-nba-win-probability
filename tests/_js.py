"""Helpers for the tests that run parts of the demo page (docs/index.html) in Node."""
import json, os, re, shutil, subprocess, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, 'docs', 'index.html')


def page_source():
    return open(PAGE, encoding='utf-8').read()


def js_function(src, name):
    """Source text of `function name(...) {...}`, found by brace matching.
    Only for functions without unbalanced braces in strings (true for the functions used in the tests)."""
    start = src.index('function ' + name + '(')
    depth = 0
    for k in range(src.index('{', start), len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[start:k + 1]
    raise ValueError('end of function not found: ' + name)


def js_const(src, name):
    """Source text of a one-line `const name=...;` statement."""
    m = re.search(r'^const ' + re.escape(name) + r'=.*$', src, flags=re.M)
    if not m:
        raise ValueError('const not found: ' + name)
    return m.group(0)


def json_const(src, name):
    """Value of a one-line `const name=<JSON>;` statement."""
    return json.loads(js_const(src, name).split('=', 1)[1].rstrip().rstrip(';'))


def node():
    return shutil.which('node')


def run_node(code, payload):
    """Runs `code` in Node with `payload` available as the global INPUT; returns the JSON that the code prints."""
    with tempfile.TemporaryDirectory() as d:
        js, inp = os.path.join(d, 'run.js'), os.path.join(d, 'input.json')
        json.dump(payload, open(inp, 'w', encoding='utf-8'))
        open(js, 'w', encoding='utf-8').write(
            "const INPUT=JSON.parse(require('fs').readFileSync(process.argv[2],'utf8'));\n" + code)
        r = subprocess.run([node(), js, inp], capture_output=True, text=True, encoding='utf-8')
        if r.returncode:
            raise RuntimeError('node failed:\n' + r.stderr[-2000:])
        return json.loads(r.stdout)


def run_tests(namespace):
    """Runs every test_* function of a test file and prints one line per test. A test may return 'skip: reason'.
    All tests run even if one fails; the exit code is 1 if any test failed."""
    import sys
    n_ok = n_fail = 0
    for name, f in list(namespace.items()):
        if name.startswith('test_') and callable(f):
            try:
                res = f()
            except Exception as e:                                  # report and go on with the next test
                n_fail += 1
                print('FAIL', name, '-', type(e).__name__, str(e).strip().replace('\n', ' | ')[:300])
                continue
            n_ok += 1
            print('skip' if isinstance(res, str) and res.startswith('skip') else 'ok', name, '' if res is None else res)
    print(f'{n_ok} tests passed' + (f', {n_fail} FAILED' if n_fail else ''))
    if n_fail:
        sys.exit(1)
