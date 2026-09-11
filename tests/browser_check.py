"""Run UI acceptance checks in installed Chrome with an isolated server/database."""
import tempfile
import threading
from pathlib import Path
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright, expect
from app import create_app

ROOT=Path(__file__).resolve().parents[1]
ARTIFACTS=ROOT/'artifacts'
ARTIFACTS.mkdir(exist_ok=True)


def main():
    with tempfile.TemporaryDirectory() as folder:
        app=create_app(dict(TESTING=True, DATABASE_URL='sqlite:///'+str(Path(folder)/'browser.db'),
                            ADMIN_PASSWORD='browser-test', PARKING_MODE='simulation'))
        server=make_server('127.0.0.1',5051,app,threaded=True)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(channel='chrome',headless=True)
                page=browser.new_page(viewport={'width':1440,'height':1050},device_scale_factor=1)
                errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.on('console',lambda message:errors.append(message.text) if message.type=='error' and 'Content Security Policy' in message.text else None)
                page.goto('http://127.0.0.1:5051')
                page.locator('#password').fill('browser-test')
                page.locator('#login-form button').click()
                expect(page.locator('#app')).to_be_visible()
                expect(page.locator('#free-count')).to_have_text('04')
                page.locator('[data-gate="entry"]').click()
                expect(page.locator('#gate-state')).to_have_text('Thanh chắn đang mở')
                page.locator('[data-slot="A1"]').click()
                expect(page.locator('#occupied-count')).to_have_text('01')
                page.locator('[data-gate="close"]').click()
                expect(page.locator('#gate-state')).to_have_text('Thanh chắn đang đóng')
                page.locator('[data-slot="A3"]').click()
                expect(page.locator('#free-count')).to_have_text('02')
                page.screenshot(path=str(ARTIFACTS/'dashboard-desktop.png'),full_page=True)
                for slot in ('A2','A4'):
                    page.locator(f'[data-slot="{slot}"]').click()
                    expect(page.locator(f'[data-slot="{slot}"]')).to_have_class('slot occupied')
                expect(page.locator('#free-count')).to_have_text('00')
                expect(page.locator('[data-gate="entry"]')).to_be_disabled()
                expect(page.locator('[data-gate="exit"]')).to_be_enabled()
                page.locator('[data-slot="A1"]').click()
                expect(page.locator('#free-count')).to_have_text('01')
                page.locator('.nav-item[data-view="history"]').click()
                expect(page.locator('#history-events tbody tr')).not_to_have_count(0)
                page.locator('#filter-kind').select_option('occupied')
                expect(page.locator('#history-events tbody tr')).to_have_count(4)
                with page.expect_download() as download:
                    page.locator('#export').click()
                download.value.save_as(str(ARTIFACTS/'browser-export.csv'))
                page.locator('.nav-item[data-view="analytics"]').click()
                expect(page.locator('.chart-group')).to_have_count(7)
                assert page.locator('.bar').last.evaluate('(el)=>getComputedStyle(el).height')!='0px'
                page.locator('.nav-item[data-view="settings"]').click()
                page.locator('#mode-select').select_option('hardware')
                page.wait_for_timeout(2200)
                expect(page.locator('#mode-select')).to_have_value('hardware')
                page.locator('#save-mode').click()
                expect(page.locator('#mode-dialog')).to_be_visible()
                page.locator('#confirm-mode').click()
                expect(page.locator('#connection')).to_have_text('ESP32 mất kết nối')
                page.locator('.nav-item[data-view="overview"]').click()
                expect(page.locator('.slot.unknown')).to_have_count(4)
                expect(page.locator('[data-gate="entry"]')).to_be_disabled()
                page.locator('.nav-item[data-view="settings"]').click()
                page.locator('#mode-select').select_option('simulation')
                page.locator('#save-mode').click();page.locator('#confirm-mode').click()
                expect(page.locator('#connection')).to_have_text('Chế độ mô phỏng')
                page.locator('.nav-item[data-view="overview"]').click()
                page.set_viewport_size({'width':390,'height':844})
                expect(page.locator('#free-count')).to_have_text('04')
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile horizontal overflow'
                page.screenshot(path=str(ARTIFACTS/'dashboard-mobile.png'),full_page=True)
                page.locator('.nav-item[data-view="history"]').click()
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'History overflow'
                page.locator('#mobile-logout').click()
                expect(page.locator('#login')).to_be_visible()
                assert not errors,errors
                browser.close()
                print('PASS: login, slot updates, barrier, full lot, history, CSV, charts, modes, offline, responsive, logout; no JS/CSP errors.')
        finally:
            server.shutdown();thread.join();server.server_close()
            app.extensions['parking_engine'].dispose()


if __name__=='__main__':main()
