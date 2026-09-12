import json
import tempfile
import time
import unittest
from pathlib import Path
from app import create_app, Driver, State


class EntryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.app=create_app(dict(TESTING=True,DATABASE_URL='sqlite:///'+str(Path(self.tmp.name)/'entry.db'),PARKING_MODE='simulation'))
        with self.app.extensions['parking_db'].begin() as db:
            db.add(Driver(id=1,name='Driver',email='driver@example.com',username='driver',password_hash='fixture',created_at=time.time()))
        self.admin=self.app.test_client()
        self.csrf=self.admin.post('/api/login',json={'password':'test-password'}).json['csrf']
        self.kiosk=self.app.test_client()
        csrf=self.kiosk.post('/api/login',json={'password':'test-password'}).json['csrf']
        self.kcsrf=self.kiosk.post('/api/kiosk/pair',json={},headers={'X-CSRF-Token':csrf}).json['csrf']
        self.driver=self.app.test_client()
        with self.driver.session_transaction() as session:
            session.update(driver_id=1,driver_csrf='driver-csrf')

    def tearDown(self):
        self.app.extensions['parking_engine'].dispose();self.tmp.cleanup()

    def arrival(self,present=True):
        return self.kiosk.post('/api/kiosk/arrival',json={'present':present},headers={'X-CSRF-Token':self.kcsrf})

    def confirm(self,token):
        return self.driver.post('/api/driver/entry',json={'token':token},headers={'X-CSRF-Token':'driver-csrf'})

    def test_admin_reuses_session_and_exit_qr_is_separate(self):
        self.assertEqual(self.admin.get('/api/kiosk/status').status_code,200)
        self.assertEqual(self.admin.get('/api/state').status_code,200)
        token=self.kiosk.post('/api/kiosk/arrival',json={'present':True,'direction':'exit'},headers={'X-CSRF-Token':self.kcsrf}).json['token']
        self.assertEqual(self.confirm(token).status_code,409)
        self.assertEqual(self.app.test_client().post('/api/driver/exit',json={'token':token}).status_code,401)
        self.assertEqual(self.driver.post('/api/driver/exit',json={'token':token},headers={'X-CSRF-Token':'driver-csrf'}).status_code,200)
        self.assertEqual(self.driver.post('/api/driver/exit',json={'token':token},headers={'X-CSRF-Token':'driver-csrf'}).status_code,409)

    def test_pairing_is_limited_and_no_entry_bypass(self):
        for route in ('state','events','location'):
            self.assertEqual(self.kiosk.get('/api/'+route).status_code,401)
        self.assertEqual(self.driver.get('/api/kiosk/status').status_code,401)
        self.assertEqual(self.app.test_client().get('/api/kiosk/status').status_code,401)
        self.assertEqual(self.kiosk.post('/api/kiosk/arrival',json={'present':True}).status_code,403)
        self.assertEqual(self.admin.post('/api/gate',json={'action':'entry'},headers={'X-CSRF-Token':self.csrf}).status_code,409)
        self.assertEqual(self.admin.post('/api/device/gate',json={'action':'entry'},headers={'X-Device-Key':'test-device-key'}).status_code,409)

    def test_account_required_token_single_use_and_not_public(self):
        token=self.arrival().json['token']
        self.assertEqual(len(token),48)
        self.assertEqual(self.app.test_client().post('/api/driver/entry',json={'token':token}).status_code,401)
        self.assertEqual(self.driver.post('/api/driver/entry',json={'token':token}).status_code,403)
        self.assertNotIn('arrival',self.driver.get('/api/driver/parking').json)
        self.assertEqual(self.confirm('0'*48).status_code,409)
        self.assertEqual(self.confirm('é'*48).status_code,400)
        self.assertEqual(self.confirm(token).status_code,200)
        self.assertEqual(self.confirm(token).status_code,409)
        status=self.kiosk.get('/api/kiosk/status').json
        self.assertTrue(status['confirmed']);self.assertIsNone(status['token'])
        self.assertEqual(self.kiosk.post('/api/kiosk/refresh',json={},headers={'X-CSRF-Token':self.kcsrf}).status_code,409)

    def test_departure_and_expiry_invalidate_qr(self):
        token=self.arrival().json['token'];self.arrival(False)
        self.assertEqual(self.confirm(token).status_code,409)
        token=self.arrival().json['token']
        with self.app.extensions['parking_db'].begin() as db:
            row=db.get(State,1);s=json.loads(row.payload);s['arrival']['expires_at']=time.time()-1;row.payload=json.dumps(s)
        self.assertIsNone(self.kiosk.get('/api/kiosk/status').json['token'])
        self.assertEqual(self.confirm(token).status_code,409)
        refreshed=self.kiosk.post('/api/kiosk/refresh',json={},headers={'X-CSRF-Token':self.kcsrf}).json['token']
        self.assertNotEqual(token,refreshed);self.assertEqual(self.confirm(refreshed).status_code,200)

    def test_hardware_requires_sensor_and_fresh_telemetry(self):
        self.admin.post('/api/mode',json={'mode':'hardware'},headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(self.arrival().status_code,409)
        payload=dict(boot_id='boot',sequence=1,slots={s:False for s in ('A1','A2','A3','A4')},barrier='closed',beam=False,entry_present=True)
        self.admin.post('/api/device/telemetry',json=payload,headers={'X-Device-Key':'test-device-key'})
        token=self.kiosk.get('/api/kiosk/status').json['token']
        self.assertTrue(token)
        with self.app.extensions['parking_db'].begin() as db:
            row=db.get(State,1);s=json.loads(row.payload);s['last_seen']=time.time()-20;row.payload=json.dumps(s)
        self.assertIsNone(self.kiosk.get('/api/kiosk/status').json['token'])
        self.assertEqual(self.confirm(token).status_code,409)
