"""Run against a disposable local `wrangler dev` database, never production."""
import concurrent.futures
import http.cookiejar
import json
import time
import urllib.error
import urllib.request
import uuid

BASE = 'http://127.0.0.1:8787'


class Client:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = ''

    def call(self, path, data=None, expected=200, headers=None):
        headers = {'Content-Type': 'application/json', 'X-CSRF-Token': self.csrf, **(headers or {})}
        request = urllib.request.Request(BASE + path, data=None if data is None else json.dumps(data).encode(), headers=headers)
        try:
            response = self.opener.open(request, timeout=20)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            raw = response.read()
            assert response.status == expected, (path, response.status, expected, raw)
            assert response.headers.get('Cache-Control') == 'no-store' if path.startswith('/api/') else True
            return json.loads(raw) if 'application/json' in response.headers.get('Content-Type', '') else raw


def main():
    admin, driver, outsider = Client(), Client(), Client()
    admin.csrf = admin.call('/api/login', {'password': 'local-cloudflare-test-password'})['csrf']
    for route in ('state', 'events', 'stats', 'location'):
        outsider.call('/api/' + route, expected=401)
    admin.call('/api/simulation', {'slot': 'A1', 'occupied': True}, expected=403, headers={'X-CSRF-Token': 'wrong'})
    admin.call('/api/location', {}, expected=403, headers={'Origin': 'https://attacker.example'})
    # This script expects a fresh local database in simulation mode.
    for slot in ('A1', 'A2', 'A3', 'A4'):
        admin.call('/api/simulation', {'slot': slot, 'occupied': False})
    email = f'test-{uuid.uuid4().hex}@example.com'
    driver.csrf = driver.call('/api/driver/session')['csrf']
    driver.call('/api/driver/register', {'name': 'A', 'email': 'bad', 'password': 'short'}, expected=400)
    username = 'user_' + uuid.uuid4().hex[:20]
    result = driver.call('/api/driver/register', {'name': 'Phương Chi', 'username': username, 'email': email, 'password': 'test-password-123'}, expected=201)
    driver.csrf = result['csrf']
    assert result['user']['email'] == email
    driver.call('/api/state', expected=401)
    driver.call('/api/gate', {'action': 'entry'}, expected=401)
    admin.call('/api/driver/parking', expected=401)
    view = driver.call('/api/driver/parking')
    assert view['available'] == 4
    assert not {'command', 'beam', 'boot_id', 'sequence', 'pending_until', 'last_seen'} & view.keys()
    loc = dict(name='Bãi kiểm thử', address='123 Đường A', hours='06:00 - 22:00', latitude=10.77, longitude=106.69)
    admin.call('/api/location', {**loc, 'latitude': 91}, expected=400)
    admin.call('/api/location', {**loc, 'longitude': None}, expected=400)
    admin.call('/api/location', loc)
    assert '10.77%2C106.69' in driver.call('/api/driver/parking')['location']['directions_url']
    # Parallel changes must keep all four slots and exactly one open visit per slot.
    def occupy(slot):
        clone = Client(); clone.jar = admin.jar
        clone.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(clone.jar)); clone.csrf = admin.csrf
        return clone.call('/api/simulation', {'slot': slot, 'occupied': True})
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        list(pool.map(occupy, ['A1', 'A2', 'A3', 'A4']))
    assert driver.call('/api/driver/parking')['full'] is True
    admin.call('/api/gate', {'action': 'entry'}, expected=409)
    admin.call('/api/gate', {'action': 'exit'})
    admin.call('/api/gate', {'action': 'close'})
    for slot in ('A1', 'A2', 'A3', 'A4'):
        admin.call('/api/simulation', {'slot': slot, 'occupied': False})
    assert admin.call('/api/stats')['days'][-1]['arrivals'] >= 4
    assert admin.call('/api/events')['total'] >= 8
    assert admin.call('/api/events/export').startswith(b'\xef\xbb\xbf')
    admin.call('/api/events?date=2026-02-30', expected=400)
    admin.call('/api/events?page=abc', expected=400)
    admin.call('/api/mode', {'mode': 'hardware'})
    assert driver.call('/api/driver/parking')['unknown'] == 4
    admin.call('/api/gate', {'action': 'entry'}, expected=409)
    device = {'X-Device-Key': 'local-cloudflare-test-device'}
    telemetry = dict(boot_id='test-boot', sequence=1, slots={s: False for s in ('A1','A2','A3','A4')}, barrier='closed', beam=False)
    outsider.call('/api/device/telemetry', telemetry, expected=401)
    outsider.call('/api/device/telemetry', telemetry, headers=device)
    outsider.call('/api/device/telemetry', telemetry, expected=409, headers=device)
    command = admin.call('/api/gate', {'action': 'entry'})['command']
    admin.call('/api/gate', {'action': 'entry'}, expected=409)
    outsider.call('/api/device/telemetry', {**telemetry, 'sequence': 2, 'ack': command['id'], 'barrier': 'open', 'beam': True}, headers=device)
    admin.call('/api/gate', {'action': 'close'}, expected=409)
    outsider.call('/api/device/telemetry', {**telemetry, 'sequence': 3, 'slots': {**telemetry['slots'], 'A1': True}}, headers=device)
    assert driver.call('/api/driver/parking')['occupied'] == 1
    print('Waiting for telemetry to become stale...', flush=True)
    time.sleep(16)
    assert driver.call('/api/driver/parking')['unknown'] == 4
    admin.call('/api/gate', {'action': 'exit'}, expected=409)
    admin.call('/api/mode', {'mode': 'simulation'})
    driver.call('/api/driver/logout', {})
    driver.call('/api/driver/parking', expected=401)
    driver.csrf = driver.call('/api/driver/session')['csrf']
    driver.call('/api/driver/login', {'email': email, 'password': 'wrong-password'}, expected=401)
    wrong = driver.call('/api/driver/login', {'identifier': username, 'password': 'wrong'}, expected=401)
    assert wrong['error'] == 'Email/tên đăng nhập hoặc mật khẩu không đúng.'
    driver.csrf = driver.call('/api/driver/login', {'identifier': username.upper(), 'password': 'test-password-123'})['csrf']
    driver.call('/api/driver/logout', {})
    driver.csrf = driver.call('/api/driver/session')['csrf']
    driver.csrf = driver.call('/api/driver/login', {'identifier': email.upper(), 'password': 'test-password-123'})['csrf']
    assert driver.call('/api/driver/session')['user']['email'] == email
    outsider.csrf = outsider.call('/api/driver/session')['csrf']
    outsider.call('/api/driver/register', {'name': 'Other User', 'username': 'other_' + uuid.uuid4().hex[:20], 'email': email, 'password': 'test-password-123'}, expected=409)
    for _ in range(10):
        try:
            outsider.call('/api/driver/login', {'email': 'missing@example.com', 'password': 'wrong-password'}, expected=401)
        except AssertionError as exc:
            assert '429' in str(exc); break
    else:
        raise AssertionError('Rate limiting did not activate')
    for path in ('/', '/driver/', '/driver/sw.js', '/static/driver/manifest.webmanifest', '/static/brand/logo.png'):
        admin.call(path)
    print('PASS: roles, CSRF, persistence, D1 concurrency, capacity, telemetry, offline safety, reports, assets and rate limits.')


if __name__ == '__main__':
    main()
