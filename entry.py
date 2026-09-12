"""Arrival challenges for a paired gate tablet. Challenges never grant access alone."""
import secrets
import time


def barrier_update(state, barrier):
    if state['barrier'] == 'open' and barrier == 'closed':
        for direction, key in [('entry', 'arrival'), ('exit', 'departure')]:
            challenge = state.get(key)
            if state.get(direction + '_present') and challenge and challenge.get('used_by'):
                state[direction + '_present'] = False
                arrival_update(state, True, direction)
    state['barrier'] = barrier


def arrival_update(state, present, direction="entry"):
    key = "arrival" if direction == "entry" else "departure"
    present_key = direction + "_present"
    if present and not state.get(present_key, False):
        state[key] = dict(token=secrets.token_hex(24), expires_at=time.time()+120, used_by=None)
    if not present:
        state[key] = None
    state[present_key] = present


def kiosk_status(state, online, direction="entry"):
    key = "arrival" if direction == "entry" else "departure"
    present_key = direction + "_present"
    arrival = state.get(key)
    ready = online and state.get(present_key, False)
    return dict(direction=direction, mode=state['mode'], online=online, present=bool(ready),
                token=arrival['token'] if ready and arrival and not arrival['used_by'] and arrival['expires_at'] > time.time() else None,
                expires_at=arrival['expires_at'] if ready and arrival else None,
                confirmed=bool(ready and arrival and arrival['used_by']),
                barrier=state['barrier'] if online else 'unknown',
                server_time=time.time())
