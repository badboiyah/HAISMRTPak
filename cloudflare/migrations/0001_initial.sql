CREATE TABLE parking_state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 0);
INSERT INTO parking_state(id,payload) VALUES(1,'{"mode":"simulation","slots":{"A1":false,"A2":false,"A3":false,"A4":false},"updated_at":null,"last_seen":null,"boot_id":null,"sequence":-1,"barrier":"closed","beam":false,"command":null,"pending_until":0}');
CREATE TABLE events(id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL NOT NULL, kind TEXT NOT NULL, slot TEXT NOT NULL, source TEXT NOT NULL, message TEXT NOT NULL);
CREATE INDEX events_timestamp ON events(timestamp);
CREATE TABLE visits(id INTEGER PRIMARY KEY AUTOINCREMENT, slot TEXT NOT NULL, entered_at REAL NOT NULL, exited_at REAL, source TEXT NOT NULL);
CREATE UNIQUE INDEX active_slot ON visits(slot) WHERE exited_at IS NULL;
CREATE INDEX visits_entered ON visits(entered_at);
CREATE INDEX visits_exited ON visits(exited_at);
CREATE TABLE drivers(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE parking_location(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL);
INSERT INTO parking_location VALUES(1,'{"name":"Bãi xe HAISMRTPak","address":"","latitude":null,"longitude":null,"hours":""}');
CREATE TABLE sessions(token_hash TEXT PRIMARY KEY, role TEXT NOT NULL, driver_id INTEGER REFERENCES drivers(id), csrf TEXT NOT NULL, expires_at REAL NOT NULL);
CREATE INDEX session_expiry ON sessions(expires_at);
CREATE TABLE rate_limits(key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires_at REAL NOT NULL);
CREATE INDEX rate_expiry ON rate_limits(expires_at);
-- An assertion in the same D1 batch makes a stale state read roll back every write.
CREATE TABLE write_guard(id TEXT PRIMARY KEY, valid INTEGER NOT NULL CHECK(valid=1));
