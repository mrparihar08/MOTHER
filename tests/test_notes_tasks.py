import pytest
from backend.api.auth import create_access_token
from backend.api.models.vitya import User


@pytest.fixture
def test_users(db_session):
    user1 = User(name="User One", username="user1", email="user1@example.com", password="hashed_pass1")
    user2 = User(name="User Two", username="user2", email="user2@example.com", password="hashed_pass2")
    db_session.add_all([user1, user2])
    db_session.commit()
    db_session.refresh(user1)
    db_session.refresh(user2)
    return user1, user2


def test_notes_user_isolation(client, test_users):
    user1, user2 = test_users
    token1 = create_access_token({"user_id": user1.id})
    headers1 = {"Authorization": f"Bearer {token1}"}

    token2 = create_access_token({"user_id": user2.id})
    headers2 = {"Authorization": f"Bearer {token2}"}

    # User 1 creates note
    res1 = client.post("/api/notes/", json={"content": "Secret note 1"}, headers=headers1)
    assert res1.status_code == 201
    note1_id = res1.json()["id"]
    assert res1.json()["user_id"] == user1.id

    # User 2 gets notes -> should be empty
    res2 = client.get("/api/notes/", headers=headers2)
    assert res2.status_code == 200
    assert len(res2.json()) == 0

    # User 2 tries to update User 1's note -> should return 404
    res_update = client.put(f"/api/notes/{note1_id}", json={"content": "Hacked"}, headers=headers2)
    assert res_update.status_code == 404

    # User 2 tries to delete User 1's note -> should return 404
    res_delete = client.delete(f"/api/notes/{note1_id}", headers=headers2)
    assert res_delete.status_code == 404

    # User 1 gets notes -> should see note
    res1_get = client.get("/api/notes/", headers=headers1)
    assert res1_get.status_code == 200
    assert len(res1_get.json()) == 1
    assert res1_get.json()[0]["content"] == "Secret note 1"


def test_tasks_user_isolation(client, test_users):
    user1, user2 = test_users
    token1 = create_access_token({"user_id": user1.id})
    headers1 = {"Authorization": f"Bearer {token1}"}

    token2 = create_access_token({"user_id": user2.id})
    headers2 = {"Authorization": f"Bearer {token2}"}

    # User 1 creates task
    res1 = client.post("/api/tasks/", json={"title": "Private task 1"}, headers=headers1)
    assert res1.status_code == 201
    task1_id = res1.json()["id"]
    assert res1.json()["user_id"] == user1.id

    # User 2 gets tasks -> empty
    res2 = client.get("/api/tasks/", headers=headers2)
    assert res2.status_code == 200
    assert len(res2.json()) == 0

    # User 2 tries to update User 1's task -> 404
    res_update = client.put(f"/api/tasks/{task1_id}", json={"title": "Hacked Task"}, headers=headers2)
    assert res_update.status_code == 404

    # User 2 tries to delete User 1's task -> 404
    res_delete = client.delete(f"/api/tasks/{task1_id}", headers=headers2)
    assert res_delete.status_code == 404
