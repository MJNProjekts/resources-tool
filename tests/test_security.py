"""Security checks before publishing. Run from the project folder:

    python -m unittest tests.test_security -v

No credits are spent: the API and Telegram calls are mocked.
"""

from __future__ import annotations

import fnmatch
import io
import os
import re
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

from rgtool.api import APIError, ResourcesAPI  # noqa: E402
from rgtool.config import Config  # noqa: E402
from rgtool.fmt import esc  # noqa: E402
from rgtool.telegram import Telegram  # noqa: E402

SECRET_VARS = ("RG_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
FAKE_KEY = "FAKEKEY_0123456789abcdef0123456789abcdef01234"
FAKE_TOKEN = "123456789:AAFakeTokenFakeTokenFakeTokenFake123"


# ------------------------------------------------------------------ helpers
def gitignore_patterns() -> list[str]:
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.startswith("#")]


def is_ignored(rel: Path, patterns: list[str]) -> bool:
    """Simple .gitignore matcher (enough for this project's patterns)."""
    parts = rel.parts
    for p in patterns:
        if p.endswith("/"):
            if any(fnmatch.fnmatch(d, p[:-1]) for d in parts[:-1]):
                return True
        elif any(fnmatch.fnmatch(x, p) for x in parts):
            return True
    return False


def publishable_files() -> list[Path]:
    pats = gitignore_patterns() + [".git/"]
    out = []
    for path in ROOT.rglob("*"):
        if path.is_file():
            rel = path.relative_to(ROOT)
            if not is_ignored(rel, pats):
                out.append(rel)
    return out


def env_secrets() -> dict[str, str]:
    env = ROOT / ".env"
    if not env.exists():
        return {}
    found = {}
    for line in env.read_text(encoding="utf-8").splitlines():
        k, _, v = line.partition("=")
        v = v.strip().strip("'\"")
        if k.strip() in SECRET_VARS and len(v) >= 6:
            found[k.strip()] = v
    return found


# ------------------------------------------------------------------ 1. files
class TestRepositoryFiles(unittest.TestCase):
    def test_gitignore_covers_private_files(self):
        pats = gitignore_patterns()
        for must in (".env", "*.db", "*.db-wal", "*.db-shm", "samples/", "_backup_*/", "_old/", ".venv/"):
            self.assertIn(must, pats, f".gitignore is missing {must}")

    def test_private_files_are_ignored(self):
        pats = gitignore_patterns()
        for rel in (".env", "resources.db", "resources.db-wal", "samples/2_warehouses.json",
                    "_backup_2026-11-08/web/app.py", "_old/history.db", "_old/samples.zip"):
            self.assertTrue(is_ignored(Path(rel), pats), f"{rel} would be published")

    def test_no_data_files_published(self):
        bad = [str(p) for p in publishable_files()
               if p.suffix in (".db", ".sqlite", ".zip", ".json") or p.name.startswith(".env") and p.name != ".env.example"]
        self.assertEqual(bad, [], f"private data files would be published: {bad}")

    def test_no_real_secrets_in_published_files(self):
        secrets = env_secrets()
        if not secrets:
            self.skipTest("no .env with secrets on this machine")
        leaks = []
        for rel in publishable_files():
            try:
                text = (ROOT / rel).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            leaks += [f"{name} in {rel}" for name, v in secrets.items() if v in text]
        self.assertEqual(leaks, [], f"secret found: {leaks}")

    def test_no_token_like_strings(self):
        tg = re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b")
        hits = []
        for rel in publishable_files():
            if rel.parts[0] == "tests":
                continue
            text = (ROOT / rel).read_text(encoding="utf-8", errors="ignore")
            if tg.search(text):
                hits.append(str(rel))
        self.assertEqual(hits, [], f"Telegram-token-like string in {hits}")

    def test_env_example_has_no_values_for_secrets(self):
        text = (ROOT / ".env.example").read_text(encoding="utf-8")
        for var in SECRET_VARS:
            m = re.search(rf"^{var}=(.*)$", text, re.M)
            self.assertIsNotNone(m, f"{var} missing from .env.example")
            self.assertEqual(m.group(1).strip(), "", f"{var} has a value in .env.example")

    def test_no_debug_mode_and_sql_is_parameterized(self):
        for rel in publishable_files():
            if rel.suffix != ".py" or rel.parts[0] == "tests":
                continue
            src = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotRegex(src, r"debug\s*=\s*True", f"debug=True in {rel}")
            self.assertNotRegex(src, r"execute(many)?\(\s*f[\"']", f"f-string SQL in {rel}")
            self.assertNotRegex(src, r"\beval\(|\bexec\(|pickle\.loads|shell=True", f"risky call in {rel}")


