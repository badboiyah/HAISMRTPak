ALTER TABLE drivers ADD COLUMN username TEXT;
CREATE UNIQUE INDEX drivers_username_unique ON drivers(username);
