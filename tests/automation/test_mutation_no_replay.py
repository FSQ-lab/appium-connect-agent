from __future__ import annotations

from collections.abc import Iterator

import pytest

from appium_connect_agent.automation import CommandError

from ._action_protocol import (
    ActionProtocolService,
    ResponsePlan,
    connected,
    session_for,
    w3c_error,
)


def _dead_session() -> dict[str, object]:
    return {
        "value": {
            "error": "invalid session id",
            "message": "session is either terminated or not started",
            "stacktrace": "",
        }
    }


@pytest.fixture
def service() -> Iterator[ActionProtocolService]:
    with ActionProtocolService() as running:
        yield running


def test_read_dead_before_mutation_reattaches_then_dispatches_once(
    service: ActionProtocolService,
) -> None:
    service.queue("find", ResponsePlan(status=404, payload=_dead_session()))

    with connected(service) as connection:
        session = session_for(service, connection, "read-dead-before-write")
        session.element("id", "button").click()

        assert len(service.of_kind("create")) == 2
        assert len(service.of_kind("find")) == 2
        assert len(service.of_kind("action")) == 1
        assert session.session_info().state == "active"
        session.quit()


def test_dead_on_mutation_is_quarantined_without_replay(
    service: ActionProtocolService,
) -> None:
    service.queue("action", ResponsePlan(status=404, payload=_dead_session()))

    with connected(service) as connection:
        session = session_for(service, connection, "dead-on-write")
        with pytest.raises(CommandError) as caught:
            session.element("id", "button").click()

        assert caught.value.code == "command_failed"
        assert caught.value.request_state == "response_received"
        assert len(service.of_kind("create")) == 1
        assert len(service.of_kind("action")) == 1
        assert session.session_info().state == "uncertain"


def test_dead_read_after_mutation_does_not_replay_prior_write(
    service: ActionProtocolService,
) -> None:
    service.queue(
        "attribute",
        ResponsePlan(payload={"value": False}),
        ResponsePlan(status=404, payload=_dead_session()),
    )

    with connected(service) as connection:
        session = session_for(service, connection, "dead-read-after-write")
        with pytest.raises(CommandError) as caught:
            session.element("id", "field").perform_editor_action("done")

        assert caught.value.code == "command_failed"
        assert caught.value.request_state == "response_received"
        assert "focus_click_completed" in caught.value.completed_steps
        assert len(service.of_kind("create")) == 1
        assert len(service.of_kind("action")) == 1
        assert len(service.of_kind("attribute")) == 2
        assert session.session_info().state == "uncertain"


def test_temporary_setting_write_blocks_replay_and_restore_after_dead_read(
    service: ActionProtocolService,
) -> None:
    service.queue("find", ResponsePlan(status=404, payload=_dead_session()))

    with connected(service) as connection:
        session = session_for(service, connection, "setting-write-before-dead-read")
        raw = session.element("id", "odd/raw@id", raw_id=True)
        with pytest.raises(CommandError) as caught:
            raw.click()

        assert caught.value.code == "command_failed"
        assert caught.value.request_state == "response_received"
        assert len(service.of_kind("create")) == 1
        assert len(service.of_kind("settings:post")) == 1
        assert len(service.of_kind("find")) == 1
        assert len(service.of_kind("action")) == 0
        assert session.session_info().state == "uncertain"


def test_dead_settings_cleanup_preserves_primary_failure_and_quarantines(
    service: ActionProtocolService,
) -> None:
    service.queue("action", ResponsePlan(status=500, payload=w3c_error("rejected")))
    service.queue(
        "settings:post",
        ResponsePlan(),
        ResponsePlan(status=404, payload=_dead_session()),
    )

    with connected(service) as connection:
        session = session_for(service, connection, "dead-setting-cleanup")
        raw = session.element("id", "odd/raw@id", raw_id=True)
        with pytest.raises(CommandError) as caught:
            raw.click()

        error = caught.value
        assert error.code == "command_failed"
        assert error.request_state == "response_received"
        assert len(error.cleanup_errors) == 1
        cleanup = error.cleanup_errors[0]
        assert isinstance(cleanup, CommandError)
        assert cleanup.code == "command_failed"
        assert cleanup.request_state == "response_received"
        assert len(service.of_kind("create")) == 1
        assert len(service.of_kind("settings:post")) == 2
        assert len(service.of_kind("action")) == 1
        assert session.session_info().state == "uncertain"
