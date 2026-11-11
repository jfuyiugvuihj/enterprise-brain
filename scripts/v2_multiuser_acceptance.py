import argparse, concurrent.futures, hashlib, json, os, secrets, subprocess, sys, time
from pathlib import Path
from urllib.parse import quote
import requests

REPO = Path.cwd()
def env_key(path, key):
    for line in Path(path).read_text('utf8').splitlines():
        if line.startswith(key + '='):
            return line.split('=', 1)[1].strip().strip('\"').strip("'")
    raise RuntimeError('Missing configured key: ' + key)
BASE = 'http://localhost/api/v1'
parser = argparse.ArgumentParser(description='20 temporary accounts: real API and optional browser verification; never a human pilot.')
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--browser', action='store_true')
args = parser.parse_args()
OUT = args.out
OUT.mkdir(parents=True, exist_ok=True)
prefix = 'v2check_' + time.strftime('%H%M%S') + secrets.token_hex(2)
accounts, files, checks = [], [], []
completed = False
root = requests.Session()
login = root.post(BASE + '/login', json={'username': env_key('deploy/.env.server', 'AUTH_USERNAME'), 'password': env_key('deploy/.env.server', 'DEMO_ADMIN_PASSWORD')}, timeout=30)
login.raise_for_status()
root.headers['Authorization'] = 'Bearer ' + login.json()['token']

def check(name, actual, expected):
    checks.append({'case': name, 'actual': actual, 'expected': expected, 'ok': actual == expected})
    print(json.dumps(checks[-1], ensure_ascii=False), flush=True)

def upload(session, filename, text, level):
    return session.post(BASE + '/upload', files={'file': (filename, text.encode('utf8'), 'text/markdown')}, data={'classification': level}, timeout=120)

try:
    for dept in range(5):
        for role in ('staff', 'manager', 'auditor', 'admin'):
            name = prefix + '_' + str(dept) + '_' + role
            password = secrets.token_urlsafe(24)
            department = prefix + '_dept_' + str(dept)
            r = root.post(BASE + '/users', json={'username': name, 'password': password, 'role': role, 'department': department}, timeout=30)
            r.raise_for_status()
            session = requests.Session()
            r = session.post(BASE + '/login', json={'username': name, 'password': password}, timeout=30)
            r.raise_for_status()
            session.headers['Authorization'] = 'Bearer ' + r.json()['token']
            accounts.append({'username': name, 'password': password, 'role': role, 'department': department, 'session': session})
    source = next(a for a in accounts if a['role'] == 'admin' and a['department'].endswith('_0'))
    for level in (1, 2, 3):
        name = prefix + '_level_' + str(level) + '.md'
        body = '# 技术验证样例\n仅用于权限自动检查，不是公司制度。\n校验标识：' + prefix + '_secret_' + str(level)
        r = upload(source['session'], name, body, level)
        r.raise_for_status()
        files.append(name)
        check('upload-level-' + str(level), r.status_code, 200)
    def read_account(a):
        session = a['session']
        rows = session.get(BASE + '/documents/catalog', timeout=60)
        rows.raise_for_status()
        names = {r['filename'] for r in rows.json()['documents']}
        result = []
        for level, name in enumerate(files, 1):
            allowed = a['role'] == 'admin' or (a['department'] == source['department'] and {'staff': 1, 'manager': 2, 'auditor': 3}[a['role']] >= level)
            result.append((a['username'] + '/catalog/' + str(level), name in names, allowed))
            for endpoint in ('preview', 'versions', 'file'):
                r = session.get(BASE + '/documents/' + quote(name) + '/' + endpoint, timeout=60)
                permitted = allowed and (endpoint != 'file' or a['role'] != 'staff')
                result.append((a['username'] + '/' + endpoint + '/' + str(level), r.status_code, 200 if permitted else 403))
        r = session.get(BASE + '/profile', timeout=30)
        result.append((a['username'] + '/profile', r.status_code, 200))
        return result
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        for result in pool.map(read_account, accounts):
            for item in result:
                check(*item)
    name = files[0]
    before = root.get(BASE + '/documents/' + quote(name) + '/file', timeout=30).content
    attacker = next(a for a in accounts if a['role'] == 'staff' and a['department'].endswith('_1'))
    r = upload(attacker['session'], name, '# 非授权替换\n' + prefix + '_overwritten', 1)
    check('cross-department-same-name-upload', r.status_code, 403)
    after = root.get(BASE + '/documents/' + quote(name) + '/file', timeout=30).content
    check('original-bytes-preserved', hashlib.sha256(after).hexdigest(), hashlib.sha256(before).hexdigest())
    auditor = next(a for a in accounts if a['role'] == 'auditor')
    audit_file = prefix + '_auditor_upload.md'
    r = upload(auditor['session'], audit_file, '# 审计员不应上传\n本轮专用样例。', 1)
    if r.status_code == 200:
        files.append(audit_file)
    check('auditor-upload-denied', r.status_code, 403)
    r = upload(source['session'], files[0], before.decode('utf8') + '\n允许的更新版本。', 1)
    check('authorized-update-allowed', r.status_code, 200)
    r = source['session'].get(BASE + '/documents/' + quote(files[0]) + '/versions', timeout=30)
    check('authorized-version-history', len(r.json()['versions']), 2)
    if args.browser:
        payload = {'out': str(OUT), 'source_department': source['department'], 'files': files[:3], 'accounts': [{k: a[k] for k in ('username', 'password', 'role', 'department')} for a in accounts]}
        proc = subprocess.run(['uv', 'run', '--no-project', '--with', 'playwright==1.63.0', '--with', 'pillow', 'python', str(Path(__file__).with_name('v2_multiuser_browser.py'))], input=json.dumps(payload), text=True, encoding='utf8', capture_output=True, timeout=240)
        print(proc.stdout, flush=True)
        if proc.returncode:
            print(proc.stderr[-2000:], flush=True)
        check('twenty-real-browser-logins-and-catalogs', proc.returncode, 0)
    completed = True
finally:
    cleanup = []
    # Include only this run's unique names, including a browser upload that unexpectedly succeeded.
    catalog = root.get(BASE + '/documents/catalog', timeout=60)
    catalog.raise_for_status()
    files = sorted(set(files) | {r['filename'] for r in catalog.json()['documents'] if r['filename'].startswith(prefix + '_')})
    for name in files:
        r = root.delete(BASE + '/documents/' + quote(name), timeout=120)
        cleanup.append({'file': name, 'status': r.status_code})
    roster = root.get(BASE + '/users', timeout=30)
    roster.raise_for_status()
    for a in roster.json()['users']:
        if a['username'].startswith(prefix + '_'):
            r = root.delete(BASE + '/users/' + str(a['id']), timeout=30)
            cleanup.append({'account': a['username'], 'status': r.status_code})
    report = {'started_prefix': prefix, 'kind': 'automated-test-accounts-not-human-pilot', 'completed': completed, 'accounts': len(accounts), 'departments': 5, 'checks': checks, 'cleanup': cleanup, 'failed': sum(not c['ok'] for c in checks)}
    (OUT / 'reading.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps({'accounts': len(accounts), 'failed': report['failed'], 'cleanup_failed': [c for c in cleanup if c['status'] != 200], 'out': str(OUT)}, ensure_ascii=False), flush=True)
sys.exit(1 if report['failed'] or any(c['status'] != 200 for c in cleanup) else 0)
