#!/usr/bin/env python3
"""Idempotent 3x-ui + XHTTP + shared-hosting installer."""

from __future__ import annotations

import argparse
import ftplib
import getpass
import io
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG = "/etc/vpn-host-installer/config.yaml"
STATE_DIR = Path("/etc/vpn-host-installer")
STATE_FILE = STATE_DIR / "state.json"
SECRETS_FILE = STATE_DIR / "secrets.json"
NGINX_SITE = Path("/etc/nginx/sites-available/vpn-host.conf")
XUI_ENV = Path("/etc/x-ui/install-result.env")
TAG = "host-cdn-xhttp"


class InstallError(RuntimeError):
    pass


def run(
    args: list[str], *, check: bool = True, timeout: int = 600
) -> subprocess.CompletedProcess[str]:
    """Run without a shell so config values cannot become shell syntax."""
    result = subprocess.run(
        args,
        text=True,
        capture_output=True,
        timeout=timeout,
        env=os.environ.copy(),
        check=False,
    )
    if check and result.returncode:
        detail = (result.stderr or result.stdout).strip()[-1200:]
        raise InstallError(
            f"Command failed ({result.returncode}): {' '.join(args)}\n{detail}"
        )
    return result


def atomic_write(path: Path, content: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def valid_domain(value: str) -> str:
    value = value.lower().strip().rstrip(".")
    pattern = r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}"
    if not re.fullmatch(pattern, value):
        raise InstallError(f"Invalid domain: {value!r}")
    return value


def valid_path(value: str) -> str:
    value = "/" + value.strip().strip("/")
    if not re.fullmatch(r"/[A-Za-z0-9_-]{1,64}", value):
        raise InstallError("xhttp.path may contain only letters, numbers, _ and -")
    return value


@dataclass
class Config:
    origin_domain: str
    panel_domain: str
    front_domain: str
    xhttp_path: str = "/p"
    xray_port: int = 2053
    xui_version: str = "v3.5.0"
    acme_email: str = ""
    ftp_host: str = ""
    ftp_user: str = ""
    ftp_site_dir: str = ""
    enable_ufw: bool = True
    ssh_port: int = 22

    @classmethod
    def load(cls, path: str) -> Config:
        try:
            raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        except FileNotFoundError as exc:
            raise InstallError(f"Config not found: {path}") from exc
        domains, xhttp = raw.get("domains", {}), raw.get("xhttp", {})
        xui, ftp, firewall = (
            raw.get("xui", {}),
            raw.get("ftp", {}),
            raw.get("firewall", {}),
        )
        cfg = cls(
            origin_domain=valid_domain(domains.get("origin", "")),
            panel_domain=valid_domain(domains.get("panel", domains.get("origin", ""))),
            front_domain=valid_domain(domains.get("front", "")),
            xhttp_path=valid_path(xhttp.get("path", "/p")),
            xray_port=int(xhttp.get("port", 2053)),
            xui_version=str(xui.get("version", "v3.5.0")),
            acme_email=str(raw.get("acme_email", "")),
            ftp_host=str(ftp.get("host", "")),
            ftp_user=str(ftp.get("user", "")),
            ftp_site_dir=str(ftp.get("site_dir", "")),
            enable_ufw=bool(firewall.get("enable", True)),
            ssh_port=int(firewall.get("ssh_port", 22)),
        )
        if not 1024 <= cfg.xray_port <= 65535:
            raise InstallError("xhttp.port must be between 1024 and 65535")
        if not re.fullmatch(r"v\d+\.\d+\.\d+", cfg.xui_version):
            raise InstallError("xui.version must be pinned, for example v3.5.0")
        if cfg.origin_domain != cfg.panel_domain:
            raise InstallError("origin and panel must currently use the same hostname")
        return cfg


@dataclass
class State:
    version: int = 1
    completed: list[str] = field(default_factory=list)
    backups: dict[str, str] = field(default_factory=dict)
    ftp_backup: str = ""

    @classmethod
    def load(cls) -> State:
        return (
            cls(**json.loads(STATE_FILE.read_text())) if STATE_FILE.exists() else cls()
        )

    def save(self) -> None:
        atomic_write(STATE_FILE, json.dumps(asdict(self), indent=2) + "\n", 0o600)

    def done(self, step: str) -> None:
        if step not in self.completed:
            self.completed.append(step)
            self.save()


