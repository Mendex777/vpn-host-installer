import tempfile
import unittest
from pathlib import Path

from src.installer import Config, Installer, InstallError, valid_domain, valid_path


class ConfigTests(unittest.TestCase):
    def test_load_and_normalize(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text(
                """domains: {origin: vpn.example.com, panel: vpn.example.com, front: front.example.com}
xhttp: {path: tunnel, port: 2053}
xui: {version: v3.5.0}
""",
                encoding="utf-8",
            )
            cfg = Config.load(str(path))
            self.assertEqual(cfg.xhttp_path, "/tunnel")

    def test_rejects_unpinned_xui(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text(
                "domains: {origin: vpn.example.com, front: front.example.com}\nxui: {version: latest}\n"
            )
            with self.assertRaises(InstallError):
                Config.load(str(path))

    def test_rejects_separate_origin_until_san_is_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text(
                "domains: {origin: origin.example.com, panel: panel.example.com, front: front.example.com}\n"
            )
            with self.assertRaises(InstallError):
                Config.load(str(path))

    def test_validators(self):
        self.assertEqual(valid_domain("VPN.Example.com."), "vpn.example.com")
        self.assertEqual(valid_path("abc-123"), "/abc-123")
        with self.assertRaises(InstallError):
            valid_path("../bad")


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


if __name__ == "__main__":
    unittest.main()
