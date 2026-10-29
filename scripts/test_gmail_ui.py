"""Headless browser checks with a temporary inbox and no external account access."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from unittest.mock import patch
from wsgiref.simple_server import make_server, WSGIRequestHandler, WSGIServer
from socketserver import ThreadingMixIn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from src.database import init_db
from src.server import create_app
from src.auth import create_session_token
from src import gmail_hub as hub


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass


class ThreadedServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def main():
    for key in ('TURSO_DATABASE_URL', 'TURSO_AUTH_TOKEN', 'VERCEL'):
        os.environ.pop(key, None)
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / 'gmail-hub-ui'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        db = str(Path(folder) / 'gmail_ui_test.db')
        init_db(db)
        hub.init_hub(db)
        for i in range(45):
            hub.ingest(db, dict(id=format(i+1, 'x'), thread_id='aaa', sender='Acme Recruiting <hr@acme.example>',
                subject=f'Acme developer update {i}' if i else '<img src=x onerror="window.hubXss=true">',
                body_text='Your application update.\n\nOriginal plain text with <script> tags, not executable HTML.',
                received_at=time.time()-i*60, trusted=False), [])
        with patch('src.aggregator.get_default_connectors', return_value=[]):
            app = create_app(db)
        server = make_server('127.0.0.1', 0, app, server_class=ThreadedServer, handler_class=QuietHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                executable = os.environ.get('GMAIL_TEST_BROWSER')
                browser = playwright.chromium.launch(headless=True, **({'executable_path': executable} if executable else {}))
                context = browser.new_context(viewport={'width':1440,'height':1000}, reduced_motion='reduce')
                context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(f'http://127.0.0.1:{server.server_port}/') else route.abort())
                context.add_cookies([dict(name='job_accel_session', value=create_session_token('admin','ui-test'),
                                         url=f'http://127.0.0.1:{server.server_port}')])
                page = context.new_page()
                errors = []
                inflight = set()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('request', lambda request: inflight.add(request.url))
                page.on('requestfinished', lambda request: inflight.discard(request.url))
                page.on('requestfailed', lambda request: inflight.discard(request.url))
                page.goto(f'http://127.0.0.1:{server.server_port}/?view=gmail')
                try:
                    page.wait_for_load_state('networkidle', timeout=5000)
                except Exception:
                    page.screenshot(path=str(output/'gmail-hub-load-failure.png'), full_page=True)
                    print(json.dumps({'browser_errors': errors, 'pending_requests': list(inflight)}))
                    if errors:
                        raise
                page.locator('#gmail-hub-container').wait_for(state='visible')
                page.locator('.gh-message').first.wait_for()
                assert page.locator('.gh-message').count() == 40
                page.locator('#gmail-load-more').click()
                page.wait_for_function('document.querySelectorAll(".gh-message").length===45')
                page.locator('[data-open="1"]').click()
                page.locator('#gmail-modal-subject').wait_for()
                page.wait_for_function('document.querySelector(".gh-body")?.textContent.includes("Original plain text")')
                assert not page.evaluate('Boolean(window.hubXss)')
                page.wait_for_function('document.querySelector("[data-read=\\"1\\"]")?.textContent.includes("unread")')
                page.locator('#gmail-viewer-unread').click()
                page.locator('#gmail-message-modal').wait_for(state='hidden')
                page.select_option('#gmail-read-filter', 'read')
                page.wait_for_function('document.querySelector("#gmail-result-count").textContent.includes("0 of 0")')
                page.select_option('#gmail-read-filter', '')
                page.locator('.gh-message').first.wait_for()
                page.locator('.gh-legend summary').click()
                page.screenshot(path=str(output/'gmail-hub-desktop.png'))
                page.set_viewport_size({'width':375,'height':812})
                page.wait_for_timeout(250)
                assert page.locator('#gmail-hub-container').evaluate('(el)=>el.scrollWidth<=el.clientWidth+1')
                print(json.dumps({'mobile_overflow': page.evaluate('''()=>[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1 && getComputedStyle(e).position!=='fixed').slice(0,8).map(e=>({tag:e.tagName,id:e.id,cl:e.className,right:e.getBoundingClientRect().right}))''')}))
                page.screenshot(path=str(output/'gmail-hub-mobile.png'))
                page.locator('.gh-subject').first.click()
                page.locator('.gh-body').wait_for()
                page.screenshot(path=str(output/'gmail-hub-reader-mobile.png'))
                page.keyboard.press('Escape')
                page.locator('#gmail-message-modal').wait_for(state='hidden')
                assert page.evaluate('document.activeElement.tagName') == 'BUTTON'
                assert not errors, errors
                browser.close()
                print(json.dumps({'ui':'passed','checks':['pagination','filters','auto-read','mark-unread','escaped-body','Gmail-link','mobile-layout','Escape-focus','no-console-errors'], 'screenshots':str(output)}))
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    main()