class Installer:
    def __init__(self, cfg: Config, *, dry_run: bool = False) -> None:
        self.cfg, self.dry_run = cfg, dry_run
        self.state = State.load()
        self.secrets = (
            json.loads(SECRETS_FILE.read_text()) if SECRETS_FILE.exists() else {}
        )

    def log(self, text: str) -> None:
        print(f"  {text}")

    def save_secrets(self) -> None:
        atomic_write(SECRETS_FILE, json.dumps(self.secrets, indent=2) + "\n", 0o600)

    def require_host(self) -> None:
        if sys.platform != "linux" or os.geteuid() != 0 or not shutil.which("apt-get"):
            raise InstallError("Run as root on an apt-based Ubuntu/Debian server")

    def public_ip(self) -> str:
        value = (
            urllib.request.urlopen("https://api.ipify.org", timeout=10)
            .read()
            .decode()
            .strip()
        )
        ipaddress.ip_address(value)
        return value

    def validate_dns(self) -> None:
        public_ip = self.public_ip()
        for domain in {self.cfg.origin_domain, self.cfg.panel_domain}:
            resolved = {
                x[4][0] for x in socket.getaddrinfo(domain, 443, socket.AF_INET)
            }
            if public_ip not in resolved:
                raise InstallError(
                    f"{domain} must resolve to this VPS ({public_ip}), got {sorted(resolved)}"
                )
        self.log(f"DNS points to {public_ip}")

    def packages(self) -> None:
        if self.dry_run:
            self.log("[dry-run] install nginx, certbot, curl, sqlite3 and ufw")
            return
        run(["apt-get", "update", "-qq"])
        run(
            [
                "apt-get",
                "install",
                "-y",
                "-qq",
                "nginx",
                "certbot",
                "curl",
                "sqlite3",
                "ca-certificates",
                "ufw",
            ]
        )
        run(["systemctl", "enable", "--now", "nginx"])
        self.state.done("packages")

    @staticmethod
    def read_env(path: Path) -> dict[str, str]:
        return dict(
            line.split("=", 1) for line in path.read_text().splitlines() if "=" in line
        )

    def install_xui(self) -> None:
        if XUI_ENV.exists() and Path("/usr/local/x-ui/x-ui").exists():
            values = self.read_env(XUI_ENV)
            self.secrets.update(
                {
                    "panel_username": values["XUI_USERNAME"],
                    "panel_password": values["XUI_PASSWORD"],
                    "panel_port": values["XUI_PANEL_PORT"],
                    "panel_path": values["XUI_WEB_BASE_PATH"].strip("/"),
                    "api_token": values["XUI_API_TOKEN"],
                }
            )
            self.save_secrets()
            self.log("3x-ui already installed")
            return
        if self.dry_run:
            self.log(f"[dry-run] install 3x-ui {self.cfg.xui_version}")
            return
        url = f"https://raw.githubusercontent.com/MHSanaei/3x-ui/{self.cfg.xui_version}/install.sh"
        script = Path(f"/root/3x-ui-install-{self.cfg.xui_version}.sh")
        atomic_write(
            script, urllib.request.urlopen(url, timeout=30).read().decode(), 0o700
        )
        env = os.environ.copy()
        env["XUI_NONINTERACTIVE"] = "1"
        result = subprocess.run(
            ["bash", str(script), self.cfg.xui_version],
            text=True,
            capture_output=True,
            timeout=900,
            env=env,
            check=False,
        )
        if result.returncode or not XUI_ENV.exists():
            raise InstallError(f"3x-ui installation failed: {result.stderr[-1200:]}")
        self.install_xui()  # Load generated values using the idempotent branch.
        run(["/usr/local/x-ui/x-ui", "setting", "-listenIP", "127.0.0.1"])
        run(["systemctl", "restart", "x-ui"])
        self.state.done("xui")

    def certificate(self) -> None:
        cert = Path(f"/etc/letsencrypt/live/{self.cfg.panel_domain}/fullchain.pem")
        if cert.exists():
            self.log("Let's Encrypt certificate already exists")
            return
        if self.dry_run:
            self.log(f"[dry-run] issue certificate for {self.cfg.panel_domain}")
            return
        Path("/var/www/html").mkdir(parents=True, exist_ok=True)
        args = [
            "certbot",
            "certonly",
            "--webroot",
            "-w",
            "/var/www/html",
            "-d",
            self.cfg.panel_domain,
            "--non-interactive",
            "--agree-tos",
        ]
        args += (
            ["--email", self.cfg.acme_email]
            if self.cfg.acme_email
            else ["--register-unsafely-without-email"]
        )
        run(args, timeout=180)
        self.state.done("certificate")

    def api(self, method: str, path: str, data: Any = None) -> dict[str, Any]:
        base = f"http://127.0.0.1:{self.secrets['panel_port']}/{self.secrets['panel_path']}"
        request = urllib.request.Request(
            base + path,
            method=method,
            data=json.dumps(data).encode() if data is not None else None,
            headers={
                "Authorization": f"Bearer {self.secrets['api_token']}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise InstallError(
                f"3x-ui API {exc.code}: {exc.read().decode()[:800]}"
            ) from exc

    def configure_inbound(self) -> None:
        if self.dry_run:
            self.log("[dry-run] upsert VLESS/XHTTP inbound through 3x-ui API")
            return
        self.secrets.setdefault("client_uuid", str(uuid.uuid4()))
        self.secrets.setdefault("subscription_id", secrets.token_urlsafe(12)[:16])
        self.save_secrets()
        result = self.api("GET", "/panel/api/inbounds/list")
        if not result.get("success"):
            raise InstallError(result.get("msg", "Cannot list inbounds"))
        existing = next((x for x in result.get("obj", []) if x.get("tag") == TAG), None)
        payload = {
            "up": 0,
            "down": 0,
            "total": 0,
            "remark": "HOST-CDN-XHTTP",
            "enable": True,
            "expiryTime": 0,
            "listen": "127.0.0.1",
            "port": self.cfg.xray_port,
            "protocol": "vless",
            "tag": TAG,
            "settings": {
                "clients": [
                    {
                        "id": self.secrets["client_uuid"],
                        "email": "user1",
                        "enable": True,
                        "expiryTime": 0,
                        "limitIp": 0,
                        "totalGB": 0,
                        "subId": self.secrets["subscription_id"],
                        "flow": "",
                    }
                ],
                "decryption": "none",
                "fallbacks": [],
            },
            "streamSettings": {
                "network": "xhttp",
                "security": "none",
                "xhttpSettings": {
                    "path": self.cfg.xhttp_path,
                    "mode": "packet-up",
                    "xPaddingBytes": "100-1000",
                },
            },
            "sniffing": {
                "enabled": True,
                "destOverride": ["http", "tls", "quic"],
                "metadataOnly": False,
                "routeOnly": False,
            },
        }
        if existing:
            payload["id"] = existing["id"]
            result = self.api(
                "POST", f"/panel/api/inbounds/update/{existing['id']}", payload
            )
        else:
            result = self.api("POST", "/panel/api/inbounds/add", payload)
        if not result.get("success"):
            raise InstallError(result.get("msg", "Inbound rejected"))
        time.sleep(2)
        self.state.done("inbound")

    def proxy_location(self) -> str:
        return f"""    location {self.cfg.xhttp_path} {{
        proxy_pass http://127.0.0.1:{self.cfg.xray_port};
        proxy_http_version 1.1;
        proxy_set_header Connection \"\";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_cache off;
        proxy_max_temp_file_size 0;
        gzip off;
        client_max_body_size 0;
        proxy_connect_timeout 10s;
        proxy_read_timeout 1h;
        proxy_send_timeout 1h;
        send_timeout 1h;
        add_header X-Accel-Buffering no always;
        add_header Cache-Control \"no-store\" always;
    }}"""

    def nginx_config(self) -> str:
        panel_path, panel_port = (
            self.secrets.get("panel_path", "PANEL_PATH"),
            self.secrets.get("panel_port", "32018"),
        )
        cert = f"/etc/letsencrypt/live/{self.cfg.panel_domain}"
        proxy = self.proxy_location()
        return f"""# Managed by vpn-host-installer
server {{
    listen 80; listen [::]:80;
    server_name {self.cfg.origin_domain} {self.cfg.panel_domain};
    location /.well-known/acme-challenge/ {{ root /var/www/html; }}
{proxy}
    location / {{ return 301 https://$host$request_uri; }}
}}
server {{
    listen 443 ssl; listen [::]:443 ssl; http2 on;
    server_name {self.cfg.origin_domain} {self.cfg.panel_domain};
    ssl_certificate {cert}/fullchain.pem;
    ssl_certificate_key {cert}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
{proxy}
    location /{panel_path}/ {{
        proxy_pass http://127.0.0.1:{panel_port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection \"upgrade\";
        proxy_read_timeout 1h;
    }}
    location / {{ root /var/www/html; try_files $uri $uri/ =404; }}
}}
"""

    def configure_nginx(self) -> None:
        if self.dry_run:
            self.log("[dry-run] write and validate Nginx configuration")
            return
        if NGINX_SITE.exists() and str(NGINX_SITE) not in self.state.backups:
            backup = NGINX_SITE.with_suffix(f".conf.backup.{int(time.time())}")
            shutil.copy2(NGINX_SITE, backup)
            self.state.backups[str(NGINX_SITE)] = str(backup)
            self.state.save()
        atomic_write(NGINX_SITE, self.nginx_config())
        enabled = Path("/etc/nginx/sites-enabled/vpn-host.conf")
        enabled.unlink(missing_ok=True)
        enabled.symlink_to(NGINX_SITE)
        Path("/etc/nginx/sites-enabled/default").unlink(missing_ok=True)
        run(["nginx", "-t"])
        run(["systemctl", "reload", "nginx"])
        self.state.done("nginx")

    def htaccess(self, public_ip: str) -> str:
        name = self.cfg.xhttp_path.lstrip("/")
        return (
            "# Managed by vpn-host-installer\nRewriteEngine On\n"
            f"RewriteRule ^{name}(.*)$ http://{public_ip}/{name}$1 [P,L,NE]\n"
        )

    def configure_ftp(self, password: str | None) -> None:
        if not self.cfg.ftp_host:
            self.log("FTP disabled; upload the generated .htaccess manually")
            return
        password = password or os.environ.get("VHI_FTP_PASSWORD")
        if not password and not self.dry_run:
            password = getpass.getpass("REG.RU FTP password: ")
        if self.dry_run:
            self.log(f"[dry-run] upload .htaccess to {self.cfg.ftp_site_dir}")
            return
        ftp = ftplib.FTP()
        try:
            ftp.connect(self.cfg.ftp_host, 21, timeout=30)
            ftp.login(self.cfg.ftp_user, password or "")
            ftp.set_pasv(True)
            ftp.cwd(self.cfg.ftp_site_dir)
            if ".htaccess" in ftp.nlst():
                backup = f".htaccess.backup.{int(time.time())}"
                ftp.rename(".htaccess", backup)
                self.state.ftp_backup = backup
                self.state.save()
            ftp.storbinary(
                "STOR .htaccess", io.BytesIO(self.htaccess(self.public_ip()).encode())
            )
        finally:
            try:
                ftp.quit()
            except ftplib.all_errors:
                ftp.close()
        self.state.done("ftp")

    def firewall(self) -> None:
        if not self.cfg.enable_ufw:
            return
        if self.dry_run:
            self.log("[dry-run] allow SSH, HTTP and HTTPS in UFW")
            return
        for port in (self.cfg.ssh_port, 80, 443):
            run(["ufw", "allow", f"{port}/tcp"])
        run(["ufw", "default", "deny", "incoming"])
        run(["ufw", "default", "allow", "outgoing"])
        run(["ufw", "--force", "enable"])
        self.state.done("firewall")

    def vless_link(self) -> str:
        from urllib.parse import quote

        query = (
            f"type=xhttp&security=tls&sni={self.cfg.front_domain}&fp=firefox&alpn=h2"
            f"&path={quote(self.cfg.xhttp_path, safe='')}&host={self.cfg.front_domain}"
            "&mode=packet-up&encryption=none"
        )
        return f"vless://{self.secrets['client_uuid']}@{self.cfg.front_domain}:443?{query}#REG-RU-XHTTP"

    def verify(self) -> None:
        if self.dry_run:
            return
        for service in ("nginx", "x-ui"):
            if (
                run(["systemctl", "is-active", service], check=False).stdout.strip()
                != "active"
            ):
                raise InstallError(f"Service inactive: {service}")
        run(["nginx", "-t"])
        with socket.create_connection(("127.0.0.1", self.cfg.xray_port), timeout=5):
            pass
        with urllib.request.urlopen(
            f"https://{self.cfg.panel_domain}/{self.secrets['panel_path']}/",
            timeout=15,
            context=ssl.create_default_context(),
        ) as response:
            if response.status != 200:
                raise InstallError(f"Panel HTTP {response.status}")
        self.log("Services, TLS, panel and local Xray listener verified")
        if self.cfg.ftp_host:
            self.verify_front_vpn()

    def verify_front_vpn(self) -> None:
        """Start a temporary local SOCKS client and traverse the complete front path."""
        binary = Path("/usr/local/x-ui/bin/xray-linux-amd64")
        if not binary.exists():
            matches = list(Path("/usr/local/x-ui/bin").glob("xray-linux-*"))
            if not matches:
                raise InstallError("Cannot find bundled Xray for end-to-end test")
            binary = matches[0]
        config = {
            "log": {"loglevel": "warning"},
            "inbounds": [
                {
                    "listen": "127.0.0.1",
                    "port": 10808,
                    "protocol": "socks",
                    "settings": {"auth": "noauth"},
                }
            ],
            "outbounds": [
                {
                    "protocol": "vless",
                    "settings": {
                        "vnext": [
                            {
                                "address": self.cfg.front_domain,
                                "port": 443,
                                "users": [
                                    {
                                        "id": self.secrets["client_uuid"],
                                        "encryption": "none",
                                    }
                                ],
                            }
                        ]
                    },
                    "streamSettings": {
                        "network": "xhttp",
                        "security": "tls",
                        "tlsSettings": {
                            "serverName": self.cfg.front_domain,
                            "alpn": ["h2"],
                            "fingerprint": "firefox",
                        },
                        "xhttpSettings": {
                            "path": self.cfg.xhttp_path,
                            "mode": "packet-up",
                        },
                    },
                }
            ],
        }
        fd, filename = tempfile.mkstemp(prefix="vhi-client-", suffix=".json")
        process = None
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(config, handle)
            process = subprocess.Popen(
                [str(binary), "run", "-config", filename],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(2)
            result = run(
                [
                    "curl",
                    "--socks5-hostname",
                    "127.0.0.1:10808",
                    "-fsS",
                    "--max-time",
                    "25",
                    "https://api.ipify.org",
                ],
                timeout=30,
            )
            ipaddress.ip_address(result.stdout.strip())
            self.log(f"End-to-end XHTTP through {self.cfg.front_domain} verified")
        finally:
            if process is not None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            Path(filename).unlink(missing_ok=True)

    def install(self, ftp_password: str | None = None) -> None:
        self.require_host()
        self.validate_dns()
        self.packages()
        self.install_xui()
        self.certificate()
        self.configure_inbound()
        self.configure_nginx()
        self.configure_ftp(ftp_password)
        self.firewall()
        self.verify()
        if not self.dry_run:
            print("\nInstallation complete")
            print(
                f"Panel: https://{self.cfg.panel_domain}/{self.secrets['panel_path']}/"
            )
            print(
                f"Username: {self.secrets['panel_username']}\nPassword: {self.secrets['panel_password']}"
            )
            print(f"VLESS: {self.vless_link()}")


def rollback() -> None:
    if sys.platform != "linux" or os.geteuid() != 0:
        raise InstallError("Rollback requires root on Linux")
    state = State.load()
    Path("/etc/nginx/sites-enabled/vpn-host.conf").unlink(missing_ok=True)
    if str(NGINX_SITE) in state.backups:
        shutil.copy2(state.backups[str(NGINX_SITE)], NGINX_SITE)
    else:
        NGINX_SITE.unlink(missing_ok=True)
    run(["nginx", "-t"], check=False)
    run(["systemctl", "reload", "nginx"], check=False)
    print(
        "Local Nginx configuration rolled back; 3x-ui and remote FTP data were preserved."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Install 3x-ui XHTTP behind shared hosting"
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--ftp-password", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.rollback:
            rollback()
        else:
            Installer(Config.load(args.config), dry_run=args.dry_run).install(
                args.ftp_password
            )
    except (InstallError, OSError, ValueError, urllib.error.URLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
