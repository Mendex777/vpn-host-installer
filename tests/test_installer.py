import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.installer import Config, Installer, InstallError, valid_domain, valid_path


class ConfigTests(unittest.TestCase):
    def test_load_and_normalize(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text(
                """domains: {origin: vpn.example.net, panel: vpn.example.net, front: front.example.net}
xhttp: {path: tunnel, port: 2053}
xui: {version: v3.5.0}
ftp: {enabled: false}
""",
                encoding="utf-8",
            )
            cfg = Config.load(str(path), interactive=False)
            self.assertEqual(cfg.xhttp_path, "/tunnel")

    def test_rejects_unpinned_xui(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text(
                "domains: {origin: vpn.example.net, front: front.example.net}\nxui: {version: latest}\nftp: {enabled: false}\n"
            )
            with self.assertRaises(InstallError):
                Config.load(str(path), interactive=False)

    def test_rejects_separate_origin_until_san_is_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text(
                "domains: {origin: origin.example.net, panel: panel.example.net, front: front.example.net}\nftp: {enabled: false}\n"
            )
            with self.assertRaises(InstallError):
                Config.load(str(path), interactive=False)

    def test_validators(self):
        self.assertEqual(valid_domain("VPN.Example.com."), "vpn.example.com")
        self.assertEqual(valid_path("abc-123"), "/abc-123")
        with self.assertRaises(InstallError):
            valid_path("../bad")

    def test_interactive_fills_example_values(self):
        answers = iter(
            [
                "vpn.example.net",
                "",
                "front.example.net",
                "admin@example.net",
                "ftp.example.net",
                "real-user",
                "/www/front.example.net",
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text(Path("config.yaml").read_text(encoding="utf-8"))
            cfg = Config.load(
                str(path),
                input_fn=lambda _prompt: next(answers),
                password_fn=lambda _prompt: "ftp-secret",
            )
        self.assertEqual(cfg.origin_domain, "vpn.example.net")
        self.assertEqual(cfg.panel_domain, "vpn.example.net")
        self.assertEqual(cfg.ftp_host, "ftp.example.net")
        self.assertEqual(cfg.ftp_user, "real-user")
        self.assertEqual(cfg.ftp_password, "ftp-secret")

    def test_non_interactive_lists_missing_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text(Path("config.yaml").read_text(encoding="utf-8"))
            with self.assertRaisesRegex(InstallError, "domains.origin.*ftp.password"):
                Config.load(str(path), interactive=False)


class RenderingTests(unittest.TestCase):
    def setUp(self):
        self.installer = Installer.__new__(Installer)
        self.installer.cfg = Config(
            "vpn.example.com", "vpn.example.com", "front.example.com", "/p", 2053
        )
        self.installer.secrets = {
            "panel_path": "secret-panel",
            "panel_port": "32018",
            "client_uuid": "00000000-0000-4000-8000-000000000000",
        }

    def test_nginx_routes_tree(self):
        text = self.installer.nginx_config()
        self.assertEqual(text.count("location /p"), 2)
        self.assertIn("proxy_pass http://127.0.0.1:2053", text)
        self.assertIn("location /secret-panel/", text)

    def test_htaccess_preserves_suffix(self):
        text = self.installer.htaccess("192.0.2.10")
        self.assertIn("^p(.*)$", text)
        self.assertIn("http://192.0.2.10/p$1", text)

    def test_vless_link_uses_front(self):
        link = self.installer.vless_link()
        self.assertIn("@front.example.com:443", link)
        self.assertIn("path=%2Fp", link)

    def test_ftp_connect_timeout_reports_context_without_quit_crash(self):
        self.installer.cfg.ftp_enabled = True
        self.installer.cfg.ftp_host = "ftp.example.net"
        self.installer.cfg.ftp_port = 21
        self.installer.cfg.ftp_user = "user"
        self.installer.cfg.ftp_password = "secret"
        self.installer.cfg.ftp_site_dir = "/www/front.example.net"
        self.installer.dry_run = False
        ftp = mock.Mock()
        ftp.sock = None
        ftp.connect.side_effect = TimeoutError("timed out")
        with (
            mock.patch("src.installer.ftplib.FTP", return_value=ftp),
            self.assertRaisesRegex(InstallError, "FTP failed.*timed out"),
        ):
            self.installer.configure_ftp(None)
        ftp.quit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
