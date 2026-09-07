from alertbot.alerts import Alert, AlertGroup
from alertbot.template import TemplateRenderer


def make_renderer() -> TemplateRenderer:
    return TemplateRenderer()


def make_group(status: str, last_actor: str | None = None) -> AlertGroup:
    group = AlertGroup(
        group_key="test-group",
        status=status,
        receiver="team-x",
        group_labels={"alertname": "TestAlert"},
        common_labels={},
        common_annotations={"summary": "Test summary"},
        truncated_alerts=0,
        external_url="http://example.com",
    )
    group.last_actor = last_actor
    return group


class TestAlertGroup:
    """Test the AlertGroup title rendering (status color + last_actor)."""

    def test_firing_color(self):
        """Firing alert groups are red."""
        group = make_group("firing")
        group.generate_message(make_renderer())
        assert "#d32f2f" in group.message

    def test_acknowledged_color(self):
        """Acknowledged alert groups are orange."""
        group = make_group("acknowledged")
        group.generate_message(make_renderer())
        assert "#ed6c02" in group.message

    def test_resolved_color(self):
        """Resolved alert groups are green."""
        group = make_group("resolved")
        group.generate_message(make_renderer())
        assert "#2e7d32" in group.message

    def test_with_actor(self):
        """last_actor is included in the title."""
        group = make_group("acknowledged", last_actor="@user:example.com")
        group.generate_message(make_renderer())
        assert "by @user:example.com" in group.message

    def test_without_actor(self):
        """No actor annotation when last_actor is unset."""
        group = make_group("firing")
        group.generate_message(make_renderer())
        assert "by " not in group.message


class TestAlert:
    """Test the per-alert message rendering."""

    def test_message_contains_labels_and_summary(self):
        """Unique labels, summary and generator URL are rendered."""
        alert = Alert(
            fingerprint="test-123",
            status="firing",
            alertmanager_data={
                "labels": {"alertname": "TestAlert", "severity": "critical"},
                "annotations": {"summary": "Test summary"},
                "generatorURL": "http://example.com",
            },
        )
        alert.generate_unique_labels(common_labels={})
        alert.generate_message(make_renderer())
        assert "severity" in alert.message
        assert "critical" in alert.message
        assert "Test summary" in alert.message
        assert "http://example.com" in alert.message
