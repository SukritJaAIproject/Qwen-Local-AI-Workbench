"""General public-web search through pinned DDGS and the Windows DNS resolver."""
from __future__ import annotations

import html
import re
import time
import threading
from collections import OrderedDict
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode


class SearchUnavailable(RuntimeError):
    pass


_CLIENT_LOCK = threading.Lock()
_CLIENT_READY = False
_CACHE_LOCK = threading.Lock()
_CACHE = OrderedDict()
_STATE_LOCK = threading.Lock()
_COOLDOWNS = {}
_SEARCH_SLOTS = threading.BoundedSemaphore(4)
_GENERAL_BACKENDS = {'brave', 'bing', 'duckduckgo', 'google', 'yahoo', 'mojeek', 'startpage', 'yandex'}


def _prepare_client():
    global _CLIENT_READY
    with _CLIENT_LOCK:
        if _CLIENT_READY:
            return
        import primp
        import ddgs.base
        from ddgs.http_client import HttpClient

        class WindowsDNSHttpClient(HttpClient):
            def __init__(self, proxy=None, timeout=6, *, verify=True):
                # Primp's default resolver returns Query Refused on some Windows
                # networks. Its supported system resolver uses normal OS DNS;
                # TLS verification remains enabled and vendor files stay intact.
                self.client = primp.Client(proxy=proxy, timeout=timeout,
                    impersonate='random', impersonate_os='windows',
                    verify=True, dns_resolver='system')

            def request(self, *args, **kwargs):
                response = super().request(*args, **kwargs)
                if response.status_code >= 400 or response.status_code == 202:
                    raise SearchUnavailable('Search engine refused the request (HTTP %d)' % response.status_code)
                return response

        ddgs.base.HttpClient = WindowsDNSHttpClient
        _CLIENT_READY = True


def _domains(value):
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or len(value) > 5:
        raise ValueError('domains must be a list of at most 5 hostnames')
    values = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError('domain must be a hostname')
        name = item.strip().lower().rstrip('.')
        try:
            name = name.encode('idna').decode('ascii')
        except UnicodeError as error:
            raise ValueError('invalid domain') from error
        if len(name) > 253 or not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,62}', name):
            raise ValueError('domain must contain only a public hostname, without URL/path/query')
        if name not in values:
            values.append(name)
    return tuple(values)


def scope(query, domains=None, recency_days=None, region=None, search_type='web', page=1):
    if not isinstance(query, str) or not query.strip() or len(query) > 2000:
        raise ValueError('query must be 1-2000 characters')
    query = query.strip()
    hosts = _domains(domains)
    if search_type not in ('web', 'news'):
        raise ValueError('search_type must be web or news')
    if not isinstance(page, int) or isinstance(page, bool) or not 1 <= page <= 5:
        raise ValueError('page must be 1-5')
    if region is None:
        region = 'th-th' if re.search(r'[\u0e00-\u0e7f]', query) else 'us-en'
    if not isinstance(region, str) or not re.fullmatch(r'[a-z]{2}-[a-z]{2}', region):
        raise ValueError('region must look like th-th or us-en')
    timelimit = None
    window = None
    if recency_days is not None:
        if not isinstance(recency_days, int) or isinstance(recency_days, bool) or not 1 <= recency_days <= 365:
            raise ValueError('recency_days must be 1-365')
        timelimit, window = next((tag, days) for tag, days in [('d', 1), ('w', 7), ('m', 31), ('y', 365)] if recency_days <= days)
    if len(hosts) == 1:
        query += ' site:' + hosts[0]
    elif hosts:
        query += ' (' + ' OR '.join('site:' + host for host in hosts) + ')'
    return {'query': query, 'domains': hosts, 'region': region, 'timelimit': timelimit,
            'window_days': window, 'search_type': search_type, 'page': page}


def _clean(row):
    if not isinstance(row, dict):
        return None
    url = row.get('href') or row.get('url') or ''
    if not isinstance(url, str):
        return None
    try:
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
            return None
        clean_query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                       if not k.lower().startswith('utm_') and k.lower() not in ('fbclid', 'gclid', 'msclkid')]
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(clean_query), parts.fragment))
    except ValueError:
        return None
    def text(value, limit):
        return re.sub(r'\s+', ' ', html.unescape(str(value or ''))).strip()[:limit]
    title = text(row.get('title'), 240)
    body = text(row.get('body') or row.get('description'), 700)
    if row.get('date'):
        body = 'Published: ' + text(row['date'], 64) + ' · ' + body
    return (title or parts.hostname, url, body)


