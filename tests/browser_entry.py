"""Browser acceptance against disposable local Workers/D1 on port 8787."""
import uuid
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    base='http://127.0.0.1:8787'
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        try:
            kiosk=browser.new_page(viewport={'width':1024,'height':1366})
            kiosk.goto(base+'/qr/')
            kiosk.locator('#password').fill('local-cloudflare-test-password')
            kiosk.locator('#pair-form button').click()
            expect(kiosk.locator('#display')).to_be_visible()
            expect(kiosk.locator('#qr')).to_be_hidden()
            kiosk.locator('#arrive').click()
            expect(kiosk.locator('#qr')).to_be_visible()
            image=kiosk.locator('#qr').evaluate('(c)=>c.toDataURL()')
            decoder=browser.new_page()
            decoder.add_script_tag(path='.runtime/qr-libs/node_modules/jsqr/dist/jsQR.js')
            url=decoder.evaluate('''async data => {
                const image=new Image();image.src=data;await image.decode();
                const c=document.createElement('canvas');c.width=image.width;c.height=image.height;
                const ctx=c.getContext('2d');ctx.drawImage(image,0,0);
                return jsQR(ctx.getImageData(0,0,c.width,c.height).data,c.width,c.height).data;
            }''',image)
            assert url.startswith(base+'/driver/#entry=')
            decoder.close()
            driver=browser.new_page(viewport={'width':390,'height':844})
            errors=[];driver.on('pageerror',lambda e:errors.append(str(e)))
            driver.goto(url)
            expect(driver.locator('#entry-notice')).to_be_visible()
            expect(driver.locator('#auth-submit')).to_be_enabled()
            driver.locator('#tab-register').click()
            driver.locator('#name').fill('QR Driver')
            suffix=uuid.uuid4().hex[:16]
            driver.locator('#username').fill('qr_'+suffix)
            driver.locator('#email').fill('qr_'+suffix+'@example.com')
            driver.locator('#password').fill('qr-test-password')
            driver.locator('#auth-submit').click()
            expect(driver.locator('#entry-panel')).to_be_visible()
            driver.locator('#confirm-entry').click()
            expect(driver.locator('#entry-result')).to_have_text('Đã xác nhận tài khoản. Vui lòng chờ thanh chắn mở trước khi di chuyển.')
            expect(kiosk.locator('#title')).to_have_text('Mời bạn vào bãi',timeout=10000)
            expect(kiosk.locator('#qr')).to_be_hidden()
            admin=browser.new_page();admin.goto(base+'/')
            admin.locator('#password').fill('local-cloudflare-test-password');admin.locator('#login-form button').click()
            expect(admin.locator('#app')).to_be_visible()
            expect(admin.locator('[data-gate="entry"]')).to_have_count(0)
            admin.locator('[data-slot="A1"]').click()
            expect(admin.locator('[data-slot="A1"] img.slot-car')).to_be_visible()
            expect(driver.locator('[data-slot="A1"] img.slot-car')).to_be_visible(timeout=10000)
            assert driver.locator('[data-slot="A1"] img').evaluate('(img)=>img.complete&&img.naturalWidth>0')
            assert driver.evaluate('document.documentElement.scrollWidth<=innerWidth')
            Path('artifacts').mkdir(exist_ok=True)
            driver.screenshot(path='artifacts/entry-driver.png',full_page=True)
            kiosk.screenshot(path='artifacts/entry-kiosk.png',full_page=True)
            admin.locator('[data-gate="close"]').click()
            admin.locator('[data-slot="A1"]').click()
            kiosk.locator('#leave').click();expect(kiosk.locator('#qr')).to_be_hidden()
            assert not errors,errors
            print('PASS: real QR image decoded, tablet pairing, phone signup, one-time entry confirmation, kiosk response, car images and mobile layout.')
        finally:
            browser.close()


if __name__=='__main__':main()
