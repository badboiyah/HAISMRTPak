import json
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from sqlalchemy import select
from app import create_app, State, Visit


class ParkingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = dict(TESTING=True, DATABASE_URL='sqlite:///'+str(Path(self.temp.name)/'test.db'),
                           ADMIN_PASSWORD='test-password', DEVICE_API_KEY='test-device-key', PARKING_MODE='simulation')
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.csrf = self.client.post('/api/login', json={'password':'test-password'}).json['csrf']
        self.device_headers = {'X-Device-Key':'test-device-key'}

    def tearDown(self):
        self.app.extensions['parking_engine'].dispose()
        self.temp.cleanup()

    def post(self, url, data):
        return self.client.post('/api'+url, json=data, headers={'X-CSRF-Token':self.csrf})

    def hardware(self):
        self.assertEqual(self.post('/mode', {'mode':'hardware'}).status_code, 200)

    def telemetry(self, seq=1, **changes):
        data=dict(boot_id='boot-test', sequence=seq, slots={s:False for s in ('A1','A2','A3','A4')},barrier='closed',beam=False)
        data.update(changes)
        return self.client.post('/api/device/telemetry',json=data,headers=self.device_headers)

    def test_authentication_and_csrf(self):
        other=self.app.test_client()
        self.assertEqual(other.get('/api/state').status_code,401)
        self.assertEqual(self.client.post('/api/gate',json={'action':'entry'}).status_code,403)
        self.assertEqual(other.post('/api/device/telemetry',json={}).status_code,401)
        self.assertEqual(self.post('/logout',{}).status_code,200)
        self.assertEqual(self.client.get('/api/state').status_code,401)

    def test_login_rate_limit(self):
        client=self.app.test_client()
        for _ in range(5):
            self.assertEqual(client.post('/api/login',json={'password':'wrong'}).status_code,401)
        self.assertEqual(client.post('/api/login',json={'password':'wrong'}).status_code,429)

    def test_initial_four_free(self):
        s=self.client.get('/api/state').json
        self.assertEqual((s['available'],s['occupied'],s['unknown']),(4,0,0))

    def test_full_denies_entry_and_allows_exit(self):
        for slot in ('A1','A2','A3','A4'):
            self.assertEqual(self.post('/simulation',dict(slot=slot,occupied=True)).status_code,200)
        self.assertEqual(self.post('/gate',{'action':'entry'}).status_code,409)
        self.assertEqual(self.post('/gate',{'action':'exit'}).status_code,200)
        self.assertEqual(self.client.get('/api/state').json['barrier'],'open')

    def test_repeated_occupancy_does_not_duplicate_visit(self):
        for _ in range(3):self.post('/simulation',dict(slot='A1',occupied=True))
        self.post('/simulation',dict(slot='A1',occupied=False))
        with self.app.extensions['parking_db']() as db:
            visits=list(db.scalars(select(Visit)))
            self.assertEqual(len(visits),1)
            self.assertIsNotNone(visits[0].exited_at)
        stats=self.client.get('/api/stats').json
        self.assertEqual(stats['days'][-1]['arrivals'],1)
        self.assertEqual(stats['days'][-1]['departures'],1)

    def test_persistence(self):
        self.post('/simulation',dict(slot='A2',occupied=True))
        other=create_app(self.config)
        client=other.test_client()
        client.post('/api/login',json={'password':'test-password'})
        self.assertTrue(client.get('/api/state').json['slots']['A2'])
        other.extensions['parking_engine'].dispose()

    def test_unknown_and_offline_block_entry(self):
        self.hardware()
        self.assertEqual(self.post('/gate',{'action':'entry'}).status_code,409)
        self.telemetry(slots={'A1':None,'A2':False,'A3':False,'A4':False})
        self.assertEqual(self.post('/gate',{'action':'entry'}).status_code,409)
        self.telemetry(2)
        with self.app.extensions['parking_db'].begin() as db:
            row=db.get(State,1);s=json.loads(row.payload);s['last_seen']=time.time()-20;row.payload=json.dumps(s)
        state=self.client.get('/api/state').json
        self.assertEqual(state['unknown'],4)
        self.assertEqual(state['available'],0)
        self.assertEqual(self.post('/gate',{'action':'exit'}).status_code,409)

    def test_telemetry_validation_and_replay(self):
        self.hardware()
        self.assertEqual(self.telemetry().status_code,200)
        self.assertEqual(self.telemetry().status_code,409)
        self.assertEqual(self.telemetry(0).status_code,409)
        self.assertEqual(self.telemetry(2,slots={'A1':'false'}).status_code,400)
        self.assertEqual(self.telemetry(2,sequence=True).status_code,400)
        self.assertEqual(self.telemetry(0,boot_id='new-boot').status_code,200)

    def test_command_ack_and_obstruction(self):
        self.hardware();self.telemetry()
        request=self.post('/gate',{'action':'entry'})
        self.assertEqual(request.status_code,200)
        self.assertEqual(request.json['barrier'],'closed')
        command=request.json['command']
        self.assertEqual(self.post('/gate',{'action':'entry'}).status_code,409)
        response=self.telemetry(2,barrier='open',beam=True,ack=command['id'])
        self.assertIsNone(response.json['command'])
        self.assertEqual(self.post('/gate',{'action':'close'}).status_code,409)

    def test_expired_command_not_delivered(self):
        self.hardware();self.telemetry();self.post('/gate',{'action':'exit'})
        with self.app.extensions['parking_db'].begin() as db:
            row=db.get(State,1);s=json.loads(row.payload);s['command']['expires_at']=time.time()-1;row.payload=json.dumps(s)
        self.assertIsNone(self.telemetry(2).json['command'])

    def test_mode_isolation(self):
        self.assertEqual(self.telemetry().status_code,409)
        self.hardware()
        self.assertEqual(self.post('/simulation',dict(slot='A1',occupied=True)).status_code,409)
        self.assertEqual(self.client.get('/api/state').json['unknown'],4)

    def test_mode_change_blocked_while_gate_open(self):
        self.post('/gate',{'action':'exit'})
        self.assertEqual(self.post('/mode',{'mode':'hardware'}).status_code,409)

    def test_entry_reservation_prevents_double_admission(self):
        self.assertEqual(self.post('/gate',{'action':'entry'}).status_code,200)
        self.post('/gate',{'action':'close'})
        self.assertEqual(self.post('/gate',{'action':'entry'}).status_code,409)
        self.post('/simulation',dict(slot='A1',occupied=True))
        self.assertEqual(self.post('/gate',{'action':'entry'}).status_code,200)

    def test_concurrent_entry_only_one_accepted(self):
        def enter(_):
            client=self.app.test_client()
            token=client.post('/api/login',json={'password':'test-password'}).json['csrf']
            return client.post('/api/gate',json={'action':'entry'},headers={'X-CSRF-Token':token}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            result=list(pool.map(enter,range(2)))
        self.assertEqual(sorted(result),[200,409])

    def test_filters_export_and_invalid_input(self):
        self.post('/simulation',dict(slot='A1',occupied=True))
        events=self.client.get('/api/events?kind=occupied').json
        self.assertEqual(events['total'],1)
        csv=self.client.get('/api/events/export?kind=occupied')
        self.assertEqual(csv.status_code,200)
        self.assertTrue(csv.data.startswith(b'\xef\xbb\xbf'))
        self.assertIn(b'A1',csv.data)
        self.assertEqual(self.client.get('/api/events?date=bad').status_code,400)
        self.assertEqual(self.client.get('/api/events?page=bad').status_code,400)
        self.assertEqual(self.post('/simulation',dict(slot='A5',occupied=True)).status_code,400)
        self.assertEqual(self.post('/simulation',dict(slot='A1',occupied='false')).status_code,400)
        self.assertEqual(self.client.post('/api/gate',json=[],headers={'X-CSRF-Token':self.csrf}).status_code,400)


if __name__=='__main__':unittest.main()
