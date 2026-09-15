"""Smart Parking: transactional state, authenticated REST API and Vietnamese dashboard."""
import csv
import hmac
import io
import json
import os
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, session, send_from_directory
from sqlalchemy import create_engine, inspect, text, String, Integer, Float, Boolean, Text, select, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from werkzeug.security import generate_password_hash, check_password_hash
from entry import arrival_update, kiosk_status, barrier_update, settle_barrier

ROOT = Path(__file__).resolve().parent
SLOTS = ('A1', 'A2', 'A3', 'A4')
EVENT_NAMES = {'occupied': 'Vị trí có xe', 'vacated': 'Vị trí trống', 'gate': 'Điều khiển cổng',
               'denied': 'Từ chối xe vào', 'mode': 'Đổi chế độ', 'ack': 'Xác nhận lệnh', 'expired': 'Lệnh hết hạn'}
SOURCE_NAMES = {'simulation': 'Mô phỏng', 'device': 'Thiết bị ESP32', 'admin': 'Quản trị'}


def vietnamese_event(message):
    # Translate historical entries for display/export without rewriting the audit trail.
    return (message.replace('barrier', 'thanh chắn').replace('Barrier', 'Thanh chắn')
            .replace('Chuyển sang simulation', 'Chuyển sang mô phỏng')
            .replace('Chuyển sang hardware', 'Chuyển sang phần cứng'))


class Base(DeclarativeBase):
    pass


class State(Base):
    __tablename__ = 'parking_state'
    id: Mapped[int] = mapped_column(primary_key=True)
    payload: Mapped[str] = mapped_column(Text)


class Event(Base):
    __tablename__ = 'events'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[float] = mapped_column(Float, index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    slot: Mapped[str] = mapped_column(String(8), default='')
    source: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(String(255))


class Visit(Base):
    __tablename__ = 'visits'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slot: Mapped[str] = mapped_column(String(8))
    entered_at: Mapped[float] = mapped_column(Float, index=True)
    exited_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(20))


class Driver(Base):
    __tablename__ = 'drivers'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(60))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    username: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[float] = mapped_column(Float)


class ParkingLocation(Base):
    __tablename__ = 'parking_location'
    id: Mapped[int] = mapped_column(primary_key=True)
    payload: Mapped[str] = mapped_column(Text)


