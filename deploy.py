#!/usr/bin/env python3
"""Deploy the polling relay to a root VPS and REG.RU shared hosting."""

import argparse
import ftplib
import getpass
import io
import os
from pathlib import Path
import re
import secrets
import shlex
import socket
import sys
import time
import tomllib
import urllib.request

import paramiko

ROOT = Path(__file__).resolve().parent
DOMAIN_RE = re.compile(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{24,128}$")


def required(section, name):
    value = str(section.get(name, "")).strip()
    if not value:
        raise SystemExit(f"Missing required setting: {name}")
    return value


def secret_value(section, name, prompt):
    value = str(section.get(name, "")).strip()
    return value or getpass.getpass(prompt)


def validate_domain(value):
    value = value.lower().rstrip(".")
    if not DOMAIN_RE.fullmatch(value):
        raise SystemExit(f"Invalid DNS domain: {value}")
    return value


def validate_token(name, value):
    if not TOKEN_RE.fullmatch(value):
        raise SystemExit(f"{name} must contain 24-128 URL-safe characters")
    return value


def run(ssh, command):
    print(f"  VPS: {command}")
    _, stdout, stderr = ssh.exec_command(command, get_pty=False)
    code = stdout.channel.recv_exit_status()
    output = stdout.read().decode(errors="replace")
    error = stderr.read().decode(errors="replace")
    if output.strip():
        print(output.rstrip())
    if code:
        raise RuntimeError(f"VPS command failed ({code}): {error.strip()}")


def upload_text(sftp, remote, content, mode=0o644):
    temporary = remote + ".new"
    with sftp.file(temporary, "wb") as handle:
        handle.write(content.encode("utf-8"))
    sftp.chmod(temporary, mode)


def nginx_http(domain):
    return f"""server {{
    listen 80;
    listen [::]:80;
    server_name {domain};
    location ^~ /.well-known/acme-challenge/ {{ root /var/www/poll-acme; }}
    location / {{ return 404; }}
}}
"""


def nginx_https(domain, path_token):
    return f"""server {{
    listen 80;
    listen [::]:80;
    server_name {domain};
    location ^~ /.well-known/acme-challenge/ {{ root /var/www/poll-acme; }}
    location / {{ return 301 https://$host$request_uri; }}
}}

server {{
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name {domain};
    ssl_certificate /etc/letsencrypt/live/{domain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location ^~ /poll-tunnel/{path_token}/ {{
        proxy_pass http://127.0.0.1:18080/;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_cache off;
        client_max_body_size 1m;
        proxy_connect_timeout 5s;
        proxy_read_timeout 40s;
        proxy_send_timeout 40s;
        add_header Cache-Control "no-store" always;
    }}
    location / {{ return 404; }}
}}
"""


def ftp_mkdirs(ftp, path):
    current = ""
    for part in path.strip("/").split("/"):
        current += "/" + part
        try:
            ftp.mkd(current)
        except ftplib.error_perm as exc:
            if not str(exc).startswith("550"):
                raise


def ftp_upload(ftp, remote, content):
    ftp.storbinary("STOR " + remote, io.BytesIO(content.encode()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.toml")
    args = parser.parse_args()
    config_path = Path(args.config)
    with config_path.open("rb") as handle:
        cfg = tomllib.load(handle)
    vps, shared, relay = cfg["vps"], cfg["shared"], cfg.get("relay", {})
    secrets_file = config_path.with_name("deployment-secrets.toml")
    saved_relay = {}
    if secrets_file.exists():
        with secrets_file.open("rb") as handle:
            saved_relay = tomllib.load(handle).get("relay", {})

    vps_host = required(vps, "host")
    vps_user = required(vps, "user")
    domain = validate_domain(required(vps, "domain"))
    email = required(vps, "acme_email")
    relay_domain = validate_domain(required(shared, "relay_domain"))
    public_token = validate_token("public_token", str(relay.get("public_token", "")).strip() or str(saved_relay.get("public_token", "")).strip() or secrets.token_hex(32))
    backend_token = validate_token("backend_token", str(relay.get("backend_token", "")).strip() or str(saved_relay.get("backend_token", "")).strip() or secrets.token_hex(32))
    path_token = validate_token("path_token", str(relay.get("path_token", "")).strip() or str(saved_relay.get("path_token", "")).strip() or secrets.token_hex(32))
    vps_password = secret_value(vps, "password", "VPS SSH password: ")
    ftp_password = secret_value(shared, "ftp_password", "Shared-hosting FTP password: ")

    secrets_file.write_text(
        "[relay]\n"
        f'public_token = "{public_token}"\n'
        f'backend_token = "{backend_token}"\n'
        f'path_token = "{path_token}"\n', encoding="utf-8")
    try:
        os.chmod(secrets_file, 0o600)
    except OSError:
        pass

    print("Connecting to VPS...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(vps_host, port=int(vps.get("port", 22)), username=vps_user,
                password=vps_password, timeout=20, look_for_keys=False)
    sftp = ssh.open_sftp()
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    run(ssh, "apt-get update -qq && apt-get install -y -qq nginx certbot python3 ca-certificates")
    run(ssh, "mkdir -p /opt/poll-tunnel /etc/poll-tunnel /var/www/poll-acme")

    backend = (ROOT / "poll-tunnel/backend.py").read_text(encoding="utf-8")
    service = (ROOT / "poll-tunnel/poll-backend.service.example").read_text(encoding="utf-8")
    upload_text(sftp, "/tmp/poll-backend.py", backend)
    upload_text(sftp, "/tmp/poll-backend.env", f"POLL_BACKEND_TOKEN={backend_token}\n", 0o600)
    upload_text(sftp, "/tmp/poll-backend.service", service)
    run(ssh, f"test ! -e /opt/poll-tunnel/backend.py || cp -a /opt/poll-tunnel/backend.py /opt/poll-tunnel/backend.py.{timestamp}.bak")
    run(ssh, "install -m 0644 /tmp/poll-backend.py /opt/poll-tunnel/backend.py && "
             "install -m 0600 /tmp/poll-backend.env /etc/poll-tunnel/backend.env && "
             "install -m 0644 /tmp/poll-backend.service /etc/systemd/system/poll-backend.service")
    run(ssh, "systemctl daemon-reload && systemctl enable poll-backend && systemctl restart poll-backend")

    upload_text(sftp, "/tmp/poll-relay-nginx.conf", nginx_http(domain))
    run(ssh, f"test ! -e /etc/nginx/sites-available/poll-relay.conf || cp -a /etc/nginx/sites-available/poll-relay.conf /etc/nginx/sites-available/poll-relay.conf.{timestamp}.bak")
    run(ssh, "install -m 0644 /tmp/poll-relay-nginx.conf /etc/nginx/sites-available/poll-relay.conf && "
             "ln -sfn /etc/nginx/sites-available/poll-relay.conf /etc/nginx/sites-enabled/poll-relay.conf && nginx -t && systemctl reload nginx")
    cert_command = "certbot certonly --webroot -w /var/www/poll-acme " + \
        "--non-interactive --agree-tos --keep-until-expiring " + \
        f"-m {shlex.quote(email)} -d {shlex.quote(domain)}"
    run(ssh, cert_command)
    upload_text(sftp, "/tmp/poll-relay-nginx.conf", nginx_https(domain, path_token))
    run(ssh, "install -m 0644 /tmp/poll-relay-nginx.conf /etc/nginx/sites-available/poll-relay.conf && nginx -t && systemctl reload nginx")
    sftp.close()
    ssh.close()

    print("Uploading Passenger relay to shared hosting...")
    ftp_class = ftplib.FTP_TLS if bool(shared.get("ftp_tls", False)) else ftplib.FTP
    ftp = ftp_class()
    ftp.connect(required(shared, "ftp_host"), int(shared.get("ftp_port", 21)), timeout=30)
    ftp.login(required(shared, "ftp_user"), ftp_password)
    if isinstance(ftp, ftplib.FTP_TLS):
        ftp.prot_p()
    site_dir = required(shared, "site_dir").rstrip("/")
    ftp_mkdirs(ftp, site_dir + "/tmp")
    passenger = (ROOT / "shared-hosting/passenger_wsgi.py").read_text(encoding="utf-8")
    relay_config = (
        f'PUBLIC_TOKEN = "{public_token}"\n'
        f'BACKEND_TOKEN = "{backend_token}"\n'
        f'BACKEND_BASE = "https://{domain}/poll-tunnel/{path_token}"\n')
    ftp_upload(ftp, site_dir + "/passenger_wsgi.py", passenger)
    ftp_upload(ftp, site_dir + "/relay_config.py", relay_config)
    ftp_upload(ftp, site_dir + "/tmp/restart.txt", str(time.time()))
    ftp.quit()

    request = urllib.request.Request(f"https://{relay_domain}/health",
                                     headers={"X-Relay-Key": public_token})
    with urllib.request.urlopen(request, timeout=15) as response:
        print("Relay health:", response.read().decode())
    print("Deployment complete.")
    print("Android relay URL:", f"https://{relay_domain}")
    print("Android public token is stored in:", secrets_file)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, KeyError, socket.error) as exc:
        raise SystemExit(f"ERROR: {exc}")
