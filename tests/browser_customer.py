"""Mobile customer flow, live admin sync, PWA offline behavior and location editor."""
import tempfile
import threading
from pathlib import Path
from werkzeug.serving import make_server, WSGIRequestHandler
from playwright.sync_api import sync_playwright, expect
from app import create_app

class Quiet(WSGIRequestHandler):
    def log_request(self,*args,**kwargs):pass

def main():
    artifacts=Path(__file__).resolve().parents[1]/'artifacts';artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        app=create_app(dict(TESTING=True,DATABASE_URL='sqlite:///'+str(Path(folder)/'ui.db'),ADMIN_PASSWORD='test-password',PARKING_MODE='simulation'))
        server=make_server('127.0.0.1',5052,app,threaded=True,request_handler=Quiet)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(channel='chrome',headless=True)
                admin_context=browser.new_context();admin=admin_context.new_page()
                admin.goto('http://127.0.0.1:5052/');admin.locator('#password').fill('test-password');admin.locator('#login-form button').click()
                expect(admin.locator('#free-count')).to_have_text('04')
                admin.locator('.nav-item[data-view="settings"]').click()
                form=admin.locator('#location-form')
                expect(form.locator('[name="name"]')).to_have_value('Bãi xe HAISMRTPak')
                form.locator('[name="name"]').fill('Bãi xe kiểm thử')
                form.locator('[name="address"]').fill('Địa chỉ mô phỏng để kiểm thử')
                form.locator('[name="latitude"]').fill('10.77');form.locator('[name="longitude"]').fill('106.69')
                form.locator('[type="submit"]').click()
                expect(admin.locator('#location-result')).to_contain_text('Đã lưu')
                context=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
                page=context.new_page();errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.on('console',lambda msg:errors.append(msg.text) if msg.type=='error' and 'Content Security Policy' in msg.text else None)
                page.goto('http://127.0.0.1:5052/driver/')
                expect(page.locator('#auth-submit')).to_be_enabled()
                page.screenshot(path=str(artifacts/'driver-login.png'),full_page=True)
                page.locator('#tab-register').click();page.locator('#name').fill('Minh Anh');page.locator('#username').fill('minhanh');page.locator('#email').fill('anh@example.com');page.locator('#password').fill('password-123');page.locator('#auth-submit').click()
                expect(page.locator('#home')).to_be_visible();expect(page.locator('#free-count')).to_have_text('4')
                expect(page.locator('#lot-name')).to_have_text('Bãi xe kiểm thử')
                expect(page.locator('#notice')).to_contain_text('tự cập nhật')
                expect(page.locator('#directions')).to_have_attribute('href','https://www.google.com/maps/dir/?api=1&destination=10.77%2C106.69&travelmode=driving')
                page.locator('[data-slot="A2"]').click();expect(page.locator('#slot-detail')).to_contain_text('A2: đang trống')
                admin.locator('.nav-item[data-view="overview"]').click()
                admin.locator('[data-slot="A2"]').click();expect(admin.locator('#occupied-count')).to_have_text('01')
                expect(page.locator('#free-count')).to_have_text('3',timeout=10000)
                expect(page.locator('#slot-detail')).to_contain_text('A2: đang có xe')
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.screenshot(path=str(artifacts/'driver-parking.png'),full_page=True)
                # Installed app assets must be cached, availability and identities must not.
                page.evaluate('navigator.serviceWorker.ready')
                page.wait_for_function('navigator.serviceWorker.controller !== null')
                cached=page.evaluate('async () => { const result=[]; for(const key of await caches.keys()){ const cache=await caches.open(key); result.push((await cache.keys()).map(r=>r.url)); } return result; }')
                assert not any('/api/' in url for urls in cached for url in urls)
                context.set_offline(True)
                expect(page.locator('#free-count')).to_have_text('—',timeout=10000)
                expect(page.locator('.slot.unknown')).to_have_count(4)
                page.reload();expect(page.locator('#auth')).to_be_visible()
                expect(page.locator('#auth-error')).to_contain_text('Không thể kết nối',timeout=10000)
                context.set_offline(False);page.locator('#retry-auth').click()
                expect(page.locator('#home')).to_be_visible();expect(page.locator('#free-count')).to_have_text('3')
                page.locator('#nav-account').click();expect(page.locator('#account-email')).to_have_text('anh@example.com')
                page.locator('#logout').click();expect(page.locator('#auth')).to_be_visible()
                page.locator('#tab-login').click();page.locator('#email').fill('anh@example.com');page.locator('#password').fill('password-123');page.locator('#auth-submit').click()
                expect(page.locator('#home')).to_be_visible()
                assert not errors,errors
                browser.close()
                print('PASS: mobile registration/login/logout, admin location, real-time slots, Maps URL, no overflow, PWA service worker, offline shell, no cached API, no JS/CSP errors.')
        finally:
            server.shutdown();thread.join();server.server_close();app.extensions['parking_engine'].dispose()

if __name__=='__main__':main()
