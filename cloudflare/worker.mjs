const slots = ['A1', 'A2', 'A3', 'A4'];
const now = () => Date.now() / 1000;
const encoder = new TextEncoder();
const token = () => Array.from(crypto.getRandomValues(new Uint8Array(32)), b => b.toString(16).padStart(2, '0')).join('');
const hex = b => Array.from(new Uint8Array(b), v => v.toString(16).padStart(2, '0')).join('');
const digest = async text => hex(await crypto.subtle.digest('SHA-256', encoder.encode(text)));
const query = (db, sql, ...args) => db.prepare(sql).bind(...args);
class HTTPError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}
const reject = (status, message) => { throw new HTTPError(status, message); };
const json = (body, status = 200) => Response.json(body, {status});
async function equal(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string') return false;
  const x = await digest(a), y = await digest(b);
  let difference = 0;
  for (let i = 0; i < x.length; i++) difference |= x.charCodeAt(i) ^ y.charCodeAt(i);
  return difference === 0;
}
export async function passwordHash(password, pepper, salt = token()) {
  if (typeof pepper !== 'string' || pepper.length < 32) reject(503, 'Chưa cấu hình bảo mật tài khoản người gửi xe.');
  // Workers production caps Web Crypto PBKDF2 at 100,000 rounds. A separately
  // stored secret pepper prevents offline guessing from a database-only leak.
  const pepperKey = await crypto.subtle.importKey('raw', encoder.encode(pepper), {name:'HMAC',hash:'SHA-256'}, false, ['sign']);
  const material = await crypto.subtle.sign('HMAC', pepperKey, encoder.encode(password));
  const key = await crypto.subtle.importKey('raw', material, 'PBKDF2', false, ['deriveBits']);
  const bits = await crypto.subtle.deriveBits({name: 'PBKDF2', hash: 'SHA-256', salt: encoder.encode(salt), iterations: 100000}, key, 256);
  return `pbkdf2-sha256-peppered$100000$${salt}$${hex(bits)}`;
}
async function passwordValid(password, saved, pepper) {
  const parts = saved?.split('$');
  if (parts?.length !== 4 || parts[0] !== 'pbkdf2-sha256-peppered' || parts[1] !== '100000') return false;
  return equal(await passwordHash(password, pepper, parts[2]), saved);
}
export const initial = mode => ({mode, slots: Object.fromEntries(slots.map(s => [s, mode === 'simulation' ? false : null])),
  updated_at: null, last_seen: null, boot_id: null, sequence: -1, barrier: 'closed', beam: false, command: null, pending_until: 0, entry_present: false, arrival: null});
