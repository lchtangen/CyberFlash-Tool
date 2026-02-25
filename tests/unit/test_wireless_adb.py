"""Unit tests for WirelessAdb — mocked AdbManager._run."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from cyberflash.core.wireless_adb import PairingResult, WirelessAdb


class TestPair:
    def test_successful_pair(self) -> None:
        with patch("cyberflash.core.wireless_adb.AdbManager._run",
                   return_value=(0, "Successfully paired", "")):
            result = WirelessAdb.pair("192.168.1.100", 37291, "123456")
        assert result.success is True
        assert result.ip == "192.168.1.100"
        assert result.port == 37291

    def test_failed_pair_returns_error(self) -> None:
        with patch("cyberflash.core.wireless_adb.AdbManager._run",
                   return_value=(1, "", "Failed to pair")):
            result = WirelessAdb.pair("192.168.1.100", 37291, "badcode")
        assert result.success is False
        assert result.error != ""


class TestConnect:
    def test_successful_connect(self) -> None:
        with patch("cyberflash.core.wireless_adb.AdbManager._run",
                   return_value=(0, "connected to 192.168.1.100:5555", "")):
            result = WirelessAdb.connect("192.168.1.100")
        assert result.success is True
        assert result.serial == "192.168.1.100:5555"

    def test_already_connected(self) -> None:
        with patch("cyberflash.core.wireless_adb.AdbManager._run",
                   return_value=(0, "already connected to 192.168.1.100:5555", "")):
            result = WirelessAdb.connect("192.168.1.100")
        assert result.success is True

    def test_connection_refused(self) -> None:
        with patch("cyberflash.core.wireless_adb.AdbManager._run",
                   return_value=(1, "failed to connect", "")):
            result = WirelessAdb.connect("10.0.0.1")
        assert result.success is False


class TestDisconnect:
    def test_disconnect_success(self) -> None:
        with patch("cyberflash.core.wireless_adb.AdbManager._run",
                   return_value=(0, "disconnected 192.168.1.100:5555", "")):
            ok = WirelessAdb.disconnect("192.168.1.100:5555")
        assert ok is True


class TestDiscoverMdns:
    def test_parses_service_entries(self) -> None:
        output = "adb-EMU001 transport_id:1  192.168.1.50:37291\n"
        with patch("cyberflash.core.wireless_adb.AdbManager._run",
                   return_value=(0, output, "")):
            services = WirelessAdb.discover_mdns()
        assert len(services) == 1
        assert services[0]["ip"] == "192.168.1.50"

    def test_empty_output_returns_empty(self) -> None:
        with patch("cyberflash.core.wireless_adb.AdbManager._run",
                   return_value=(0, "", "")):
            services = WirelessAdb.discover_mdns()
        assert services == []


class TestGenerateQrData:
    def test_qr_format(self) -> None:
        qr = WirelessAdb.generate_qr_data("192.168.1.1", 37291, "654321")
        assert qr.startswith("WIFI:T:ADB;")
        assert "654321" in qr
        assert "37291" in qr


class TestGetConnectedWifiDevices:
    def test_filters_ip_serials(self) -> None:
        with patch("cyberflash.core.wireless_adb.AdbManager.list_devices",
                   return_value=[
                       ("192.168.1.1:5555", "device"),
                       ("USBSERIAL001", "device"),
                       ("10.0.0.5:5555", "device"),
                   ]):
            devices = WirelessAdb.get_connected_wifi_devices()
        assert "192.168.1.1:5555" in devices
        assert "USBSERIAL001" not in devices
        assert "10.0.0.5:5555" in devices
