import json
import tempfile
import time
import unittest
from pathlib import Path
from sqlalchemy import select
from app import create_app, Driver, State


class CustomerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.config=dict(TESTING=True,DATABASE_URL='sqlite:///'+str(Path(self.temp.name)/'customer.db'),ADMIN_PASSWORD='test-password',PARKING_MODE='simulation')
        self.app=create_app(self.config)
        self.client=self.app.test_client()
        self.token=self.client.get('/api/driver/session').json['csrf']
        self.admin=self.app.test_client()
        self.admin_token=self.admin.post('/api/login',json={'password':'test-password'}).json['csrf']

    def tearDown(self):
        self.app.extensions['parking_engine'].dispose();self.temp.cleanup()

    def post(self,path,data):
        return self.client.post('/api/driver'+path,json=data,headers={'X-CSRF-Token':self.token})

    def register(self):
        response=self.post('/register',dict(name='Phương Chi',username='phuongchi',email='Driver@Example.com',password='password-123'))
        self.assertEqual(response.status_code,201)
        self.token=response.json['csrf']
        return response

    def admin_post(self,path,data):
        return self.admin.post('/api'+path,json=data,headers={'X-CSRF-Token':self.admin_token})

    def test_register_login_logout_persist_and_hash(self):
        self.register()
        self.assertEqual(self.client.get('/api/driver/session').json['user']['email'],'driver@example.com')
        with self.app.extensions['parking_db']() as db:
            user=db.scalar(select(Driver));self.assertNotEqual(user.password_hash,'password-123')
        self.assertEqual(self.post('/logout',{}).status_code,200)
        self.assertEqual(self.client.get('/api/driver/parking').status_code,401)
        other=create_app(self.config);client=other.test_client()
        token=client.get('/api/driver/session').json['csrf']
        result=client.post('/api/driver/login',json={'email':'DRIVER@example.com','password':'password-123'},headers={'X-CSRF-Token':token})
        self.assertEqual(result.status_code,200)
        other.extensions['parking_engine'].dispose()

    def test_username_login_and_generic_error(self):
        self.register()
        self.post('/logout', {})
        self.token = self.client.get('/api/driver/session').json['csrf']
        for identifier in ('PHUONGCHI', 'driver@example.com'):
            result = self.post('/login', dict(identifier=identifier, password='password-123'))
            self.assertEqual(result.status_code, 200)
            self.token = result.json['csrf']
            self.post('/logout', {})
            self.token = self.client.get('/api/driver/session').json['csrf']
        for identifier, password in [('phuongchi','wrong'), ('driver@example.com','wrong'), ('missing','password-123')]:
            result = self.post('/login', dict(identifier=identifier, password=password))
            self.assertEqual(result.status_code, 401)
            self.assertEqual(result.json['error'], 'Email/tên đăng nhập hoặc mật khẩu không đúng.')

    def test_username_required_and_unique(self):
        for username in ('', 'ab', 'bad@name'):
            result = self.post('/register', dict(name='Valid Name', username=username, email='valid@example.com', password='password-123'))
            self.assertEqual(result.status_code, 400)
        self.register()
        other = self.app.test_client()
        csrf = other.get('/api/driver/session').json['csrf']
        result = other.post('/api/driver/register', json=dict(name='Other User', username='PHUONGCHI', email='other@example.com', password='password-123'), headers={'X-CSRF-Token':csrf})
        self.assertEqual(result.status_code, 409)

    def test_roles_and_allowlist(self):
        self.register()
        for route in ('state','events','stats','location'):
            self.assertEqual(self.client.get('/api/'+route).status_code,401)
        for route,data in [('gate',{'action':'entry'}),('simulation',{'slot':'A1','occupied':True}),('mode',{'mode':'hardware'}),('location',{})]:
            self.assertEqual(self.client.post('/api/'+route,json=data,headers={'X-CSRF-Token':self.token}).status_code,401)
        self.assertEqual(self.admin.get('/api/driver/parking').status_code,401)
        result=self.client.get('/api/driver/parking').json
        self.assertEqual(result['available'],4)
        for key in ('command','beam','boot_id','sequence','pending_until','last_seen','password_hash'):
            self.assertNotIn(key,result)

    def test_live_state_full_and_offline(self):
        self.register()
        for slot in ('A1','A2','A3','A4'):
            self.admin_post('/simulation',dict(slot=slot,occupied=True))
        result=self.client.get('/api/driver/parking').json
        self.assertTrue(result['full']);self.assertEqual(result['available'],0)
        with self.app.extensions['parking_db'].begin() as db:
            row=db.get(State,1);s=json.loads(row.payload);s['mode']='hardware';s['last_seen']=time.time()-20;s['slots']={slot:False for slot in s['slots']};row.payload=json.dumps(s)
        result=self.client.get('/api/driver/parking').json
        self.assertEqual(result['unknown'],4);self.assertEqual(result['available'],0)

    def test_location_validation_and_directions(self):
        self.register()
        self.assertIsNone(self.client.get('/api/driver/parking').json['location']['directions_url'])
        location=dict(name='Bãi thử nghiệm',address='123 Đường A, Thành phố B',hours='06:00 - 22:00',latitude=10.77,longitude=106.69)
        self.assertEqual(self.admin_post('/location',location).status_code,200)
        saved=self.client.get('/api/driver/parking').json['location']
        self.assertTrue(saved['configured']);self.assertIn('destination=10.77%2C106.69',saved['directions_url'])
        for changes in ({'latitude':91},{'longitude':None},{'latitude':True},{'latitude':float('nan')},{'name':'x'}):
            self.assertEqual(self.admin_post('/location',{**location,**changes}).status_code,400)
        self.assertEqual(self.admin_post('/location',{**location,'latitude':None,'longitude':None}).status_code,200)
        self.assertIn('123',self.client.get('/api/driver/parking').json['location']['directions_url'])

    def test_csrf_validation_and_duplicate_email(self):
        self.assertEqual(self.client.post('/api/driver/register',json={}).status_code,403)
        self.assertEqual(self.post('/register',dict(name='A',email='bad',password='123')).status_code,400)
        self.register()
        self.assertEqual(self.client.post('/api/driver/logout',json={}).status_code,403)
        other=self.app.test_client();token=other.get('/api/driver/session').json['csrf']
        result=other.post('/api/driver/register',json=dict(name='Other',username='otheruser',email='DRIVER@example.com',password='password-123'),headers={'X-CSRF-Token':token})
        self.assertEqual(result.status_code,409)

    def test_wrong_password_and_rate_limit(self):
        for _ in range(10):
            self.assertEqual(self.post('/login',dict(email='none@example.com',password='password-123')).status_code,401)
        self.assertEqual(self.post('/login',dict(email='none@example.com',password='password-123')).status_code,429)

    def test_no_cache_and_worker_scope(self):
        self.register()
        self.assertEqual(self.client.get('/api/driver/parking').headers['Cache-Control'],'no-store')
        with self.client.get('/driver/') as response:
            self.assertEqual(response.status_code,200)
        with self.client.get('/driver/sw.js') as response:
            self.assertEqual(response.headers['Cache-Control'],'no-cache')
        with self.client.get('/static/driver/manifest.webmanifest') as response:
            self.assertEqual(response.json['scope'],'/driver/')


if __name__=='__main__':unittest.main()
