"""Exercise camera QR decoding against an isolated Flask application."""
import tempfile
import threading
from pathlib import Path
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright, expect
from app import create_app

with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    app=create_app(dict(TESTING=True,DATABASE_URL='sqlite:///'+str(Path(folder)/'scanner.db'),ADMIN_PASSWORD='test',PARKING_MODE='simulation'))
    server=make_server('127.0.0.1',5054,app,threaded=True)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            page=browser.new_page(viewport={'width':390,'height':844})
            page.goto('http://127.0.0.1:5054/driver/')
            expect(page.locator('#scan-section')).to_be_hidden()
            expect(page.locator('#auth-submit')).to_be_enabled()
            page.locator('#tab-register').click()
            for field,value in [('name','QR Driver'),('username','qrdriver'),('email','qrdriver@example.com'),('password','scanner-password')]:
                page.locator('#'+field).fill(value)
            page.locator('#auth-submit').click()
            expect(page.locator('#scan-section')).to_be_visible()
            page.add_script_tag(url='/static/vendor/qrcode.js')
            page.evaluate('''() => {
                const qr=qrcode(0,'M');qr.addData(location.origin+'/driver/#exit='+'a'.repeat(48));qr.make();
                const canvas=document.createElement('canvas');canvas.width=canvas.height=400;
                const ctx=canvas.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,400,400);
                const n=qr.getModuleCount(),size=Math.floor(360/n),offset=Math.floor((400-n*size)/2);
                ctx.fillStyle='black';for(let y=0;y<n;y++)for(let x=0;x<n;x++)if(qr.isDark(y,x))ctx.fillRect(offset+x*size,offset+y*size,size,size);
                navigator.mediaDevices.getUserMedia=async()=>{const stream=canvas.captureStream(10);setInterval(()=>{ctx.fillStyle='white';ctx.fillRect(0,0,1,1)},100);return stream;};
            }''')
            page.locator('#scan-qr').click()
            page.wait_for_url('**/#exit='+'a'*48)
            expect(page.locator('#entry-notice')).to_be_hidden()
            expect(page.locator('#entry-panel')).to_be_visible()
            expect(page.locator('#confirm-entry')).to_have_text('Xác nhận ra bãi')
            page.evaluate("() => {navigator.mediaDevices.getUserMedia=async()=>{throw new Error('denied')};}")
            page.locator('#scan-qr').click()
            expect(page.locator('#scan-status')).to_contain_text('Không mở được camera')
            expect(page.locator('#scan-qr')).to_be_enabled()
            browser.close()
        print('PASS: camera image decoded, login required, camera denial handled')
    finally:
        server.shutdown()
        app.extensions['parking_engine'].dispose()
