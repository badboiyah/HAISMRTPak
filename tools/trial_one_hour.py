"""Run a free temporary HTTPS tunnel and close only that tunnel after one hour."""
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime'
status_path = RUNTIME / 'trial-status.json'
start = datetime.now(timezone.utc)
status = {'started_at': start.isoformat(), 'expires_at': (start + timedelta(hours=1)).isoformat(),
          'state': 'starting', 'origin': 'http://127.0.0.1:5000'}

def save():
    status_path.write_text(json.dumps(status, indent=2), encoding='utf-8')

with (RUNTIME / 'trial-tunnel.log').open('w', encoding='utf-8') as log:
    process = subprocess.Popen([
        str(RUNTIME / 'cloudflared.exe'), 'tunnel', '--no-autoupdate',
        '--url', status['origin'], '--protocol', 'http2',
    ], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
       creationflags=subprocess.CREATE_NO_WINDOW)
    status.update(state='running', tunnel_pid=process.pid)
    save()
    try:
        process.wait(timeout=3600)
        status.update(state='stopped', exit_code=process.returncode)
    except subprocess.TimeoutExpired:
        process.terminate()
        process.wait(timeout=15)
        status.update(state='expired', exit_code=process.returncode)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        status['stopped_at'] = datetime.now(timezone.utc).isoformat()
        save()