function settleBarrier(s) {
  if(s.mode==='simulation'&&s.barrier==='open'&&s.auto_close_at&&now()>=s.auto_close_at&&!s.beam){barrierUpdate(s,'closed');s.auto_close_at=null;}
}
function barrierUpdate(s, barrier) {
  if(s.barrier==='open'&&barrier==='closed') {
    for(const [direction,key] of [['entry','arrival'],['exit','departure']]) {
      if(s[direction+'_present']&&s[key]?.used_by) {
        s[direction+'_present']=false;
        arrivalUpdate(s,true,direction);
      }
    }
  }
  s.barrier=barrier;
}
function arrivalUpdate(s, present, direction='entry') {
  const key=direction==='entry'?'arrival':'departure',pk=direction+'_present';
  if(present&&!s[pk])s[key]={token:token().slice(0,48),expires_at:now()+120,used_by:null};
  if(!present)s[key]=null;
  s[pk]=present;
}
function kioskStatus(s,direction='entry') {
  const key=direction==='entry'?'arrival':'departure',ready=online(s)&&s[direction+'_present'];
  let a=s[key];
  if(ready&&a?.used_by&&a.confirmed_at!=null&&now()>=a.confirmed_at+5){s[direction+'_present']=false;arrivalUpdate(s,true,direction);a=s[key];}
  return {direction,mode:s.mode,online:online(s),present:Boolean(ready),token:ready&&a&&!a.used_by&&a.expires_at>now()?a.token:null,
  expires_at:ready&&a?a.expires_at:null,confirmed:Boolean(ready&&a&&a.used_by),barrier:online(s)?s.barrier:'unknown',server_time:now()};
}
const online = s => s.mode === 'simulation' || Boolean(s.last_seen && now() - s.last_seen < 15);
export function publicState(s) {
  const fresh = online(s), visible = Object.fromEntries(slots.map(k => [k, fresh ? s.slots[k] : null]));
  const reserved=Object.entries(s.assignments||{}).filter(([k,v])=>fresh&&visible[k]===false&&(v.expires_at==null||v.expires_at>now())).map(([k])=>k);
  for(const k of reserved)visible[k]=true;
  const available = Object.values(visible).filter(x => x === false).length;
  const occupied = Object.values(visible).filter(x => x === true).length;
  return {...s, slots: visible, reserved, online: fresh, available, occupied, unknown: 4 - available - occupied, full: occupied === 4, server_time: now()};
}
async function state(db) { const s=JSON.parse((await query(db, 'SELECT payload FROM parking_state WHERE id=1').first()).payload);settleBarrier(s);return s; }
function event(writes, db, kind, message, source, slot = '') {
  writes.push(query(db, 'INSERT INTO events(timestamp,kind,slot,source,message) VALUES(?,?,?,?,?)', now(), kind, slot, source, message));
}
function changeSlots(writes, db, s, changes, source) {
  const timestamp = now();
  for (const [slot, occupied] of Object.entries(changes)) {
    if(occupied===true&&s.assignments)delete s.assignments[slot];
    if (occupied === s.slots[slot]) continue;
    if (occupied !== null) {
      event(writes, db, occupied ? 'occupied' : 'vacated', `${slot}: ${occupied ? 'có xe' : 'trống'}`, source, slot);
      if (occupied) {
        writes.push(query(db, 'INSERT INTO visits(slot,entered_at,source) SELECT ?,?,? WHERE NOT EXISTS(SELECT 1 FROM visits WHERE slot=? AND exited_at IS NULL)', slot, timestamp, source, slot));
        s.pending_until = 0;
      } else writes.push(query(db, 'UPDATE visits SET exited_at=? WHERE slot=? AND exited_at IS NULL', timestamp, slot));
    }
    s.slots[slot] = occupied;
  }
  s.updated_at = timestamp;
}
// A CHECK constraint guards the version and aborts the entire D1 transaction on conflict.
export async function mutate(db, fn) {
  for (let attempt = 0; attempt < 8; attempt++) {
    const row = await query(db, 'SELECT payload,version FROM parking_state WHERE id=1').first();
    const s = JSON.parse(row.payload), writes = [];settleBarrier(s);const result = fn(s, writes), guard = token();
    try {
      await db.batch([
        query(db, 'INSERT INTO write_guard(id,valid) VALUES(?,CASE WHEN (SELECT version FROM parking_state WHERE id=1)=? THEN 1 ELSE 0 END)', guard, row.version),
        ...writes,
        query(db, 'UPDATE parking_state SET payload=?,version=version+1 WHERE id=1', JSON.stringify(s)),
        query(db, 'DELETE FROM write_guard WHERE id=?', guard)
      ]);
      return result ?? publicState(s);
    } catch (e) {
      if (!String(e).includes('CHECK constraint failed')) throw e;
    }
  }
  reject(409, 'Hệ thống đang có nhiều thao tác. Vui lòng thử lại.');
}
function gate(writes, db, s, action, source, verified = false) {
  if (!['entry', 'exit', 'close'].includes(action)) reject(400, 'Lệnh điều khiển cổng không hợp lệ.');
  if ((action === 'entry' || (action === 'exit' && source === 'device')) && !verified) return 'Người gửi xe cần quét QR tại cổng và đăng nhập để xác nhận vào bãi.';
  if (!online(s)) return 'ESP32 mất kết nối; không thể điều khiển từ xa.';
  if (s.command && s.command.expires_at > now()) return 'Có lệnh đang chờ ESP32 xác nhận.';
  if (action === 'entry') {
    if (s.barrier !== 'closed') return 'Thanh chắn đang mở.';
    if (s.pending_until > now()) return 'Đang chờ xe trước vào vị trí (tối đa 30 giây).';
    if (Object.values(s.slots).some(v => v === null) || !Object.values(s.slots).some(v => v === false)) {
      event(writes, db, 'denied', 'Từ chối xe vào: bãi đầy hoặc cảm biến chưa xác định.', source);
      return 'Bãi đầy hoặc trạng thái cảm biến chưa xác định.';
    }
  }
  if (action === 'close' && s.beam) return 'Có vật cản tại thanh chắn; chưa thể đóng.';
  if (s.mode === 'simulation') { barrierUpdate(s, action === 'close' ? 'closed' : 'open'); s.command = null; }
  else s.command = {id: token().slice(0, 24), action, expires_at: now() + 10};
  if (action === 'entry') s.pending_until = now() + 30;
  event(writes, db, 'gate', {entry: 'Yêu cầu mở cổng vào', exit: 'Yêu cầu mở cổng ra', close: 'Yêu cầu đóng thanh chắn'}[action], source);
  return null;
}
async function readSession(request, db) {
  const value = request.headers.get('Cookie')?.match(/(?:^|;\s*)haismrtpak_session=([a-f0-9]{64})(?:;|$)/)?.[1];
  if (!value) return null;
  const hash = await digest(value);
  const row = await query(db, 'SELECT * FROM sessions WHERE token_hash=? AND expires_at>?', hash, now()).first();
  return row ? {...row, token_hash: hash} : null;
}
async function sessionResponse(request, db, previous, role, driver = null, status = 200) {
  const value = token(), csrf = token(), time = now(), hash = await digest(value);
  const writes = [query(db, 'DELETE FROM sessions WHERE expires_at<=?', time), query(db, 'DELETE FROM rate_limits WHERE expires_at<=?', time)];
  if (previous) writes.push(query(db, 'DELETE FROM sessions WHERE token_hash=?', previous.token_hash));
  writes.push(query(db, 'INSERT INTO sessions(token_hash,role,driver_id,csrf,expires_at) VALUES(?,?,?,?,?)', hash, role, driver?.id ?? null, csrf, time + 28800));
  await db.batch(writes);
  const response = json(role === 'admin' ? {csrf} : {user: driver ? {name: driver.name, email: driver.email} : null, csrf}, status);
  response.headers.set('Set-Cookie', `haismrtpak_session=${value}; Path=/; HttpOnly; SameSite=Strict; Max-Age=28800${new URL(request.url).protocol === 'https:' ? '; Secure' : ''}`);
  return response;
}
async function csrfGuard(request, session) {
  if (!session || !await equal(request.headers.get('X-CSRF-Token'), session.csrf)) reject(403, 'Phiên hết hạn. Hãy tải lại ứng dụng.');
}
async function rate(request, db, kind, limit, window) {
  const key = `${kind}:${await digest(request.headers.get('CF-Connecting-IP') || 'local')}`;
  const time = now();
  const row = await query(db, `INSERT INTO rate_limits(key,count,expires_at) VALUES(?,1,?)
    ON CONFLICT(key) DO UPDATE SET count=CASE WHEN expires_at<=? THEN 1 ELSE count+1 END,
    expires_at=CASE WHEN expires_at<=? THEN ? ELSE expires_at END RETURNING count`, key, time + window, time, time, time + window).first();
  if (row.count > limit) reject(429, 'Đã thử nhiều lần. Vui lòng chờ rồi thử lại.');
}
function credentials(body) {
  if (typeof body.email !== 'string' || body.email.trim().length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(body.email.trim())) reject(400, 'Vui lòng nhập địa chỉ thư điện tử hợp lệ.');
  if (typeof body.password !== 'string' || body.password.length < 8 || body.password.length > 128) reject(400, 'Mật khẩu cần từ 8 đến 128 ký tự.');
  return {email: body.email.trim().toLowerCase(), password: body.password};
}
async function location(db) {
  const loc = JSON.parse((await query(db, 'SELECT payload FROM parking_location WHERE id=1').first()).payload);
  const destination = loc.latitude !== null && loc.longitude !== null ? `${loc.latitude},${loc.longitude}` : loc.address;
  return {...loc, configured: Boolean(destination), directions_url: destination ? 'https://www.google.com/maps/dir/?' + new URLSearchParams({api: '1', destination, travelmode: 'driving'}) : null};
}
function cleanLocation(data) {
  const result = {};
  for (const [name, min, max] of [['name', 2, 100], ['address', 0, 300], ['hours', 0, 100]]) {
    const value = data[name] ?? '';
    if (typeof value !== 'string' || value.trim().length < min || value.trim().length > max || /[\u0000-\u001f]/.test(value)) reject(400, 'Tên, địa chỉ hoặc giờ hoạt động không hợp lệ.');
    result[name] = value.trim();
  }
  for (const [name, bound] of [['latitude', 90], ['longitude', 180]]) {
    const value = data[name] ?? null;
    if (value !== null && (typeof value !== 'number' || !Number.isFinite(value) || Math.abs(value) > bound)) reject(400, 'Tọa độ không hợp lệ.');
    result[name] = value;
  }
  if ((result.latitude === null) !== (result.longitude === null)) reject(400, 'Nhập đủ cả vĩ độ và kinh độ hoặc để trống cả hai.');
  return result;
}
async function parseBody(request) {
  if (Number(request.headers.get('Content-Length')) > 16384) reject(413, 'Dữ liệu quá lớn.');
  const reader = request.body?.getReader();
  if (!reader) reject(400, 'Nội dung phải là một đối tượng dữ liệu JSON.');
  let size = 0; const chunks = [];
  while (true) {
    const {done, value} = await reader.read(); if (done) break;
    size += value.byteLength;
    if (size > 16384) { await reader.cancel(); reject(413, 'Dữ liệu quá lớn.'); }
    chunks.push(value);
  }
  const bytes = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  let body;
  try { body = JSON.parse(new TextDecoder().decode(bytes)); } catch { reject(400, 'Dữ liệu JSON không hợp lệ.'); }
  if (!body || typeof body !== 'object' || Array.isArray(body)) reject(400, 'Nội dung phải là một đối tượng dữ liệu JSON.');
  return body;
}
async function api(request, env) {
  const db = env.DB, url = new URL(request.url), path = url.pathname, method = request.method;
  if (method === 'GET' && path === '/api/health') {
    await query(db, 'SELECT id FROM parking_state WHERE id=1').first(); return json({status: 'ok'});
  }
  if (!['GET', 'POST'].includes(method)) reject(405, 'Phương thức không được hỗ trợ.');
  if (method === 'POST') {
    const origin = request.headers.get('Origin');
    if (origin && origin !== url.origin) reject(403, 'Nguồn yêu cầu không hợp lệ.');
  }
  const data = method === 'POST' ? await parseBody(request) : null;
  const session = await readSession(request, db);
  if (path === '/api/kiosk/pair' && method === 'POST') {
    if (session?.role !== 'admin') reject(401, 'Vui lòng đăng nhập quản trị để kết nối máy tính bảng.');
    await csrfGuard(request, session);
    return sessionResponse(request, db, session, 'kiosk');
  }
  if (path.startsWith('/api/kiosk/')) {
    if (!['admin','kiosk'].includes(session?.role)) reject(401, 'Vui lòng kết nối máy tính bảng với bãi xe.');
    const direction=(method==='GET'?url.searchParams.get('direction'):data?.direction)||'entry';
    if(!['entry','exit'].includes(direction))reject(400,'Hướng cổng không hợp lệ.');
    const key=direction==='entry'?'arrival':'departure',pk=direction+'_present';
    if (method === 'POST') await csrfGuard(request, session);
    if (path === '/api/kiosk/status' && method === 'GET') return json({...await mutate(db,s=>kioskStatus(s,direction)),csrf:session.csrf});
    if (path === '/api/kiosk/arrival' && method === 'POST') {
      if (typeof data.present !== 'boolean') reject(400, 'Trạng thái xe đến không hợp lệ.');
      return json(await mutate(db, s => {
        if (s.mode !== 'simulation') reject(409, 'Chỉ cảm biến ESP32 được báo xe đến trong chế độ phần cứng.');
        arrivalUpdate(s, data.present,direction);
        return kioskStatus(s,direction);
      }));
    }
    if (path === '/api/kiosk/refresh' && method === 'POST') return json(await mutate(db, s => {
      if (!online(s) || !s[pk] || !s[key] || s[key].used_by) reject(409, 'Không có lượt xe đang chờ xác nhận.');
      if (s[key].expires_at <= now()) {s[pk]=false;arrivalUpdate(s,true,direction);}
      return kioskStatus(s,direction);
    }));
    reject(404, 'Không tìm thấy chức năng.');
  }
  if (path === '/api/login' && method === 'POST') {
    if (typeof data.password !== 'string' || data.password.length > 256) reject(400, 'Mật khẩu không hợp lệ.');
    if (!env.ADMIN_PASSWORD) reject(503, 'Chưa cấu hình tài khoản quản trị.');
    await rate(request, db, 'admin', 5, 300);
    if (!await equal(data.password, env.ADMIN_PASSWORD)) reject(401, 'Mật khẩu không đúng.');
    return sessionResponse(request, db, session, 'admin');
  }
  if (path === '/api/driver/session' && method === 'GET') {
    if (session?.role === 'driver') {
      const user = await query(db, 'SELECT name,email FROM drivers WHERE id=?', session.driver_id).first();
      if (user) return json({user, csrf: session.csrf});
    }
    if (session?.role === 'anonymous') return json({user: null, csrf: session.csrf});
    return sessionResponse(request, db, session, 'anonymous');
  }
  if (['/api/driver/register', '/api/driver/login'].includes(path) && method === 'POST') {
    await csrfGuard(request, session);
    const registering = path.endsWith('/register');
    await rate(request, db, registering ? 'register' : 'login', registering ? 5 : 10, registering ? 3600 : 300);
    let user;
    if (registering) {
      const {email, password} = credentials(data);
      if (typeof data.username !== 'string' || !/^[A-Za-z0-9_]{3,32}$/.test(data.username.trim())) reject(400, 'Tên đăng nhập cần 3–32 chữ cái không dấu, chữ số hoặc dấu gạch dưới.');
      const username = data.username.trim().toLowerCase();
      if (typeof data.name !== 'string' || data.name.trim().length < 2 || data.name.trim().length > 60 || /[\u0000-\u001f]/.test(data.name)) reject(400, 'Tên cần từ 2 đến 60 ký tự.');
      const hash = await passwordHash(password, env.PASSWORD_PEPPER);
      try { user = await query(db, 'INSERT INTO drivers(name,email,username,password_hash,created_at) VALUES(?,?,?,?,?) RETURNING id,name,email,username', data.name.trim(), email, username, hash, now()).first(); }
      catch (e) { if (String(e).includes('UNIQUE constraint failed')) reject(409, 'Email hoặc tên đăng nhập đã được sử dụng.'); throw e; }
    } else {
      const identifier = data.identifier ?? data.email, password = data.password;
      if (typeof identifier !== 'string' || !identifier.trim() || identifier.trim().length > 254 || typeof password !== 'string' || !password || password.length > 128) reject(401, 'Email/tên đăng nhập hoặc mật khẩu không đúng.');
      const normalized = identifier.trim().toLowerCase();
      user = await query(db, 'SELECT * FROM drivers WHERE email=? OR username=?', normalized, normalized).first();
      const saved = user?.password_hash || `pbkdf2-sha256-peppered$100000$${'0'.repeat(64)}$${'0'.repeat(64)}`;
      const valid = await passwordValid(password, saved, env.PASSWORD_PEPPER);
      if (!user || !valid) reject(401, 'Email/tên đăng nhập hoặc mật khẩu không đúng.');
    }
    return sessionResponse(request, db, session, 'driver', user, registering ? 201 : 200);
  }
  const device = path.startsWith('/api/device/'), driver = path.startsWith('/api/driver/');
  if (device) {
    if (!env.DEVICE_API_KEY || !await equal(request.headers.get('X-Device-Key'), env.DEVICE_API_KEY)) reject(401, 'Khóa thiết bị không hợp lệ.');
  } else {
    if (session?.role !== (driver ? 'driver' : 'admin')) reject(401, 'Vui lòng đăng nhập.');
    if (method === 'POST') await csrfGuard(request, session);
  }
  if (path === '/api/session' && method === 'GET') return json({csrf: session.csrf});
  if (['/api/logout', '/api/driver/logout'].includes(path) && method === 'POST') {
    await query(db, 'DELETE FROM sessions WHERE token_hash=?', session.token_hash).run();
    const response = json({ok: true}); response.headers.set('Set-Cookie', 'haismrtpak_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0'); return response;
  }
  if (path === '/api/state' && method === 'GET') return json(publicState(await state(db)));
  if (path === '/api/driver/parking' && method === 'GET') {
    const s = publicState(await state(db)), visible = {};
    for (const key of ['slots', 'reserved', 'available', 'occupied', 'unknown', 'full', 'online', 'mode', 'updated_at', 'server_time']) visible[key] = s[key];
    return json({...visible, location: await location(db)});
  }
  if (['/api/driver/entry','/api/driver/exit'].includes(path) && method === 'POST') {
    if (typeof data.token !== 'string' || !/^[a-f0-9]{48}$/.test(data.token)) reject(400, 'Mã QR không hợp lệ. Vui lòng quét mã tại cổng.');
    const direction=path.endsWith('/exit')?'exit':'entry';
    const user = await query(db,'SELECT id,username,email FROM drivers WHERE id=?',session.driver_id).first();
    if (!user) reject(401, 'Vui lòng đăng nhập tài khoản người gửi xe.');
    const result = await mutate(db, (s,writes) => {
      const a=s[direction==='entry'?'arrival':'departure'];
      if (!online(s) || !s[direction+'_present'] || !a || a.used_by || a.expires_at<=now() || a.token!==data.token) reject(409, 'Mã QR đã hết hạn, đã dùng hoặc xe đã rời cổng. Vui lòng quét lại.');
      let assigned_slot=null;
      if(direction==='entry') {
        const existing=Object.entries(s.assignments||{}).find(([k,v])=>v.driver_id===user.id&&(v.expires_at==null||v.expires_at>now()));
        const previous=s.active_entries?.[user.id]||(existing?{slot:existing[0],expires_at:existing[1].expires_at}:null);
        if(previous&&(previous.expires_at==null||previous.expires_at>now()||s.slots[previous.slot]===true))return {error:'Bạn đã có chỗ tại ô '+previous.slot+'. Không được xác nhận vào bãi lần nữa. Vui lòng quét QR cổng ra khi rời bãi.'};
        s.assignments=Object.fromEntries(Object.entries(s.assignments||{}).filter(([k,v])=>(v.expires_at==null||v.expires_at>now())&&s.slots[k]===false));
        assigned_slot=slots.find(k=>s.slots[k]===false&&!s.assignments[k]);
        if(!assigned_slot)return {error:'Không còn ô trống để xếp xe. Vui lòng chờ.'};
      }
      const error=gate(writes,db,s,direction,'admin',true);
      if (error) return {error};
      if(assigned_slot)s.assignments[assigned_slot]={driver_id:user.id,expires_at:null};
      if(assigned_slot){s.active_entries??={};s.active_entries[user.id]={slot:assigned_slot,expires_at:null};}
      if(direction==='exit'&&s.active_entries?.[user.id]){delete s.assignments?.[s.active_entries[user.id].slot];delete s.active_entries[user.id];}
      if(s.mode==='simulation')s.auto_close_at=now()+8;
      a.used_by=user.id;
      a.confirmed_at=now();
      event(writes,db,'gate',`Tài khoản ${user.username||user.email} xác nhận ${direction==='entry'?'vào bãi':'ra bãi'} bằng QR.`,'admin');
      return {ok:true,assigned_slot,mode:s.mode,message:s.mode==='simulation'?'Đã mở thanh chắn mô phỏng.':'Đã xác nhận. Đang chờ ESP32 mở thanh chắn.'};
    });
    return json(result,result.error?409:200);
  }
  if (path === '/api/location') {
    if (method === 'GET') return json(await location(db));
    await query(db, 'UPDATE parking_location SET payload=? WHERE id=1', JSON.stringify(cleanLocation(data))).run(); return json({ok: true});
  }
  if (path === '/api/simulation' && method === 'POST') {
    if (!slots.includes(data.slot) || typeof data.occupied !== 'boolean') reject(400, 'Cần vị trí A1–A4 và trạng thái hợp lệ.');
    return json(await mutate(db, (s, writes) => {
      if (s.mode !== 'simulation') reject(409, 'Mô phỏng đã tắt trong chế độ phần cứng.');
      changeSlots(writes, db, s, {[data.slot]: data.occupied}, 'simulation');
    }));
  }
  if (path === '/api/mode' && method === 'POST') {
    if (!['simulation', 'hardware'].includes(data.mode)) reject(400, 'Chế độ không hợp lệ.');
    return json(await mutate(db, (s, writes) => {
      if (s.mode === data.mode) return;
      if (s.barrier !== 'closed' || s.command || s.pending_until > now()) reject(409, 'Đóng thanh chắn và chờ lượt vào kết thúc trước khi đổi chế độ.');
      writes.push(query(db, 'UPDATE visits SET exited_at=? WHERE exited_at IS NULL', now()));
      Object.assign(s, initial(data.mode));
      event(writes, db, 'mode', `Chuyển sang ${data.mode === 'hardware' ? 'phần cứng' : 'mô phỏng'}; kết thúc phiên đỗ cũ.`, 'admin');
    }));
  }
  if (['/api/gate', '/api/device/gate'].includes(path) && method === 'POST') {
    const result = await mutate(db, (s, writes) => {
      if (device && s.mode !== 'hardware') reject(409, 'Chưa bật chế độ phần cứng.');
      const error = gate(writes, db, s, data.action, device ? 'device' : 'admin');
      return error ? {error} : device ? {command: s.command} : publicState(s);
    });
    return json(result, result.error ? 409 : 200);
  }
  if (path === '/api/device/telemetry' && method === 'POST') {
    if (!data.slots || typeof data.slots !== 'object' || Object.keys(data.slots).length !== 4 || !slots.every(k => Object.hasOwn(data.slots, k) && [true, false, null].includes(data.slots[k]))) reject(400, 'Dữ liệu phải chứa đủ A1–A4 với trạng thái hợp lệ.');
    if (!Number.isSafeInteger(data.sequence) || data.sequence < 0 || typeof data.boot_id !== 'string' || data.boot_id.length < 1 || data.boot_id.length > 64) reject(400, 'Số thứ tự gói tin hoặc mã phiên khởi động không hợp lệ.');
    if (!['open', 'closed'].includes(data.barrier) || typeof data.beam !== 'boolean') reject(400, 'Cần trạng thái thanh chắn và cảm biến vật cản hợp lệ.');
    if (['entry_present','exit_present'].some(k => data[k] !== undefined && typeof data[k] !== 'boolean')) reject(400, 'Trạng thái cảm biến xe đến không hợp lệ.');
    return json(await mutate(db, (s, writes) => {
      if (s.mode !== 'hardware') reject(409, 'Máy chủ đang ở chế độ mô phỏng.');
      if (s.boot_id === data.boot_id && data.sequence <= s.sequence) reject(409, 'Gói tin trùng hoặc sai thứ tự.');
      changeSlots(writes, db, s, data.slots, 'device');
      if (!online(s) || s.boot_id!==data.boot_id) {arrivalUpdate(s,false);arrivalUpdate(s,false,'exit');}
      arrivalUpdate(s,data.entry_present ?? false);
      arrivalUpdate(s,data.exit_present ?? false,'exit');
      barrierUpdate(s,data.barrier);
      Object.assign(s, {last_seen: now(), boot_id: data.boot_id, sequence: data.sequence, beam: data.beam});
      if (s.command && (data.ack === s.command.id || s.command.expires_at < now())) {
        const ack = data.ack === s.command.id;
        event(writes, db, ack ? 'ack' : 'expired', ack ? 'Thiết bị xác nhận lệnh' : 'Lệnh hết hạn', 'device'); s.command = null;
      }
      return {command: s.command, available: publicState(s).available, server_time: now()};
    }));
  }
  if (['/api/events', '/api/events/export'].includes(path) && method === 'GET') {
    const conditions = [], args = [], kind = url.searchParams.get('kind'), date = url.searchParams.get('date');
    if (kind) { conditions.push('kind=?'); args.push(kind); }
    if (date) {
      const start = Date.parse(`${date}T00:00:00+07:00`) / 1000;
      if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !Number.isFinite(start) || new Date((start + 25200) * 1000).toISOString().slice(0, 10) !== date) reject(400, 'Ngày phải có dạng năm-tháng-ngày hợp lệ.');
      conditions.push('timestamp>=? AND timestamp<?'); args.push(start, start + 86400);
    }
    const where = conditions.length ? ' WHERE ' + conditions.join(' AND ') : '';
    if (path.endsWith('/export')) {
      const {results} = await query(db, 'SELECT * FROM events' + where + ' ORDER BY id DESC LIMIT 10000', ...args).all();
      const kinds = {occupied:'Vị trí có xe',vacated:'Vị trí trống',gate:'Điều khiển cổng',denied:'Từ chối xe vào',mode:'Đổi chế độ',ack:'Xác nhận lệnh',expired:'Lệnh hết hạn'};
      const sources = {simulation:'Mô phỏng',device:'Thiết bị ESP32',admin:'Quản trị'};
      const rows = [['Mã sự kiện','Thời gian (+07:00)','Loại','Vị trí','Nguồn','Nội dung'], ...results.map(e => [e.id,new Date(e.timestamp*1000).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}),kinds[e.kind]||e.kind,e.slot,sources[e.source]||e.source,e.message])];
      return new Response('\ufeff' + rows.map(row => row.map(v => '"' + String(v).replaceAll('"','""') + '"').join(',')).join('\r\n'), {headers:{'Content-Type':'text/csv; charset=utf-8','Content-Disposition':'attachment; filename=parking-events.csv'}});
    }
    const pageText = url.searchParams.get('page') || '1';
    if (!/^-?\d+$/.test(pageText) || !Number.isSafeInteger(Number(pageText))) reject(400, 'Số trang phải là một số nguyên hợp lệ.');
    const page = Math.max(1, Number(pageText));
    const [count, items] = await db.batch([query(db, 'SELECT COUNT(*) AS total FROM events' + where, ...args),query(db, 'SELECT * FROM events' + where + ' ORDER BY id DESC LIMIT 20 OFFSET ?', ...args, (page-1)*20)]);
    const total = count.results[0].total;
    await Promise.all(items.results.map(async e=>{
      const match=/^Tài khoản #(\d+) xác nhận (entry|exit|vào bãi|ra bãi) bằng QR\.$/.exec(e.message);
      if(match){const driver=await query(db,'SELECT username,email FROM drivers WHERE id=?',Number(match[1])).first();if(driver)e.message=`Tài khoản ${driver.username||driver.email} xác nhận ${['entry','vào bãi'].includes(match[2])?'vào bãi':'ra bãi'} bằng QR.`;}
    }));
    return json({items:items.results,total,page,pages:Math.max(1,Math.ceil(total/20))});
  }
  if (path === '/api/stats' && method === 'GET') {
    const today = Math.floor((now()+25200)/86400)*86400-25200, days = [];
    const statements = [];
    for (let i=6;i>=0;i--) {
      const start=today-i*86400;
      statements.push(query(db,'SELECT (SELECT COUNT(*) FROM visits WHERE entered_at>=? AND entered_at<?) AS arrivals,(SELECT COUNT(*) FROM visits WHERE exited_at>=? AND exited_at<?) AS departures',start,start+86400,start,start+86400));
      days.push({date:new Date((start+25200)*1000).toISOString().slice(5,10).split('-').reverse().join('/')});
    }
    statements.push(query(db,'SELECT AVG(exited_at-entered_at) AS duration FROM visits WHERE exited_at IS NOT NULL'));
    const result=await db.batch(statements);
    return json({days:days.map((day,i)=>({...day,...result[i].results[0]})),average_minutes:Math.round((result[7].results[0].duration||0)/6)/10});
  }
  reject(404, 'Không tìm thấy chức năng.');
}
export default {
  async fetch(request, env) {
    let response;
    const path = new URL(request.url).pathname;
    try {
      response = path.startsWith('/api/') ? await api(request, env) : await env.ASSETS.fetch(request);
    } catch (e) {
      if (!(e instanceof HTTPError)) console.error('Request failed', e.message);
      response = json({error: e instanceof HTTPError ? e.message : 'Máy chủ chưa xử lý được yêu cầu. Vui lòng thử lại.'}, e.status || 500);
    }
    response = new Response(response.body, response);
    response.headers.set('X-Content-Type-Options','nosniff');
    response.headers.set('X-Frame-Options','DENY');
    response.headers.set('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'");
    if (path.startsWith('/api/')) response.headers.set('Cache-Control','no-store');
    if (path === '/driver/sw.js') response.headers.set('Cache-Control','no-cache');
    return response;
  }
};