def _available_engines(search_type):
    from ddgs.engines import ENGINES
    # Disabled backends must never reach DDGS: an unavailable explicit backend
    # silently falls back to auto there, which includes encyclopedia backends.
    return ENGINES['news' if search_type == 'news' else 'text']


def _query_engine(engine, request, count, timeout):
    from ddgs import DDGS
    client = DDGS(timeout=timeout, verify=True)
    client._proxy = None  # Preserve the service's no-environment-proxy policy.
    method = client.news if request['search_type'] == 'news' else client.text
    return method(request['query'], region=request['region'], safesearch='moderate',
        timelimit=request['timelimit'], max_results=count, page=request['page'], backend=engine)


def _search_engines(engines, request, n, timeout):
    available = _available_engines(request['search_type'])
    engines = list(dict.fromkeys(engine for engine in engines if engine in available))
    if not engines:
        raise SearchUnavailable('No configured general search engines are available; check backends in config.json.')
    hits, seen, attempted, failed, status = [], set(), [], [], {}
    empty = False
    deadline = time.monotonic() + 30
    count = min(36, n * 3) if request['domains'] else n
    for engine in engines:
        with _STATE_LOCK:
            if _COOLDOWNS.get((request['search_type'], engine), 0) > time.monotonic():
                continue
        remaining = int(deadline - time.monotonic())
        if remaining < 2:
            break
        attempted.append(engine)
        try:
            # Isolate each engine so one fast failure cannot discard another
            # engine's pending results in the upstream aggregation loop.
            rows = _query_engine(engine, request, count, min(timeout, remaining))
            status[engine] = 'results:' + str(len(rows))
        except Exception as error:
            if str(error).strip().lower() in ('no results found.', 'no results found'):
                rows = []
                status[engine] = 'no_results'
            else:
                failed.append(engine)
                reason = str(error).lower()
                code = re.search(r'http (\d{3})', reason)
                status[engine] = 'http:' + code.group(1) if code else type(error).__name__
                if any(tag in reason for tag in ('429', '403', '202', 'timed out', 'timeout')):
                    with _STATE_LOCK:
                        _COOLDOWNS[(request['search_type'], engine)] = time.monotonic() + 120
                continue
        empty = True
        for row in rows:
            hit = _clean(row)
            if hit is None:
                continue
            host = urlsplit(hit[1]).hostname.lower()
            if request['domains'] and not any(host == d or host.endswith('.' + d) for d in request['domains']):
                continue
            canonical = hit[1].split('#', 1)[0].rstrip('/')
            if canonical in seen:
                continue
            seen.add(canonical)
            hits.append(hit)
            if len(hits) == n:
                break
        if len(hits) == n:
            break
    if not hits and not empty:
        raise SearchUnavailable('General web search is temporarily unavailable or rate-limited. '
            'Try another query or retry after two minutes; no encyclopedia fallback was substituted.')
    request['engines_attempted'] = attempted
    request['engines_failed'] = failed
    request['engine_status'] = status
    return hits


def search(cfg, query, n, *, domains=None, recency_days=None, region=None, search_type='web', page=1):
    request = scope(query, domains, recency_days, region, search_type, page)
    engines = cfg.get('backends') or ['yahoo', 'duckduckgo', 'brave', 'google', 'mojeek']
    if isinstance(engines, str):
        engines = [x.strip() for x in engines.split(',')]
    if not isinstance(engines, list) or not engines or len(engines) > 8 or any(x not in _GENERAL_BACKENDS for x in engines):
        raise ValueError('backends must list supported general search engines; auto/Wikipedia are not used')
    if search_type == 'news':
        engines = cfg.get('news_backends') or ['bing', 'yahoo', 'duckduckgo']
        if not isinstance(engines, list) or not engines or any(x not in ('bing', 'duckduckgo', 'yahoo') for x in engines):
            raise ValueError('news_backends must list bing, duckduckgo or yahoo')
    timeout = max(2, min(10, int(cfg.get('timeout_seconds') or 6)))
    key = (request['query'], request['domains'], request['region'], request['timelimit'], search_type, page, n, tuple(engines))
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached and now - cached[0] < 60:
            _CACHE.move_to_end(key)
            return list(cached[1]), request
    if not _SEARCH_SLOTS.acquire(timeout=5):
        raise SearchUnavailable('General search is busy; retry shortly.')
    try:
        _prepare_client()
        hits = _search_engines(engines, request, n, timeout)
    finally:
        _SEARCH_SLOTS.release()
    with _CACHE_LOCK:
        _CACHE[key] = (time.monotonic(), tuple(hits))
        _CACHE.move_to_end(key)
        while len(_CACHE) > 128:
            _CACHE.popitem(last=False)
    return hits, request
