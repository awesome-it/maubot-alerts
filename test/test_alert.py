import pytest
from alertbot.main import Alert


class TestAlert:
    """Test the Alert dataclass"""

    def test_alert_firing_color(self):
        """Test that firing alerts are red"""
        alert = Alert(
            fingerprint="test-123",
            status="firing",
            alertmanager_data={
                "labels": {"alertname": "TestAlert"},
                "annotations": {"description": "Test description"},
                "generatorURL": "http://example.com",
            },
        )
        alert.generate_message()
        assert "red" in alert.message

    def test_alert_acknowledged_color(self):
        """Test that acknowledged alerts are orange"""
        alert = Alert(
            fingerprint="test-123",
            status="acknowledged",
            alertmanager_data={
                "labels": {"alertname": "TestAlert"},
                "annotations": {"description": "Test description"},
                "generatorURL": "http://example.com",
            },
        )
        alert.generate_message()
        assert "orange" in alert.message

    def test_alert_resolved_color(self):
        """Test that resolved alerts are green"""
        alert = Alert(
            fingerprint="test-123",
            status="resolved",
            alertmanager_data={
                "labels": {"alertname": "TestAlert"},
                "annotations": {"description": "Test description"},
                "generatorURL": "http://example.com",
            },
        )
        alert.generate_message()
        assert "green" in alert.message

    def test_alert_with_actor(self):
        """Test that last_actor is included in message"""
        alert = Alert(
            fingerprint="test-123",
            status="acknowledged",
            alertmanager_data={
                "labels": {"alertname": "TestAlert"},
                "annotations": {"description": "Test description"},
                "generatorURL": "http://example.com",
            },
            last_actor="@user:example.com",
        )
        alert.generate_message()
        assert "by @user:example.com" in alert.message
