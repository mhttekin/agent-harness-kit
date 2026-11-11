"""Protocol tests do not launch an agent or access the network."""

from scripts.codex_stop import stop_response


def test_stop_protocol():
    assert stop_response("{}", 0, "") == {}
    assert stop_response("{}", 2, "broken") == {"decision": "block", "reason": "broken"}
    assert stop_response('{"stop_hook_active":true}', 2, "broken") == {
        "systemMessage": "checks still failing: broken"
    }
