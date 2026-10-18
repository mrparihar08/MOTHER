import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api.models.vitya import Base, Conversation, ChatMessage, User
from backend.chats.chat import find_conversation_by_id


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()

    user = User(name="Test User", username="testuser", email="test@example.com", password="pwd")
    session.add(user)
    session.commit()
    session.refresh(user)

    yield session, user
    session.close()


def test_conversation_automatically_generates_unique_id(db_session):
    session, user = db_session
    conv = Conversation(user_id=user.id, title="Test Chat")
    session.add(conv)
    session.commit()
    session.refresh(conv)

    assert conv.id is not None
    assert conv.unique_id is not None
    assert conv.unique_id.startswith("conv_")
    assert len(conv.unique_id) >= 10


def test_find_conversation_by_id_or_unique_id(db_session):
    session, user = db_session
    conv1 = Conversation(user_id=user.id, title="Chat 1")
    conv2 = Conversation(user_id=user.id, title="Chat 2")
    session.add_all([conv1, conv2])
    session.commit()
    session.refresh(conv1)
    session.refresh(conv2)

    # Search by integer ID
    found_by_int = find_conversation_by_id(session, conv1.id, user.id)
    assert found_by_int is not None
    assert found_by_int.id == conv1.id

    # Search by numeric string ID
    found_by_num_str = find_conversation_by_id(session, str(conv1.id), user.id)
    assert found_by_num_str is not None
    assert found_by_num_str.id == conv1.id

    # Search by unique_id string
    found_by_unique = find_conversation_by_id(session, conv1.unique_id, user.id)
    assert found_by_unique is not None
    assert found_by_unique.id == conv1.id
    assert found_by_unique.unique_id == conv1.unique_id

    # Different conversation unique_id
    found_conv2 = find_conversation_by_id(session, conv2.unique_id, user.id)
    assert found_conv2 is not None
    assert found_conv2.id == conv2.id
    assert found_conv2.unique_id != conv1.unique_id

    # Non-existent ID
    assert find_conversation_by_id(session, "conv_nonexistent_9999", user.id) is None
    assert find_conversation_by_id(session, 999999, user.id) is None
