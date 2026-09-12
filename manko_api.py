import os
import hashlib
from urllib.parse import urlparse
import manko_api_v2 as core
from film4k_addon import register_film4k_addon


def _is_supported_movie_url(value):
    url = str(value or '').strip()
    if url.startswith('https://manko.fun/movie-info/'):
        return True
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower().split(':', 1)[0]
        return parsed.scheme == 'https' and host in {'film4k.net', 'www.film4k.net'} and parsed.path not in {'', '/'}
    except Exception:
        return False


def _movie_key(payload):
    url = str((payload or {}).get('movieUrl') or '')
    try:
        host = urlparse(url).netloc.lower().split(':', 1)[0]
    except Exception:
        host = ''
    prefix = 'movie_film4k_' if host in {'film4k.net', 'www.film4k.net'} else 'movie_manko_'
    return prefix + hashlib.sha1(url.encode()).hexdigest()[:16]


# Reuse the complete Manko queue/runner/collector/Neon pipeline. Only widen
# source validation and IDs so Film4K can enter the same machinery safely.
core.is_movie_url = _is_supported_movie_url
core.movie_key = _movie_key

app = core.app
register_film4k_addon(app, core.load_store)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '10000')))
