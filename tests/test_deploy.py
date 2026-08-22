import unittest

import deploy


class TemplateTests(unittest.TestCase):
    def test_http_template_keeps_acme_on_nginx_port_80(self):
        rendered = deploy.nginx_http("backend.example.com")
        self.assertIn("listen 80;", rendered)
        self.assertIn("/.well-known/acme-challenge/", rendered)
        self.assertIn("server_name backend.example.com;", rendered)

    def test_https_template_exposes_only_secret_backend_path(self):
        rendered = deploy.nginx_https("backend.example.com", "secret-path")
        self.assertIn("/poll-tunnel/secret-path/", rendered)
        self.assertIn("proxy_pass http://127.0.0.1:18080/;", rendered)
        self.assertIn("location / { return 404; }", rendered)

    def test_validation_rejects_nginx_and_python_injection(self):
        with self.assertRaises(SystemExit):
            deploy.validate_domain("example.com; return 200")
        with self.assertRaises(SystemExit):
            deploy.validate_token("token", 'bad"token')


if __name__ == "__main__":
    unittest.main()
