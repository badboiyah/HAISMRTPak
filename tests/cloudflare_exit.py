"""Exit QR acceptance against disposable local D1 only."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from cloudflare_check import Client
import uuid

admin=Client()
admin.csrf=admin.call('/api/login',{'password':'local-cloudflare-test-password'})['csrf']
assert admin.call('/api/kiosk/status')['direction']=='entry'
assert admin.call('/api/state')['mode']=='simulation'
admin.call('/api/gate',{'action':'close'})
admin.call('/api/kiosk/arrival',{'present':False,'direction':'exit'})
token=admin.call('/api/kiosk/arrival',{'present':True,'direction':'exit'})['token']
guest=Client()
guest.call('/api/driver/exit',{'token':token},expected=401)
driver=Client();driver.csrf=driver.call('/api/driver/session')['csrf']
suffix=uuid.uuid4().hex[:12]
driver.csrf=driver.call('/api/driver/register',{'name':'Exit Driver','username':'exit_'+suffix,'email':suffix+'@example.com','password':'exit-test-password'},expected=201)['csrf']
driver.call('/api/driver/entry',{'token':token},expected=409)
driver.call('/api/driver/exit',{'token':token},headers={'X-CSRF-Token':'wrong'},expected=403)
driver.call('/api/driver/exit',{'token':token})
driver.call('/api/driver/exit',{'token':token},expected=409)
assert admin.call('/api/kiosk/status?direction=exit')['confirmed']
admin.call('/api/gate',{'action':'close'})
admin.call('/api/kiosk/arrival',{'present':False,'direction':'exit'})
print('PASS: admin shared QR session, separate exit token, login/CSRF enforcement, single-use exit')

