"""Exercise real category controls against an isolated local database."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from wsgiref.simple_server import make_server, WSGIRequestHandler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for key in ('TURSO_DATABASE_URL', 'TURSO_AUTH_TOKEN', 'VERCEL', 'RENDER'):
    os.environ.pop(key, None)
from playwright.sync_api import sync_playwright
from src.auth import create_session_token
from src.database import init_db, insert_jobs, get_jobs, update_job_status, set_user_setting
from src.server import create_app
from tests.test_video_editor import job


class Quiet(WSGIRequestHandler):
    def log_message(self, *args):
        pass


def main():
    output = Path(sys.argv[1]); output.mkdir(parents=True, exist_ok=True)
    checks = []
    with tempfile.TemporaryDirectory() as folder:
        db = str(Path(folder)/'isolated.db'); init_db(db)
        insert_jobs(db, [job(6), job(1, platform='Indeed', title='Gaming Video Editor'), job(0, category='Web/Software Dev', title='Software Developer')])
        update_job_status(db, next(j['id'] for j in get_jobs(db) if j['platform']=='Indeed'), 'saved', notes='Keep this note')
        set_user_setting(db, 'target_stack', 'React')
        set_user_setting(db, 'filter_skills_only', '1')
        server = make_server('127.0.0.1', 0, create_app(db), handler_class=Quiet)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, executable_path='C:/Users/PC/AppData/Local/Chromium/Application/chrome.exe')
                page = browser.new_page(); errors=[]
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.add_init_script('localStorage.setItem("job_accel_session_token",'+json.dumps(create_session_token('admin','admin'))+')')
                page.goto(f'http://127.0.0.1:{server.server_port}'); page.wait_for_load_state('networkidle')
                page.locator('#filter-by-skills-btn').click()
                page.wait_for_function('filterBySkillsOnly === true')
                for width in (1380, 390):
                    page.set_viewport_size({'width':width,'height':900})
                    chips=page.locator('#role-group button'); assert chips.count()==8
                    for chip in chips.all():
                        chip.click(); assert chip.get_attribute('aria-pressed')=='true'
                    video=page.get_by_role('button', name='Video Editor', exact=True)
                    video.focus(); page.keyboard.press('Enter')
                    try:
                        page.wait_for_function('currentRole === "Video Editor" && jobsList.length === 1', timeout=7000)
                    except Exception:
                        print('DB rows', [{k:r.get(k) for k in ('id','title','status','role_category','date_posted')} for r in get_jobs(db)], flush=True)
                        print('API', page.evaluate('async()=>await (await fetch("/api/jobs?role=Video%20Editor&status=new",{headers:{Authorization:"Bearer "+localStorage.getItem("job_accel_session_token")}})).json()'), flush=True)
                        print('Browser errors',errors,flush=True)
                        raise
                    assert page.locator('#role-filter-help').inner_text().find('7 days')>=0
                    page.locator('#platform-select').select_option('OnlineJobs.ph')
                    page.wait_for_function('jobsList.length===1 && jobsList[0].platform==="OnlineJobs.ph"')
                    page.locator('#platform-select').select_option('All')
                    page.locator('.status-tab[data-val="saved"]').click()
                    video.click()
                    page.wait_for_function('currentStatus==="saved" && currentRole==="Video Editor" && jobsList.length===1 && jobsList[0].platform==="Indeed"')
                    assert page.evaluate('jobsList[0].notes')=='Keep this note'
                    assert page.evaluate('generateTailoredPitch(jobsList[0]).includes("louisricafrente-studio")')
                    assert page.locator('#role-group').evaluate('(e)=>e.getBoundingClientRect().right<=innerWidth')
                    page.screenshot(path=str(output/f'video-editor-category-{width}.png'))
                    checks.append({'width':width,'category_chips':chips.count(),'video_filter':'pass','saved_notes':'pass','keyboard':'pass','site_filter':'pass','skills_filter':'pass'})
                    page.locator('.status-tab[data-val="new"]').click()
                assert not errors, errors
                browser.close()
        finally:
            server.shutdown()
    (output/'video-editor-ui-2026-10-30.json').write_text(json.dumps(checks,indent=2))
    print(json.dumps(checks))


if __name__=='__main__':
    main()
