from genesis_core.state import StateStore


def test_sessions_and_messages_are_persistent(tmp_path):
    database = tmp_path / "genesis.db"
    first = StateStore(database)
    session = first.create_session("Shared workspace")
    first.add_message(session["id"], "user", "Hello from TUI")

    second = StateStore(database)
    assert second.get_session(session["id"])["title"] == "Shared workspace"
    messages = second.list_messages(session["id"])
    assert len(messages) == 1
    assert messages[0]["content"] == "Hello from TUI"
    assert messages[0]["role"] == "user"


def test_first_user_message_sets_session_title(tmp_path):
    store = StateStore(tmp_path / "genesis.db")
    session = store.create_session()
    store.add_message(session["id"], "user", "Plan my research project")

    assert store.get_session(session["id"])["title"] == "Plan my research project"


def test_missing_session_rejects_message(tmp_path):
    store = StateStore(tmp_path / "genesis.db")
    try:
        store.add_message("missing", "user", "Hello")
    except KeyError:
        pass
    else:
        raise AssertionError("Expected missing session to raise KeyError")
