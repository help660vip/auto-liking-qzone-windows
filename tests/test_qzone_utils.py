import json
import tempfile
import unittest
from pathlib import Path

from qzone_utils import (
    ConfigError,
    Credentials,
    calculate_g_tk,
    cookie_value,
    extract_callback_code,
    load_credentials,
    save_credentials,
    validate_qq,
)


class QZoneUtilsTests(unittest.TestCase):
    def test_validate_qq(self):
        self.assertEqual(validate_qq("12345"), "12345")
        self.assertEqual(validate_qq(123456789), "123456789")
        for invalid in ("", "01234", "1234", "1234567890123", "12ab5"):
            with self.subTest(invalid=invalid), self.assertRaises(ConfigError):
                validate_qq(invalid)

    def test_cookie_value(self):
        header = "uin=o12345; p_skey=@abc=123; theme=dark"
        self.assertEqual(cookie_value(header, "p_skey"), "@abc=123")
        self.assertIsNone(cookie_value(header, "missing"))

    def test_calculate_g_tk_has_stable_result(self):
        self.assertEqual(calculate_g_tk("@abc"), 2088882539)
        self.assertEqual(calculate_g_tk("test"), 2090756197)

    def test_extract_callback_code_supports_json_and_jsonp(self):
        self.assertEqual(extract_callback_code('{"code": 0}'), 0)
        self.assertEqual(extract_callback_code("callback({'code':-3000})"), -3000)
        self.assertIsNone(extract_callback_code("not a result"))

    def test_credentials_can_derive_g_tk_from_cookie(self):
        credentials = Credentials.from_mapping(
            {
                "qq": "12345",
                "cookie_str": "uin=o12345; p_skey=@abc",
                "user_agent": "test-agent",
            }
        )
        self.assertEqual(credentials.g_tk, 2088882539)

    def test_credentials_round_trip(self):
        credentials = Credentials(
            qq="12345",
            cookie_str="uin=o12345; p_skey=@abc",
            user_agent="test-agent",
            g_tk=2088882539,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            save_credentials(path, credentials)
            loaded = load_credentials(path)

        self.assertEqual(loaded.qq, credentials.qq)
        self.assertEqual(loaded.cookie_str, credentials.cookie_str)
        self.assertEqual(loaded.g_tk, credentials.g_tk)
        self.assertTrue(loaded.updated_at)

    def test_load_credentials_rejects_non_object_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            path.write_text(json.dumps(["unexpected"]), encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_credentials(path)


if __name__ == "__main__":
    unittest.main()
