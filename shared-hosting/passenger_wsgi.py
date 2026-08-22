import hmac
import urllib.error
import urllib.request

from relay_config import BACKEND_BASE, BACKEND_TOKEN, PUBLIC_TOKEN

MAX_BODY = 1024 * 1024


def response(start_response, status, body=b"", content_type="application/octet-stream"):
    start_response(status, [
        ("Content-Type", content_type),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "no-store"),
    ])
    return [body]


def application(environ, start_response):
    if not hmac.compare_digest(environ.get("HTTP_X_RELAY_KEY", ""), PUBLIC_TOKEN):
        return response(start_response, "403 Forbidden")
    path = environ.get("PATH_INFO", "/")
    query = environ.get("QUERY_STRING", "")
    target = BACKEND_BASE + path + (("?" + query) if query else "")
    method = environ.get("REQUEST_METHOD", "GET")
    try:
        length = int(environ.get("CONTENT_LENGTH") or "0")
    except ValueError:
        return response(start_response, "400 Bad Request")
    if length < 0 or length > MAX_BODY:
        return response(start_response, "413 Payload Too Large")
    body = environ["wsgi.input"].read(length) if length else None
    headers = {"Authorization": "Bearer " + BACKEND_TOKEN, "Cache-Control": "no-store"}
    if environ.get("CONTENT_TYPE"):
        headers["Content-Type"] = environ["CONTENT_TYPE"]
    request = urllib.request.Request(target, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=35) as upstream:
            payload = upstream.read(MAX_BODY + 1)
            if len(payload) > MAX_BODY:
                return response(start_response, "502 Bad Gateway")
            return response(start_response, f"{upstream.status} OK", payload,
                            upstream.headers.get("Content-Type", "application/octet-stream"))
    except urllib.error.HTTPError as exc:
        return response(start_response, f"{exc.code} Upstream", exc.read(MAX_BODY),
                        exc.headers.get("Content-Type", "application/octet-stream"))
    except Exception:
        return response(start_response, "502 Bad Gateway")
