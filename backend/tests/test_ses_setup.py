"""Tests for the SES pre-flight checker and the single-send helper."""

import pytest

from app.config import Settings
from app.scripts import check_ses, send_test

BASE = {
    "app_env": "test",
    "mail_provider": "ses",
    "aws_region": "ap-south-1",
    "aws_access_key_id": "AKIAEXAMPLE1234",
    "aws_secret_access_key": "secret-example-value",
    "ses_from_email": "noreply@testingmail2btd.net",
}


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **(BASE | overrides))


def test_mask_never_reveals_full_secret() -> None:
    assert check_ses.mask("AKIAEXAMPLE1234") == "AKIA...1234"
    assert check_ses.mask(None) == "(unset)"
    assert check_ses.mask("short") == "*****"


def test_domain_of() -> None:
    assert check_ses.domain_of("noreply@testingmail2btd.net") == "testingmail2btd.net"
    assert check_ses.domain_of("broken") == ""


def test_check_settings_reports_ready(capsys: pytest.CaptureFixture[str]) -> None:
    report = check_ses.Report()
    assert check_ses.check_settings(_settings(), report) is True
    assert report.failed == 0
    printed = capsys.readouterr().out
    assert "secret-example-value" not in printed


def test_check_settings_fails_without_secret(capsys: pytest.CaptureFixture[str]) -> None:
    report = check_ses.Report()
    assert check_ses.check_settings(_settings(aws_secret_access_key=None), report) is False
    assert report.failed == 1
    assert "AWS_SECRET_ACCESS_KEY" in capsys.readouterr().out


def test_check_settings_warns_about_fake_provider() -> None:
    report = check_ses.Report()
    check_ses.check_settings(_settings(mail_provider="fake"), report)
    assert any(status == check_ses.WARN for status, _, _ in report.rows)


def test_check_settings_warns_about_missing_configuration_set() -> None:
    report = check_ses.Report()
    check_ses.check_settings(_settings(ses_configuration_set=None), report)
    names = [name for status, name, _ in report.rows if status == check_ses.WARN]
    assert "SES_CONFIGURATION_SET" in names


def test_offline_mode_exit_code(capsys: pytest.CaptureFixture[str], monkeypatch) -> None:
    monkeypatch.setattr(check_ses, "Settings", lambda: _settings())
    assert check_ses.main(["--offline"]) == 0
    assert "failures: 0" in capsys.readouterr().out


def test_offline_mode_fails_on_bad_from_email(monkeypatch) -> None:
    monkeypatch.setattr(check_ses, "Settings", lambda: _settings(ses_from_email="nope"))
    assert check_ses.main(["--offline"]) == 1


def test_send_test_refuses_when_provider_is_fake(monkeypatch, capsys) -> None:
    monkeypatch.setattr(send_test, "Settings", lambda: _settings(mail_provider="fake"))
    assert send_test.main(["--to", "a@example.com"]) == 2
    assert "Refusing to send" in capsys.readouterr().out


def test_send_test_refuses_self_send(monkeypatch, capsys) -> None:
    monkeypatch.setattr(send_test, "Settings", lambda: _settings())
    assert send_test.main(["--to", "noreply@testingmail2btd.net"]) == 2
    assert "same as the From" in capsys.readouterr().out


def test_send_test_sends_one_message(monkeypatch, capsys) -> None:
    sent = {}

    class FakeProvider:
        def __init__(self, settings):  # noqa: ARG002
            pass

        def submit(self, message):
            from app.providers.email import SubmissionResult

            sent["message"] = message
            return SubmissionResult(
                provider_message_id="ses-123", accepted=True, provider_name="ses"
            )

    monkeypatch.setattr(send_test, "Settings", lambda: _settings())
    monkeypatch.setattr(send_test, "SESEmailProvider", FakeProvider)

    assert send_test.main(["--to", "success@simulator.amazonses.com"]) == 0
    assert sent["message"].recipients == ("success@simulator.amazonses.com",)
    out = capsys.readouterr().out
    assert "ses-123" in out
    assert "acceptance receipt only" in out
