import asyncio, json, sys
from pathlib import Path
from playwright.async_api import async_playwright

payload = json.loads(sys.stdin.read())
out = Path(payload['out'])

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        limit = asyncio.Semaphore(4)
        async def visit(a):
            async with limit:
                context = await browser.new_context(viewport={'width': 1440, 'height': 900})
                page = await context.new_page()
                await page.goto('http://localhost', wait_until='load')
                await page.locator('[data-testid=login-username]').fill(a['username'])
                await page.locator('[data-testid=login-password]').fill(a['password'])
                await page.locator('[data-testid=login-submit]').click()
                await page.locator('[data-testid=sidebar]').wait_for(timeout=30000)
                await page.goto('http://localhost/profile', wait_until='load')
                await page.locator('[data-testid=cell-username-value]').get_by_text(a['username'], exact=True).wait_for(timeout=30000)
                await page.screenshot(path=str(out / (a['username'] + '-profile.png')), full_page=True)
                await page.goto('http://localhost/docs', wait_until='load')
                await page.locator('[data-testid=documents-panel]').wait_for(timeout=30000)
                try:
                    await page.wait_for_function("() => {const n=document.querySelector('[data-testid=documents-panel] .panel-hd-left .badge'); return n && /^[0-9]+$/.test(n.innerText.trim())}", timeout=30000)
                except Exception:
                    await page.screenshot(path=str(out / (a['username'] + '-failure.png')), full_page=True)
                    raise
                rows = await page.locator('[data-testid=doc-row]').all_inner_texts()
                visible = '\n'.join(rows)
                tests = []
                for level, name in enumerate(payload['files'], 1):
                    expected = a['role'] == 'admin' or (a['department'] == payload['source_department'] and {'staff': 1, 'manager': 2, 'auditor': 3}[a['role']] >= level)
                    tests.append({'case': a['username'] + '/browser-catalog/' + str(level), 'actual': name in visible, 'expected': expected, 'ok': (name in visible) == expected})
                await page.screenshot(path=str(out / (a['username'] + '-docs.png')), full_page=True)
                if (a['role'] == 'auditor' and a['department'] == payload['source_department']) or (a['role'] == 'staff' and a['department'].endswith('_1')):
                    name = payload['files'][0] if a['role'] == 'staff' else a['username'] + '-denied.md'
                    fixture = out / name
                    fixture.write_text('# 未授权上传样例\n仅用于本轮技术检查。', 'utf8')
                    async with page.expect_response(lambda r: '/api/v1/upload' in r.url and r.request.method == 'POST', timeout=30000) as response:
                        await page.locator('[data-testid=document-upload-input]').set_input_files(str(fixture))
                    r = await response.value
                    await page.locator('.upload-item.error').wait_for(timeout=15000)
                    tests.append({'case': a['username'] + '/browser-upload-denied', 'actual': r.status, 'expected': 403, 'ok': r.status == 403})
                    await page.screenshot(path=str(out / (a['username'] + '-upload-denied.png')), full_page=True)
                await context.close()
                return tests
        gathered = await asyncio.gather(*(visit(a) for a in payload['accounts']))
        await browser.close()
        result = [c for group in gathered for c in group]
        (out / 'browser.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
        print(json.dumps({'browser_accounts': len(gathered), 'failed': sum(not c['ok'] for c in result)}), flush=True)
        return 1 if any(not c['ok'] for c in result) else 0

sys.exit(asyncio.run(main()))
