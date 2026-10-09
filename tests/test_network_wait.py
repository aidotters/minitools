"""wait_for_network と ArxivCollector の接続リトライのテスト"""

import socket
from unittest.mock import MagicMock, patch

import pytest
import requests

from minitools.collectors.arxiv import ArxivCollector
from minitools.utils import network
from minitools.utils.network import wait_for_network


class FakeClock:
    """time.monotonic / time.sleep を差し替える疑似時計"""

    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(network.time, "monotonic", fake.monotonic)
    monkeypatch.setattr(network.time, "sleep", fake.sleep)
    return fake


class TestWaitForNetwork:
    def test_returns_true_immediately_when_resolvable(self, clock, monkeypatch):
        monkeypatch.setattr(socket, "getaddrinfo", lambda host, port: [("ok",)])

        assert wait_for_network(["example.com"]) is True
        assert clock.sleeps == []

    def test_retries_until_resolvable(self, clock, monkeypatch):
        calls = {"n": 0}

        def flaky(host, port):
            calls["n"] += 1
            if calls["n"] <= 2:
                raise socket.gaierror(8, "nodename nor servname provided")
            return [("ok",)]

        monkeypatch.setattr(socket, "getaddrinfo", flaky)

        assert wait_for_network(["example.com"], timeout=60, interval=5) is True
        assert clock.sleeps == [5, 5]

    def test_succeeds_if_any_host_resolves(self, clock, monkeypatch):
        def only_second(host, port):
            if host == "bad.example":
                raise socket.gaierror(8, "fail")
            return [("ok",)]

        monkeypatch.setattr(socket, "getaddrinfo", only_second)

        assert wait_for_network(["bad.example", "good.example"]) is True

    def test_returns_false_after_timeout(self, clock, monkeypatch):
        def always_fail(host, port):
            raise socket.gaierror(8, "fail")

        monkeypatch.setattr(socket, "getaddrinfo", always_fail)

        assert wait_for_network(["example.com"], timeout=12, interval=5) is False
        # 5 + 5 + 2（残り時間で打ち切り）
        assert clock.sleeps == [5, 5, 2]


class TestArxivSearchRetry:
    @patch("minitools.collectors.arxiv.time.sleep")
    @patch("minitools.collectors.arxiv.requests.get")
    def test_retries_on_connection_error(self, mock_get, mock_sleep):
        ok = MagicMock()
        ok.text = "<feed></feed>"
        mock_get.side_effect = [requests.ConnectionError("dns"), ok]

        papers = ArxivCollector().search(["LLM"], "20261008", "20261008")

        assert papers == []
        assert mock_get.call_count == 2
        mock_sleep.assert_called_once_with(5.0)

    @patch("minitools.collectors.arxiv.time.sleep")
    @patch("minitools.collectors.arxiv.requests.get")
    def test_gives_up_after_max_retries(self, mock_get, mock_sleep):
        mock_get.side_effect = requests.ConnectionError("dns")

        papers = ArxivCollector().search(["LLM"], "20261008", "20261008")

        assert papers == []
        assert mock_get.call_count == 4
        assert [c.args[0] for c in mock_sleep.call_args_list] == [5.0, 10.0, 20.0]
