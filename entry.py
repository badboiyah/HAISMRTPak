"""Arrival challenges for a paired gate tablet. Challenges never grant access alone."""
import secrets
import time


def arrival_update(state, present):
    if present and not state.get('entry_present', False):
        state['arrival'] = dict(token=secrets.token_hex(24), expires_at=time.time()+120, used_by=None)
    if not present:
        state['arrival'] = None
    state['entry_present'] = present


def kiosk_status(state, online):
    arrival = state.get('arrival')
    ready = online and state.get('entry_present', False)
    return dict(mode=state['mode'], online=online, present=bool(ready),
                token=arrival['token'] if ready and arrival and not arrival['used_by'] and arrival['expires_at'] > time.time() else None,
                expires_at=arrival['expires_at'] if ready and arrival else None,
                confirmed=bool(ready and arrival and arrival['used_by']),
                barrier=state['barrier'] if online else 'unknown',
                server_time=time.time())
