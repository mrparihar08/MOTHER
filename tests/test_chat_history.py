import pytest
from backend.api.auth import create_access_token
from backend.api.models.vitya import User, Conversation, ChatMessage


@pytest.fixture
def chat_user(db_session):
    user = User(
        name="Chat User",
        username="chatuser",
        email="chat@example.com",
        password="hashed_pass",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_chat_message_persistence(client, chat_user):
    token = create_access_token({"user_id": chat_user.id})
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Send chat message
    response = client.post(
        "/api/chat/",
        json={"message": "What is Vitya AI?"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "conversation_id" in data

    conv_id = data["conversation_id"]

    # 2. Fetch history and verify user + assistant messages exist in DB
    history_res = client.get("/api/chat/history", headers=headers)
    assert history_res.status_code == 200
    history = history_res.json()

    assert history["conversation_id"] == conv_id
    messages = history["messages"]
    assert len(messages) >= 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "What is Vitya AI?"
    assert messages[1]["role"] == "assistant"


def test_clear_chat_history(client, chat_user):
    token = create_access_token({"user_id": chat_user.id})
    headers = {"Authorization": f"Bearer {token}"}

    client.post(
        "/api/chat/",
        json={"message": "Hello bot"},
        headers=headers,
    )

    del_res = client.delete("/api/chat/history", headers=headers)
    assert del_res.status_code == 200

    history_res = client.get("/api/chat/history", headers=headers)
    assert history_res.json()["messages"] == []
