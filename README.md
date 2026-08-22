# Metadmin Poll Relay

TCP VPN transport through REG.RU shared hosting without `mod_proxy`, WebSocket,
or long-lived requests. The shared host runs a small Passenger/WSGI application
that forwards short authenticated HTTPS requests to a VPS. The Android client
converts the device TUN interface to SOCKS5 and multiplexes all downstream TCP
sessions through one polling request.

```text
Android apps
    │ TUN + HEV mapdns
    ▼
Android polling SOCKS5 client
    │ HTTPS short requests: open / up / mux-down / close
    ▼
REG.RU Passenger WSGI (public relay domain, allowed shared-hosting address)
    │ HTTPS + private backend token
    ▼
VPS Nginx → poll-tunnel backend on 127.0.0.1:18080
    │ ordinary TCP sockets
    ▼
Internet
```

The legacy 3x-ui/XHTTP installer is preserved in branch `xhttp_old`. It is not
part of the current polling relay.

## Components

- `android-client/` — Android `VpnService`, HEV tun2socks and multiplexed polling transport.
- `poll-tunnel/backend.py` — authenticated VPS TCP session backend.
- `shared-hosting/passenger_wsgi.py` — stateless REG.RU Passenger forwarder.
- `deploy.py` — repeatable deployment from a workstation over SSH/SFTP and FTP/FTPS.
- `config.example.toml` — deployment configuration template.
- `docs/MANUAL_SETUP_RU.md` — complete manual installation in Russian.

## Automated deployment

Requirements: Python 3.11+, DNS records for both domains, root SSH access to the
VPS, and FTP/FTPS access to the REG.RU website directory.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config.example.toml config.toml
nano config.toml
.venv/bin/python deploy.py --config config.toml
```

On Windows PowerShell use `.venv\Scripts\python.exe` instead. Missing passwords
and tokens are requested without echo. Generated tokens are saved to
`deployment-secrets.toml`; protect that file and never commit it.

The deployer installs the VPS service and Nginx, obtains a webroot Let's Encrypt
certificate, uploads the WSGI relay to REG.RU, restarts Passenger, and validates
both health endpoints. Re-running it reconciles the same deployment. Managed VPS
files are backed up with a timestamp before replacement.

## Build Android APK

Pushes affecting `android-client/` trigger GitHub Actions. The APK is available
as the `metadmin-relay-debug-apk` workflow artifact. It can also be built with:

```bash
cd android-client
./gradlew assembleDebug
```

In the app enter `https://relay.example.com` and the generated public relay token.

## Security and limitations

- Use independent random public, backend and URL-path tokens.
- The REG.RU-to-VPS leg is HTTPS; the backend listens only on loopback.
- Only TCP is transported. DNS uses HEV mapped DNS; arbitrary UDP is unsupported.
- Shared hosting adds latency and bandwidth limits.
- The current Android build is a debug build; use a private release signing key
  before distributing it.

Use only where allowed by law and the terms of both providers.
