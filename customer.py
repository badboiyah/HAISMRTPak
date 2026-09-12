"""Driver accounts, parking availability and authenticated QR entry confirmation."""
import hmac
import json
import math
import re
import secrets
import time
from functools import wraps
from urllib.parse import urlencode

from flask import jsonify, request, session, send_from_directory, redirect
from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash


def register_customer(app, DB, lock, State, Driver, Location, public, admin_guard, confirm_entry):
    with DB.begin() as db:
        if not db.get(Location, 1):
            db.add(Location(id=1, payload=json.dumps(dict(name='Bãi xe HAISMRTPak', address='',
                                                         latitude=None, longitude=None, hours=''))))
    limits = {}
    dummy_hash = generate_password_hash(secrets.token_urlsafe(24))

    def payload():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValueError('Dữ liệu phải là một đối tượng JSON.')
        return data

    def csrf_valid(key):
        expected = session.get(key)
        return isinstance(expected, str) and hmac.compare_digest(request.headers.get('X-CSRF-Token', ''), expected)

    def limit(kind, count, window):
        now = time.time()
        with lock:
            for k in list(limits):
                if limits[k][-1] < now-3600:
                    del limits[k]
            key = (kind, request.remote_addr)
            recent = [t for t in limits.get(key, []) if now-t < window]
            if len(recent) >= count:
                return False
            limits[key] = recent + [now]
            return True

    def driver_guard(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            with DB() as db:
                user = db.get(Driver, session['driver_id']) if session.get('driver_id') else None
            if not user:
                return jsonify(error='Vui lòng đăng nhập tài khoản người gửi xe.'), 401
            if request.method != 'GET' and not csrf_valid('driver_csrf'):
                return jsonify(error='Phiên hết hạn. Hãy tải lại ứng dụng.'), 403
            return fn(*args, **kwargs)
        return wrapped

    def user_json(user):
        return dict(name=user.name, email=user.email, username=user.username)

    def authenticate(user):
        session.clear()
        session.permanent = True
        session.update(driver_id=user.id, driver_csrf=secrets.token_urlsafe(24))
        return jsonify(user=user_json(user), csrf=session['driver_csrf'])

    def location_json(db):
        location = json.loads(db.get(Location, 1).payload)
        destination = None
        if location['latitude'] is not None and location['longitude'] is not None:
            destination = f"{location['latitude']},{location['longitude']}"
        elif location['address']:
            destination = location['address']
        return dict(**location, configured=bool(destination), directions_url=(
            'https://www.google.com/maps/dir/?'+urlencode(dict(api=1, destination=destination, travelmode='driving'))
            if destination else None))

    @app.get('/driver')
    def driver_redirect():
        return redirect('/driver/')

    @app.get('/driver/')
    def driver_index():
        return send_from_directory(app.static_folder, 'driver/index.html')

    @app.get('/driver/sw.js')
    def driver_worker():
        response = send_from_directory(app.static_folder, 'driver/sw.js')
        response.headers['Cache-Control'] = 'no-cache'
        return response

    @app.get('/api/driver/session')
    def driver_session():
        with DB() as db:
            user = db.get(Driver, session['driver_id']) if session.get('driver_id') else None
            if user:
                return jsonify(user=user_json(user), csrf=session['driver_csrf'])
        if not session.get('driver_auth_csrf'):
            session['driver_auth_csrf'] = secrets.token_urlsafe(24)
        return jsonify(user=None, csrf=session['driver_auth_csrf'])

    def credentials(data):
        email, password = data.get('email'), data.get('password')
        if not isinstance(email, str) or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email.strip()) or len(email.strip()) > 254:
            raise ValueError('Vui lòng nhập địa chỉ thư điện tử hợp lệ.')
        if not isinstance(password, str) or not 8 <= len(password) <= 128:
            raise ValueError('Mật khẩu cần từ 8 đến 128 ký tự.')
        return email.strip().lower(), password

    @app.post('/api/driver/register')
    def driver_register():
        if not csrf_valid('driver_auth_csrf'):
            return jsonify(error='Vui lòng tải lại ứng dụng trước khi đăng ký.'), 403
        if not limit('register', 5, 3600):
            return jsonify(error='Đã đạt giới hạn đăng ký. Vui lòng thử lại sau 1 giờ.'), 429
        data = payload()
        email, password = credentials(data)
        username = data.get('username', '')
        if not isinstance(username, str) or not re.fullmatch(r'[A-Za-z0-9_]{3,32}', username.strip()):
            raise ValueError('Tên đăng nhập cần 3–32 chữ cái không dấu, chữ số hoặc dấu gạch dưới.')
        username = username.strip().lower()
        name = data.get('name')
        if not isinstance(name, str) or not 2 <= len(name.strip()) <= 60 or any(ord(c) < 32 for c in name):
            raise ValueError('Tên cần từ 2 đến 60 ký tự.')
        hashed = generate_password_hash(password)
        try:
            with lock, DB.begin() as db:
                user = Driver(name=name.strip(), email=email, username=username, password_hash=hashed, created_at=time.time())
                db.add(user)
                db.flush()
            return authenticate(user), 201
        except IntegrityError:
            return jsonify(error='Email hoặc tên đăng nhập đã được sử dụng.'), 409

    @app.post('/api/driver/login')
    def driver_login():
        if not csrf_valid('driver_auth_csrf'):
            return jsonify(error='Vui lòng tải lại ứng dụng trước khi đăng nhập.'), 403
        if not limit('login', 10, 300):
            return jsonify(error='Đã thử đăng nhập nhiều lần. Vui lòng chờ 5 phút.'), 429
        data = payload()
        identifier, password = data.get('identifier', data.get('email', '')), data.get('password')
        if not isinstance(identifier, str) or not 1 <= len(identifier.strip()) <= 254 or not isinstance(password, str) or not 1 <= len(password) <= 128:
            return jsonify(error='Email/tên đăng nhập hoặc mật khẩu không đúng.'), 401
        identifier = identifier.strip().lower()
        with DB() as db:
            user = db.scalar(select(Driver).where(or_(Driver.email == identifier, Driver.username == identifier)))
            valid = check_password_hash(user.password_hash if user else dummy_hash, password)
            if not user or not valid:
                return jsonify(error='Email/tên đăng nhập hoặc mật khẩu không đúng.'), 401
            return authenticate(user)

    @app.post('/api/driver/logout')
    @driver_guard
    def driver_logout():
        session.clear()
        return jsonify(ok=True)

    @app.post('/api/driver/entry')
    @driver_guard
    def driver_entry():
        return confirm_entry(payload(), session['driver_id'])

    @app.get('/api/driver/parking')
    @driver_guard
    def driver_parking():
        with lock, DB.begin() as db:
            s = public(json.loads(db.get(State, 1).payload))
            # Explicit allow-list: no device IDs, gate commands, visits or admin data.
            visible = {k:s[k] for k in ('slots','available','occupied','unknown','full','online','mode','updated_at','server_time')}
            return jsonify(**visible, location=location_json(db))

    @app.get('/api/location')
    @admin_guard
    def get_location():
        with DB() as db:
            return jsonify(location_json(db))

    @app.post('/api/location')
    @admin_guard
    def update_location():
        data = payload()
        cleaned = {}
        for key, minimum, maximum in (('name',2,100), ('address',0,300), ('hours',0,100)):
            value = data.get(key, '')
            if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum or any(ord(c)<32 for c in value):
                label = {'name':'Tên bãi xe', 'address':'Địa chỉ', 'hours':'Giờ hoạt động'}[key]
                raise ValueError(f'{label}: độ dài phải từ {minimum} đến {maximum} ký tự.')
            cleaned[key] = value.strip()
        for key, bound in (('latitude',90), ('longitude',180)):
            value = data.get(key)
            if value is not None and (type(value) not in (int,float) or not math.isfinite(value) or not -bound <= value <= bound):
                raise ValueError('Tọa độ không hợp lệ.')
            cleaned[key] = value
        if (cleaned['latitude'] is None) != (cleaned['longitude'] is None):
            raise ValueError('Nhập đủ cả vĩ độ và kinh độ hoặc để trống cả hai.')
        with lock, DB.begin() as db:
            row = db.execute(select(Location).where(Location.id==1).with_for_update()).scalar_one()
            row.payload = json.dumps(cleaned)
        return jsonify(ok=True)