def create_app(config=None):
    load_dotenv(ROOT / '.env')
    app = Flask(__name__, static_folder='static', static_url_path='/static')
    data_dir = ROOT / 'data'
    data_dir.mkdir(exist_ok=True)
    testing = bool(config and config.get('TESTING'))
    secret_file = data_dir / 'secrets.json'
    if testing:
        keys = dict(secret='test-secret', admin='test-password', device='test-device-key')
    else:
        if not secret_file.exists():
            secret_file.write_text(json.dumps(dict(secret=secrets.token_hex(32), admin=secrets.token_urlsafe(12), device=secrets.token_urlsafe(32))), encoding='utf-8')
        keys = json.loads(secret_file.read_text(encoding='utf-8'))
    app.config.update(SECRET_KEY=os.getenv('SECRET_KEY') or keys['secret'],
                      ADMIN_PASSWORD=os.getenv('ADMIN_PASSWORD') or keys['admin'],
                      DEVICE_API_KEY=os.getenv('DEVICE_API_KEY') or keys['device'],
                      DATABASE_URL=os.getenv('DATABASE_URL') or 'sqlite:///' + str(data_dir / 'parking.db'),
                      PARKING_MODE=os.getenv('PARKING_MODE', 'simulation'),
                      MAX_CONTENT_LENGTH=16384, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE='Strict', SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE') == '1',
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=8))
    if config:
        app.config.update(config)
    if app.config['PARKING_MODE'] not in ('simulation', 'hardware'):
        raise ValueError('PARKING_MODE must be simulation or hardware')
    password_hash = generate_password_hash(app.config['ADMIN_PASSWORD'])
    engine = create_engine(app.config['DATABASE_URL'], pool_pre_ping=True)
    Base.metadata.create_all(engine)
    if "username" not in {c["name"] for c in inspect(engine).get_columns("drivers")}:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE drivers ADD COLUMN username VARCHAR(32)"))
            connection.execute(text("CREATE UNIQUE INDEX drivers_username_unique ON drivers(username)"))
    DB = sessionmaker(engine, expire_on_commit=False)
    lock = threading.RLock()
    app.extensions['parking_db'] = DB
    app.extensions['parking_engine'] = engine
    failures = {}

    def initial():
        return dict(mode=app.config['PARKING_MODE'], slots={s: False if app.config['PARKING_MODE'] == 'simulation' else None for s in SLOTS},
                    updated_at=None, last_seen=None, boot_id=None, sequence=-1,
                    barrier='closed', beam=False, command=None, pending_until=0, entry_present=False, arrival=None)

    with DB.begin() as db:
        if not db.get(State, 1):
            db.add(State(id=1, payload=json.dumps(initial())))

    def read_state(db):
        # Row lock also serializes writers in MySQL. SQLite is serialized by the process lock.
        row = db.execute(select(State).where(State.id == 1).with_for_update()).scalar_one()
        state = json.loads(row.payload)
        settle_barrier(state)
        row.payload = json.dumps(state)
        return row, state

    def save(row, state):
        row.payload = json.dumps(state)

    def event(db, kind, message, source, slot=''):
        db.add(Event(timestamp=time.time(), kind=kind, slot=slot, source=source, message=message))

    def online(s):
        return s['mode'] == 'simulation' or bool(s['last_seen'] and time.time() - s['last_seen'] < 15)

    def public(s):
        fresh = online(s)
        slots = {k: v if fresh else None for k, v in s['slots'].items()}
        reserved = [k for k,v in s.get('assignments', {}).items() if fresh and slots.get(k) is False and (v.get('expires_at') is None or v['expires_at'] > time.time())]
        for k in reserved:
            slots[k] = True
        available = sum(v is False for v in slots.values())
        occupied = sum(v is True for v in slots.values())
        return {**s, 'slots': slots, 'reserved': reserved, 'online': fresh, 'available': available,
                'occupied': occupied, 'unknown': 4-available-occupied,
                'server_time': time.time(), 'full': occupied == 4}

    def change_slots(db, s, slots, source):
        now = time.time()
        for name, occupied in slots.items():
            if occupied is True:
                s.get('assignments', {}).pop(name, None)
            old = s['slots'][name]
            if occupied == old:
                continue
            if occupied is not None:
                event(db, 'occupied' if occupied else 'vacated',
                      f'{name}: ' + ('có xe' if occupied else 'trống'), source, name)
                active = db.scalar(select(Visit).where(Visit.slot == name, Visit.exited_at.is_(None)))
                if occupied and active is None:
                    db.add(Visit(slot=name, entered_at=now, source=source))
                    s['pending_until'] = 0
                elif not occupied and active is not None:
                    active.exited_at = now
            s['slots'][name] = occupied
        s['updated_at'] = now

    def guard(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not session.get('authenticated'):
                return jsonify(error='Vui lòng đăng nhập.'), 401
            if request.method != 'GET' and not hmac.compare_digest(request.headers.get('X-CSRF-Token', ''), session.get('csrf', '!')):
                return jsonify(error='Phiên không hợp lệ. Hãy đăng nhập lại.'), 403
            return fn(*args, **kwargs)
        return wrapped

    def device_guard(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not hmac.compare_digest(request.headers.get('X-Device-Key', ''), app.config['DEVICE_API_KEY']):
                return jsonify(error='Khóa thiết bị không hợp lệ.'), 401
            return fn(*args, **kwargs)
        return wrapped

    def body():
        value = request.get_json(silent=True)
        if not isinstance(value, dict):
            raise ValueError('Nội dung phải là một đối tượng dữ liệu JSON.')
        return value

    @app.errorhandler(ValueError)
    def invalid(exc):
        message = str(exc)
        if message.startswith('invalid literal for int'):
            message = 'Số trang phải là một số nguyên hợp lệ.'
        return jsonify(error=message), 400

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/')
    def index():
        return send_from_directory(app.static_folder, 'index.html')

    @app.get('/api/health')
    def health():
        with DB() as db:
            db.execute(select(State.id).limit(1))
        return jsonify(status='ok')

    @app.post('/api/login')
    def login():
        data = body()
        pwd = data.get('password')
        if not isinstance(pwd, str) or len(pwd) > 256:
            raise ValueError('Mật khẩu không hợp lệ.')
        ip = request.remote_addr
        now = time.time()
        with lock:
            for key in list(failures):
                if now - failures[key][-1] >= 300:
                    del failures[key]
            attempts = failures.get(ip, [])
            attempts = [t for t in attempts if now-t < 300]
            if len(attempts) >= 5:
                return jsonify(error='Thử lại sau 5 phút.'), 429
            if not check_password_hash(password_hash, pwd):
                failures[ip] = attempts + [now]
                return jsonify(error='Mật khẩu không đúng.'), 401
            failures.pop(ip, None)
        session.clear()
        session.permanent = True
        session.update(authenticated=True, csrf=secrets.token_urlsafe(24))
        return jsonify(csrf=session['csrf'])

    @app.get('/api/session')
    @guard
    def current_session():
        return jsonify(csrf=session['csrf'])

    @app.post('/api/logout')
    @guard
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.get('/api/state')
    @guard
    def state():
        with lock, DB.begin() as db:
            _, s = read_state(db)
            return jsonify(public(s))

    @app.post('/api/simulation')
    @guard
    def simulate():
        data = body()
        name, occupied = data.get('slot'), data.get('occupied')
        if name not in SLOTS or type(occupied) is not bool:
            raise ValueError('Cần vị trí A1–A4 và trạng thái có xe hoặc trống hợp lệ.')
        with lock, DB.begin() as db:
            row, s = read_state(db)
            if s['mode'] != 'simulation':
                return jsonify(error='Mô phỏng đã tắt trong chế độ phần cứng.'), 409
            change_slots(db, s, {name: occupied}, 'simulation')
            save(row, s)
            return jsonify(public(s))

    @app.post('/api/mode')
    @guard
    def mode():
        target = body().get('mode')
        if target not in ('simulation', 'hardware'):
            raise ValueError('Chế độ không hợp lệ.')
        with lock, DB.begin() as db:
            row, s = read_state(db)
            if s['mode'] != target:
                if s['barrier'] != 'closed' or s['command'] or s['pending_until'] > time.time():
                    return jsonify(error='Đóng thanh chắn và chờ lượt vào kết thúc trước khi đổi chế độ.'), 409
                for visit in db.scalars(select(Visit).where(Visit.exited_at.is_(None))):
                    visit.exited_at = time.time()
                s = initial()
                s['mode'] = target
                if target == 'simulation':
                    s['slots'] = {k: False for k in SLOTS}
                event(db, 'mode', 'Chuyển sang ' + {'simulation':'mô phỏng', 'hardware':'phần cứng'}[target] + '; kết thúc phiên đỗ cũ.', 'admin')
                save(row, s)
            return jsonify(public(s))

    def gate_request(db, s, action, source, verified=False):
        now = time.time()
        if action not in ('entry', 'exit', 'close'):
            raise ValueError('Lệnh điều khiển phải là mở cổng vào, mở cổng ra hoặc đóng thanh chắn.')
        if (action == 'entry' or (action == 'exit' and source == 'device')) and not verified:
            return 'Người gửi xe cần quét QR tại cổng và đăng nhập để xác nhận vào bãi.'
        if not online(s):
            return 'ESP32 mất kết nối; không thể điều khiển từ xa.'
        if s['command'] and s['command']['expires_at'] > now:
            return 'Có lệnh đang chờ ESP32 xác nhận.'
        if action == 'entry':
            if s['barrier'] != 'closed':
                return 'Thanh chắn đang mở.'
            if s['pending_until'] > now:
                return 'Đang chờ xe trước vào vị trí (tối đa 30 giây).'
            if any(v is None for v in s['slots'].values()) or not any(v is False for v in s['slots'].values()):
                event(db, 'denied', 'Từ chối xe vào: bãi đầy hoặc cảm biến chưa xác định.', source)
                return 'Bãi đầy hoặc trạng thái cảm biến chưa xác định.'
        if action == 'close' and s['beam']:
            return 'Có vật cản tại thanh chắn; chưa thể đóng.'
        command = dict(id=secrets.token_hex(12), action=action, expires_at=now+10)
        if s['mode'] == 'simulation':
            barrier_update(s, 'closed' if action == 'close' else 'open')
            s['command'] = None
        else:
            s['command'] = command
        if action == 'entry':
            s['pending_until'] = now+30
        event(db, 'gate', {'entry': 'Yêu cầu mở cổng vào', 'exit': 'Yêu cầu mở cổng ra', 'close': 'Yêu cầu đóng thanh chắn'}[action], source)
        return None

    @app.post('/api/gate')
    @guard
    def gate():
        action = body().get('action')
        with lock, DB.begin() as db:
            row, s = read_state(db)
            error = gate_request(db, s, action, 'admin')
            save(row, s)
            return (jsonify(error=error), 409) if error else jsonify(public(s))

    @app.get('/qr/')
    def kiosk_page():
        return send_from_directory(app.static_folder, 'kiosk/index.html')

    @app.post('/api/kiosk/pair')
    @guard
    def kiosk_pair():
        session.clear()
        session.permanent = True
        session.update(kiosk=True, csrf=secrets.token_urlsafe(24))
        return jsonify(csrf=session['csrf'])

    def kiosk_guard(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not (session.get('kiosk') or session.get('authenticated')):
                return jsonify(error='Vui lòng kết nối máy tính bảng với bãi xe.'), 401
            if request.method != 'GET' and not hmac.compare_digest(request.headers.get('X-CSRF-Token', ''), session.get('csrf', '!')):
                return jsonify(error='Phiên không hợp lệ.'), 403
            return fn(*args, **kwargs)
        return wrapped

    @app.get('/api/kiosk/status')
    @kiosk_guard
    def kiosk_state():
        direction = request.args.get("direction", "entry")
        if direction not in ("entry", "exit"): raise ValueError("Hướng cổng không hợp lệ.")
        with lock, DB.begin() as db:
            row, s = read_state(db)
            status = kiosk_status(s, online(s), direction)
            save(row, s)
            return jsonify(**status, csrf=session['csrf'])

    @app.post('/api/kiosk/arrival')
    @kiosk_guard
    def simulate_arrival():
        data = body()
        direction = data.get('direction', 'entry')
        if direction not in ('entry', 'exit'): raise ValueError('Hướng cổng không hợp lệ.')
        present = data.get('present')
        if type(present) is not bool:
            raise ValueError('Trạng thái xe đến không hợp lệ.')
        with lock, DB.begin() as db:
            row, s = read_state(db)
            if s['mode'] != 'simulation':
                return jsonify(error='Chỉ cảm biến ESP32 được báo xe đến trong chế độ phần cứng.'), 409
            arrival_update(s, present, direction)
            save(row, s)
            return jsonify(kiosk_status(s, online(s), direction))

    @app.post('/api/kiosk/refresh')
    @kiosk_guard
    def refresh_arrival():
        direction = body().get("direction", "entry")
        if direction not in ("entry", "exit"): raise ValueError("Hướng cổng không hợp lệ.")
        with lock, DB.begin() as db:
            row, s = read_state(db)
            arrival = s.get('arrival' if direction == 'entry' else 'departure')
            if not online(s) or not s.get(direction + '_present') or not arrival or arrival['used_by']:
                return jsonify(error='Không có lượt xe đang chờ xác nhận.'), 409
            if arrival['expires_at'] <= time.time():
                s[direction + '_present'] = False
                arrival_update(s, True, direction)
                save(row, s)
            return jsonify(kiosk_status(s, online(s), direction))

    def confirm_entry(data, driver_id):
        direction = "exit" if request.path.endswith("/exit") else "entry"
        token = data.get('token')
        if not isinstance(token, str) or len(token) != 48 or any(c not in '0123456789abcdef' for c in token):
            return jsonify(error='Mã QR không hợp lệ. Vui lòng quét mã tại cổng.'), 400
        with lock, DB.begin() as db:
            row, s = read_state(db)
            arrival = s.get('arrival' if direction == 'entry' else 'departure')
            if not online(s) or not s.get(direction + '_present') or not arrival or arrival['used_by'] or arrival['expires_at'] <= time.time() or not hmac.compare_digest(token, arrival['token']):
                return jsonify(error='Mã QR đã hết hạn, đã dùng hoặc xe đã rời cổng. Vui lòng quét lại.'), 409
            if not db.get(Driver, driver_id):
                return jsonify(error='Vui lòng đăng nhập tài khoản người gửi xe.'), 401
            assigned_slot = None
            if direction == 'entry':
                previous = s.get('active_entries', {}).get(str(driver_id))
                if not previous:
                    previous = next((dict(slot=k, expires_at=v['expires_at']) for k,v in s.get('assignments', {}).items() if v['driver_id'] == driver_id and (v.get('expires_at') is None or v['expires_at'] > time.time())), None)
                if previous and (previous.get('expires_at') is None or previous['expires_at'] > time.time() or s['slots'].get(previous['slot']) is True):
                    return jsonify(error='Bạn đã có chỗ tại ô '+previous['slot']+'. Không được xác nhận vào bãi lần nữa. Vui lòng quét QR cổng ra khi rời bãi.'), 409
                s['assignments'] = {k:v for k,v in s.get('assignments', {}).items() if (v.get('expires_at') is None or v['expires_at'] > time.time()) and s['slots'].get(k) is False}
                assigned_slot = next((k for k in sorted(s['slots']) if s['slots'][k] is False and k not in s['assignments']), None)
                if not assigned_slot:
                    return jsonify(error='Không còn ô trống để xếp xe. Vui lòng chờ.'), 409
            error = gate_request(db, s, direction, 'admin', verified=True)
            if not error:
                if assigned_slot:
                    s['assignments'][assigned_slot] = dict(driver_id=driver_id, expires_at=None)
                    s.setdefault('active_entries', {})[str(driver_id)] = dict(slot=assigned_slot, expires_at=None)
                if direction == 'exit':
                    previous = s.get('active_entries', {}).pop(str(driver_id), None)
                    if previous:
                        s.get('assignments', {}).pop(previous['slot'], None)
                if s['mode'] == 'simulation':
                    s['auto_close_at'] = time.time()+8
                arrival['used_by'] = driver_id
                arrival['confirmed_at'] = time.time()
                driver = db.get(Driver, driver_id)
                account_name = driver.username or driver.email
                action_name = 'vào bãi' if direction == 'entry' else 'ra bãi'
                event(db, 'gate', f'Tài khoản {account_name} xác nhận {action_name} bằng QR.', 'admin')
            save(row, s)
            if error:
                return jsonify(error=error), 409
            return jsonify(ok=True, assigned_slot=assigned_slot, mode=s['mode'], message='Đã mở thanh chắn mô phỏng.' if s['mode']=='simulation' else 'Đã xác nhận. Đang chờ ESP32 mở thanh chắn.')

    @app.post('/api/device/telemetry')
    @device_guard
    def telemetry():
        data = body()
        slots = data.get('slots')
        if not isinstance(slots, dict) or set(slots) != set(SLOTS) or any(v is not None and type(v) is not bool for v in slots.values()):
            raise ValueError('Dữ liệu phải chứa đủ A1–A4 với trạng thái có xe, trống hoặc chưa xác định.')
        seq, boot = data.get('sequence'), data.get('boot_id')
        if type(seq) is not int or seq < 0 or not isinstance(boot, str) or not 1 <= len(boot) <= 64:
            raise ValueError('Số thứ tự gói tin hoặc mã phiên khởi động không hợp lệ.')
        if data.get('barrier') not in ('open', 'closed') or type(data.get('beam')) is not bool:
            raise ValueError('Cần trạng thái thanh chắn và cảm biến vật cản hợp lệ.')
        if any(type(data.get(k, False)) is not bool for k in ('entry_present', 'exit_present')):
            raise ValueError('Trạng thái cảm biến xe đến không hợp lệ.')
        with lock, DB.begin() as db:
            row, s = read_state(db)
            if s['mode'] != 'hardware':
                return jsonify(error='Máy chủ đang ở chế độ mô phỏng.'), 409
            if s['boot_id'] == boot and seq <= s['sequence']:
                return jsonify(error='Gói tin trùng hoặc sai thứ tự.'), 409
            change_slots(db, s, slots, 'device')
            if not online(s) or s['boot_id'] != boot:
                arrival_update(s, False)
                arrival_update(s, False, "exit")
            arrival_update(s, data.get('entry_present', False))
            arrival_update(s, data.get('exit_present', False), 'exit')
            barrier_update(s, data['barrier'])
            s.update(last_seen=time.time(), boot_id=boot, sequence=seq, beam=data['beam'])
            command = s['command']
            if command and (data.get('ack') == command['id'] or command['expires_at'] < time.time()):
                event(db, 'ack' if data.get('ack') == command['id'] else 'expired',
                      'Thiết bị xác nhận lệnh' if data.get('ack') == command['id'] else 'Lệnh hết hạn', 'device')
                s['command'] = None
            save(row, s)
            return jsonify(command=s['command'], available=public(s)['available'], server_time=time.time())

    @app.post('/api/device/gate')
    @device_guard
    def device_gate():
        action = body().get('action')
        with lock, DB.begin() as db:
            row, s = read_state(db)
            if s['mode'] != 'hardware':
                return jsonify(error='Chưa bật chế độ phần cứng.'), 409
            error = gate_request(db, s, action, 'device')
            save(row, s)
            return (jsonify(error=error), 409) if error else jsonify(command=s['command'])

    def event_query():
        q = select(Event)
        kind = request.args.get('kind', '')
        if kind:
            q = q.where(Event.kind == kind)
        date = request.args.get('date', '')
        if date:
            try:
                start = datetime.strptime(date, '%Y-%m-%d').replace(tzinfo=timezone(timedelta(hours=7))).timestamp()
            except ValueError:
                raise ValueError('Ngày phải có dạng năm-tháng-ngày, ví dụ 2026-09-10.')
            q = q.where(Event.timestamp >= start, Event.timestamp < start+86400)
        return q.order_by(Event.id.desc())

    @app.post('/api/parking/release')
    @guard
    def release_parking():
        slot = body().get('slot')
        if slot not in SLOTS:
            raise ValueError('Vị trí không hợp lệ.')
        with lock, DB.begin() as db:
            row, s = read_state(db)
            assigned = s.get('assignments', {}).pop(slot, None)
            owners = [k for k,v in s.get('active_entries', {}).items() if v['slot'] == slot]
            if not assigned and not owners:
                return jsonify(error='Ô này không có tài khoản được xếp chỗ.'), 409
            for k in owners:
                del s['active_entries'][k]
            if s['mode'] == 'simulation':
                change_slots(db, s, {slot: False}, 'admin')
            event(db, 'gate', f'Quản trị giải phóng chỗ đã xếp tại {slot}.', 'admin', slot)
            save(row, s)
            return jsonify(public(s))

    @app.get('/api/events')
    @guard
    def events():
        page = max(1, int(request.args.get('page', '1')))
        with DB() as db:
            query = event_query()
            total = db.scalar(select(func.count()).select_from(query.subquery()))
            items = [dict(id=e.id, timestamp=e.timestamp, kind=e.kind, slot=e.slot, source=e.source, message=account_event(db, e.message))
                     for e in db.scalars(query.offset((page-1)*20).limit(20))]
        return jsonify(items=items, total=total, page=page, pages=max(1, (total+19)//20))

    def account_event(db, message):
        import re
        match = re.fullmatch(r'Tài khoản #(\d+) xác nhận (entry|exit|vào bãi|ra bãi) bằng QR\.', message)
        if match:
            driver = db.get(Driver, int(match[1]))
            if driver:
                direction = 'vào bãi' if match[2] in ('entry', 'vào bãi') else 'ra bãi'
                return f'Tài khoản {driver.username or driver.email} xác nhận {direction} bằng QR.'
        return vietnamese_event(message)

    @app.get('/api/events/export')
    @guard
    def export():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Mã sự kiện', 'Thời gian (+07:00)', 'Loại', 'Vị trí', 'Nguồn', 'Nội dung'])
        with DB() as db:
            for e in db.scalars(event_query().limit(10000)):
                writer.writerow([e.id, datetime.fromtimestamp(e.timestamp, timezone(timedelta(hours=7))).strftime('%d/%m/%Y %H:%M:%S'), EVENT_NAMES.get(e.kind, e.kind), e.slot, SOURCE_NAMES.get(e.source, e.source), vietnamese_event(e.message)])
        return app.response_class('\ufeff'+output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=parking-events.csv'})

    @app.get('/api/stats')
    @guard
    def stats():
        tz = timezone(timedelta(hours=7))
        today = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        days = []
        with DB() as db:
            for i in range(6, -1, -1):
                start = (today-timedelta(days=i)).timestamp()
                arrivals = db.scalar(select(func.count()).select_from(Visit).where(Visit.entered_at >= start, Visit.entered_at < start+86400))
                departures = db.scalar(select(func.count()).select_from(Visit).where(Visit.exited_at >= start, Visit.exited_at < start+86400))
                days.append(dict(date=datetime.fromtimestamp(start, tz).strftime('%d/%m'), arrivals=arrivals, departures=departures))
            avg = db.scalar(select(func.avg(Visit.exited_at-Visit.entered_at)).where(Visit.exited_at.is_not(None)))
        return jsonify(days=days, average_minutes=round((avg or 0)/60, 1))

    from customer import register_customer
    register_customer(app, DB, lock, State, Driver, ParkingLocation, public, guard, confirm_entry)
    return app


if __name__ == '__main__':
    from waitress import serve
    application = create_app()
    host, port = os.getenv('HOST', '127.0.0.1'), int(os.getenv('PORT', '5000'))
    print(f'HAISMRTPak: http://{host}:{port}', flush=True)
    print('Mat khau: data/secrets.json (hoac cau hinh trong .env)', flush=True)
    serve(application, host=host, port=port, threads=8)
