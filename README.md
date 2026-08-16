# VPN Host Installer

Repeatable installer for a verified topology:

```text
XHTTP client → HTTPS shared-hosting front → HTTP VPS/Nginx
             → 3x-ui managed Xray on 127.0.0.1 → Internet
```

It intentionally supports one tested setup: Ubuntu/Debian, a pinned 3x-ui release, VLESS/XHTTP `packet-up`, Nginx, UFW, and an Apache shared-hosting front (tested with REG.RU).

## Safety

- No passwords or generated UUIDs belong in Git.
- FTP password may come from hidden input, protected YAML, or `VHI_FTP_PASSWORD`.
- Credentials are stored in `/etc/vpn-host-installer/secrets.json` with mode `0600`.
- Commands use argument arrays instead of interpolated shell strings.
- 3x-ui is the only process managing Xray.
- Re-runs preserve the UUID and update the tagged inbound.
- Existing Nginx and remote `.htaccess` files are backed up.
- Existing UFW rules are not reset.

## DNS prerequisites

```text
origin.example.com  A  VPS_IP
panel.example.com   A  VPS_IP  # may be the same as origin
front.example.com   A  SHARED_HOSTING_IP
```

Create the front-domain website on the shared hosting and enable TLS there.

## Install

The first bootstrap run creates the configuration and stops. On the next command,
every blank or example value is requested interactively:

```bash
curl -fsSL https://raw.githubusercontent.com/Mendex777/vpn-host-installer/main/install.sh | bash
nano /etc/vpn-host-installer/config.yaml
/opt/vpn-host-installer/.venv/bin/python /opt/vpn-host-installer/install.py
```

For non-interactive FTP authentication:

```bash
read -rsp "FTP password: " VHI_FTP_PASSWORD
export VHI_FTP_PASSWORD
/opt/vpn-host-installer/.venv/bin/python /opt/vpn-host-installer/install.py
unset VHI_FTP_PASSWORD
```

Never place the password directly in command arguments. Prefer hidden input or
`VHI_FTP_PASSWORD`; YAML is supported when unattended installation requires it.

All interactive values can instead be supplied in YAML, including FTP connection
details and `ftp.password`. The file is created and enforced with mode `0600`.
For unattended provisioning, use:

```bash
/opt/vpn-host-installer/.venv/bin/python /opt/vpn-host-installer/install.py --non-interactive
```

This mode never prompts. It reports every missing required field before changing
the server. `VHI_FTP_PASSWORD` overrides `ftp.password` and is preferable in CI.

## Configuration and repeat runs

See [`config.yaml`](config.yaml). `xui.version` must be an exact tag such as `v3.5.0`; moving targets such as `latest` are rejected.

FTP configuration includes `enabled`, `host`, `port`, `user`, `password`, and
`site_dir`. Example/test values are deliberately rejected as incomplete.

The Apache rule proxies the entire XHTTP route tree:

```apache
RewriteRule ^p(.*)$ http://VPS_IP/p$1 [P,L,NE]
```

This matters because XHTTP creates URLs such as `/p/<session-id>/0`. Re-run the same command to reconcile the existing installation; state lives under `/etc`, outside the replaceable `/opt` code directory.

## Rollback

```bash
/opt/vpn-host-installer/.venv/bin/python /opt/vpn-host-installer/install.py --rollback
```

Rollback restores local Nginx when a backup exists. It deliberately preserves 3x-ui, its database, firewall rules, and remote FTP data.

## Validation

The installer checks DNS, Nginx syntax, services, panel TLS, and the local Xray listener. A real client test is still recommended because shared hosts may change proxy limits.

```bash
python -m unittest discover -s tests -v
```

## Limitations

- One local 3x-ui node only.
- Keep `origin` and `panel` equal for now; one certificate is issued.
- FTP is unencrypted where that is all the plan exposes; prefer FTPS/SFTP when available.
- Shared hosting is not a CDN and its proxy policy can change.

Use only where permitted by applicable law and provider terms.
