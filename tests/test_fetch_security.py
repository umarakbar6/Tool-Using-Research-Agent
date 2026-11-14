import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from research_agent.fetch import FetchError, _connect_public, validate_public_url

def address(ip):
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 443))]

class PublicConnectionTests(unittest.TestCase):
    def test_dns_rebinding_is_rejected_before_connecting(self):
        with patch("socket.getaddrinfo", side_effect=[address("8.8.8.8"), address("127.0.0.1")]), patch("socket.socket") as create:
            validate_public_url("https://example.com")
            with self.assertRaises(FetchError) as result:
                _connect_public(("example.com", 443), 3)
            self.assertEqual(result.exception.code, "private_network_blocked")
            create.assert_not_called()
    def test_connection_uses_the_checked_numeric_address(self):
        connection = Mock()
        with patch("socket.getaddrinfo", return_value=address("8.8.8.8")) as resolve, patch("socket.socket", return_value=connection):
            self.assertIs(_connect_public(("example.com", 443), 3), connection)
            self.assertEqual(resolve.call_count, 1)
            connection.connect.assert_called_once_with(("8.8.8.8", 443))
    def test_shared_address_space_is_rejected(self):
        with patch("socket.getaddrinfo", return_value=address("100.64.0.1")), patch("socket.socket") as create:
            with self.assertRaises(FetchError):
                _connect_public(("example.com", 443), 3)
            create.assert_not_called()
    def test_mixed_public_private_answers_fail_closed(self):
        with patch("socket.getaddrinfo", return_value=address("8.8.8.8") + address("10.0.0.1")), patch("socket.socket") as create:
            with self.assertRaises(FetchError):
                _connect_public(("example.com", 443), 3)
            create.assert_not_called()
if __name__ == "__main__":
    unittest.main()
