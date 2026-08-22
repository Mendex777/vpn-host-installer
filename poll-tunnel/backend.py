#!/usr/bin/env python3
import hmac
import json
import os
import secrets
import select
import socket
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

AUTH_TOKEN = os.environ["POLL_BACKEND_TOKEN"]
MAX_BODY = 1024 * 1024
MUX_HEADER = 37  # 32-byte hex session id, 1-byte flags, 4-byte payload length.
sessions = {}
sessions_lock = threading.Lock()


class Session:
    def __init__(self, sock):
        self.sock = sock
        self.send_lock = threading.Lock()
        self.touched = time.monotonic()

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def remove_session(sid):
    with sessions_lock:
        session = sessions.pop(sid, None)
    if session:
        session.close()


class Handler(BaseHTTPRequestHandler):
    server_version = "poll-backend/1"

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {fmt % args}", flush=True)

    def authorized(self):
        supplied = self.headers.get("Authorization", "")
        return hmac.compare_digest(supplied, "Bearer " + AUTH_TOKEN)

    def send_bytes(self, status, payload=b"", content_type="application/octet-stream"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD" and payload:
            self.wfile.write(payload)

    def read_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > MAX_BODY:
            raise ValueError("invalid body size")
        return self.rfile.read(length)

    def get_session(self, sid):
        with sessions_lock:
            session = sessions.get(sid)
        if session:
            session.touched = time.monotonic()
        return session

    def do_GET(self):
        if not self.authorized():
            return self.send_bytes(403)
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/health":
            payload = json.dumps({"status": "ok", "sessions": len(sessions)}).encode()
            return self.send_bytes(200, payload, "application/json")
        if parsed.path == "/mux/down":
            query = urllib.parse.parse_qs(parsed.query)
            wait = min(max(float(query.get("wait", ["10"])[0]), 0.1), 20.0)
            with sessions_lock:
                snapshot = [(sid, session) for sid, session in sessions.items()]
            if not snapshot:
                time.sleep(min(wait, 0.25))
                return self.send_bytes(204)
            by_socket = {session.sock: (sid, session) for sid, session in snapshot}
            try:
                readable, _, _ = select.select(list(by_socket), [], [], wait)
            except (OSError, ValueError):
                return self.send_bytes(204)
            if not readable:
                return self.send_bytes(204)
            framed = bytearray()
            for sock in readable:
                sid, session = by_socket[sock]
                room = MAX_BODY - len(framed) - MUX_HEADER
                if room <= 0:
                    break
                flags = 0
                try:
                    data = sock.recv(min(room, 262144))
                    if not data:
                        flags = 1
                        remove_session(sid)
                except OSError:
                    data = b""
                    flags = 1
                    remove_session(sid)
                session.touched = time.monotonic()
                framed += sid.encode("ascii")
                framed.append(flags)
                framed += len(data).to_bytes(4, "big")
                framed += data
            return self.send_bytes(200 if framed else 204, bytes(framed))
        parts = parsed.path.strip("/").split("/")
        if len(parts) != 2 or parts[0] != "down":
            return self.send_bytes(404)
        sid = parts[1]
        session = self.get_session(sid)
        if not session:
            return self.send_bytes(404)
        query = urllib.parse.parse_qs(parsed.query)
        wait = min(max(float(query.get("wait", ["10"])[0]), 0.1), 20.0)
        size = min(max(int(query.get("max", ["262144"])[0]), 1), MAX_BODY)
        try:
            readable, _, _ = select.select([session.sock], [], [], wait)
            if not readable:
                return self.send_bytes(204)
            data = session.sock.recv(size)
            if not data:
                remove_session(sid)
                return self.send_bytes(410)
            return self.send_bytes(200, data)
        except OSError:
            remove_session(sid)
            return self.send_bytes(410)

    def do_POST(self):
        if not self.authorized():
            return self.send_bytes(403)
        parsed = urllib.parse.urlsplit(self.path)
        try:
            body = self.read_body()
        except (ValueError, TypeError):
            return self.send_bytes(413)
        if parsed.path == "/open":
            try:
                request = json.loads(body)
                host = str(request["host"])
                port = int(request["port"])
                if not host or not (1 <= port <= 65535):
                    raise ValueError
                sock = socket.create_connection((host, port), timeout=10)
                sock.settimeout(None)
            except Exception:
                return self.send_bytes(502)
            sid = secrets.token_hex(16)
            with sessions_lock:
                sessions[sid] = Session(sock)
            payload = json.dumps({"session": sid}).encode()
            return self.send_bytes(201, payload, "application/json")
        parts = parsed.path.strip("/").split("/")
        if len(parts) != 2 or parts[0] != "up":
            return self.send_bytes(404)
        sid = parts[1]
        session = self.get_session(sid)
        if not session:
            return self.send_bytes(404)
        try:
            with session.send_lock:
                session.sock.sendall(body)
            return self.send_bytes(204)
        except OSError:
            remove_session(sid)
            return self.send_bytes(410)

    def do_DELETE(self):
        if not self.authorized():
            return self.send_bytes(403)
        parts = urllib.parse.urlsplit(self.path).path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "close":
            remove_session(parts[1])
            return self.send_bytes(204)
        return self.send_bytes(404)


ThreadingHTTPServer(("127.0.0.1", 18080), Handler).serve_forever()