# ------------------------------------------------------------------ 2. API key
class FakeResp:
    def __init__(self, status=200, text="", js=None):
        self.status_code, self.text, self._js = status, text, js

    def json(self):
        if self._js is None:
            raise ValueError("not json")
        return self._js


class TestApiKeyNeverLeaks(unittest.TestCase):
    def setUp(self):
        self.api = ResourcesAPI(FAKE_KEY)

    def assertNoKey(self, exc):
        self.assertNotIn(FAKE_KEY, str(exc))
        self.assertIsNone(exc.__cause__)  # "from None": no chained traceback with the URL

    def test_missing_key(self):
        with self.assertRaises(APIError):
            ResourcesAPI("")

    def test_network_error_hides_key(self):
        err = requests.ConnectionError(f"https://api.resources-game.ch/?k={FAKE_KEY}")
        with mock.patch("rgtool.api.requests.get", side_effect=err):
            with self.assertRaises(APIError) as cm:
                self.api.query(2)
        self.assertNoKey(cm.exception)

    def test_non_json_answer_hides_key(self):
        resp = FakeResp(text=f"<html>bad key {FAKE_KEY}</html>")
        with mock.patch("rgtool.api.requests.get", return_value=resp):
            with self.assertRaises(APIError) as cm:
                self.api.query(2)
        self.assertNoKey(cm.exception)

    def test_http_error_hides_key(self):
        with mock.patch("rgtool.api.requests.get", return_value=FakeResp(status=500)):
            with self.assertRaises(APIError) as cm:
                self.api.query(2)
        self.assertNoKey(cm.exception)

    def test_repr_hides_key(self):
        self.assertNotIn(FAKE_KEY, repr(self.api))

    def test_days_param_is_clamped(self):
        with mock.patch("rgtool.api.requests.get", return_value=FakeResp(js=[])) as g:
            self.api.query(6, days=999)
        self.assertEqual(g.call_args.kwargs["params"]["d"], 30)


# ------------------------------------------------------------------ 3. Telegram
class TestTelegram(unittest.TestCase):
    def test_send_error_hides_token(self):
        tg = Telegram(FAKE_TOKEN, "1")
        err = requests.ConnectionError(f"https://api.telegram.org/bot{FAKE_TOKEN}/sendMessage")
        buf = io.StringIO()
        with mock.patch("rgtool.telegram.requests.post", side_effect=err), redirect_stdout(buf):
            tg.send("hi")
        self.assertNotIn(FAKE_TOKEN, buf.getvalue())

    def test_html_escape(self):
        self.assertEqual(esc('<b>"x"&</b>'), "&lt;b&gt;&quot;x&quot;&amp;&lt;/b&gt;")


