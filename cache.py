"""A small in-memory response cache, so repeated calls for the same product
or listing don't hit Trendyol again within the TTL. It lives in this process
only and empties on restart.

    cached_call(namespace, data, fn, ttl)  ->  fn(**data), served from memory
                                               for `ttl` (a timedelta)
"""
import json
import threading
import time

MAX_ENTRIES = 1000

_lock = threading.Lock()
_store = {}   # key -> (expires_at, json text)


def _key(namespace, data):
    return namespace + "\n" + json.dumps(data, sort_keys=True, default=str, ensure_ascii=False)


def cached_call(namespace, data, fn, ttl):
    key = _key(namespace, data)
    now = time.monotonic()
    with _lock:
        hit = _store.get(key)
        if hit and hit[0] > now:
            # a fresh copy every time: callers may change the dict they get
            return json.loads(hit[1])
    result = fn(**data)
    seconds = ttl.total_seconds() if ttl else 0
    if seconds > 0:
        with _lock:
            if len(_store) >= MAX_ENTRIES:
                for stale in [k for k, (exp, _) in _store.items() if exp <= now] or list(_store)[:MAX_ENTRIES // 10]:
                    _store.pop(stale, None)
            _store[key] = (now + seconds, json.dumps(result, ensure_ascii=False))
    return json.loads(json.dumps(result, ensure_ascii=False))