# ------------------------------------------------------------------ 4. web
class TestWeb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from web.app import create_app
        cls.create_app = staticmethod(create_app)
        cfg = Config(api_key=FAKE_KEY, db_path=os.devnull)
        cls.client = create_app(cfg).test_client()

    def post_refresh(self, headers=None, ip="127.0.0.1"):
        with mock.patch("web.app.ResourcesAPI") as api, mock.patch("web.app.Database") as db:
            r = self.client.post("/api/refresh/warehouse", headers=headers or {},
                                 environ_base={"REMOTE_ADDR": ip})
            return r, api, db

    def test_security_headers(self):
        r = self.client.get("/")
        self.assertEqual(r.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(r.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(r.headers.get("Referrer-Policy"), "no-referrer")

    def test_refresh_needs_custom_header(self):
        r, api, _ = self.post_refresh()
        self.assertEqual(r.status_code, 403)
        api.assert_not_called()

    def test_refresh_blocked_from_lan(self):
        r, api, _ = self.post_refresh({"X-Requested-With": "rgtool"}, ip="192.168.1.50")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.get_json()["code"], "local_only")
        api.assert_not_called()

    def test_refresh_get_not_allowed(self):
        self.assertEqual(self.client.get("/api/refresh/warehouse").status_code, 405)

    def test_static_path_traversal(self):
        for path in ("/static/../../.env", "/static/..%2f..%2f.env", "/static/%2e%2e/%2e%2e/.env",
                     "/static/../app.py", "/.env", "/resources.db"):
            r = self.client.get(path)
            self.assertIn(r.status_code, (400, 404), path)
            self.assertNotIn(b"RG_API_KEY", r.data, path)

    def test_api_key_not_in_responses(self):
        r = self.client.get("/")
        self.assertNotIn(FAKE_KEY.encode(), r.data)

    def test_default_listens_on_localhost_only(self):
        import web.app as wa
        seen = {}

        class FakeApp:
            def run(self, host, port, debug):
                seen.update(host=host, debug=debug)

        with mock.patch.object(sys, "argv", ["web.app"]), \
                mock.patch.object(wa, "load_dotenv"), \
                mock.patch.object(wa.Config, "from_env", return_value=Config()), \
                mock.patch.object(wa, "create_app", return_value=FakeApp()):
            wa.main()
        self.assertEqual(seen, {"host": "127.0.0.1", "debug": False})


# ------------------------------------------------------------------ 5. Host check (DNS rebinding)
class TestHostCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from web.app import create_app
        cfg = Config(api_key=FAKE_KEY, db_path=os.devnull)
        cls.local = create_app(cfg).test_client()
        cls.lan = create_app(cfg, allow_lan=True).test_client()

    def status(self, client, host, path="/"):
        with mock.patch("web.app.ResourcesAPI"), mock.patch("web.app.Database"), \
                mock.patch("web.app.data"):
            return client.get(path, headers={"Host": host}).status_code

    def test_local_names_allowed(self):
        for host in ("127.0.0.1:8050", "localhost:8050", "[::1]:8050", "localhost"):
            self.assertEqual(self.status(self.local, host), 200, host)

    def test_foreign_domain_blocked(self):
        for host in ("evil.example:8050", "evil.example", "localhost.evil.example",
                     "127.0.0.1.evil.example", "192.168.1.20:8050", "mac.local:8050", ""):
            for path in ("/", "/api/overview", "/api/status"):
                self.assertEqual(self.status(self.local, host, path), 403, f"{host} {path}")

    def test_refresh_blocked_for_foreign_domain(self):
        with mock.patch("web.app.ResourcesAPI") as api, mock.patch("web.app.Database"):
            r = self.local.post("/api/refresh/warehouse", headers={
                "Host": "evil.example:8050", "X-Requested-With": "rgtool"})
        self.assertEqual(r.status_code, 403)
        api.assert_not_called()

    def test_lan_mode_allows_ip_and_local_name(self):
        for host in ("192.168.1.20:8050", "10.0.0.5", "MacBook.local:8050", "localhost:8050"):
            self.assertEqual(self.status(self.lan, host), 200, host)

    def test_lan_mode_still_blocks_domains(self):
        for host in ("evil.example:8050", "192.168.1.20.evil.example", "a.b.local"):
            self.assertEqual(self.status(self.lan, host), 403, host)


if __name__ == "__main__":
    unittest.main(verbosity=2)
