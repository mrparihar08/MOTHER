import pytest
from datetime import datetime
from backend.api.auth import create_access_token
from backend.api.models.vitya import User, Expense


@pytest.fixture
def test_expense_data(db_session):
    user = User(name="Test User", username="testuser", email="test@example.com", password="hashed_pass")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    e1 = Expense(amount=100.0, category="Groceries", user_id=user.id, date=datetime(2025, 1, 1))
    e2 = Expense(amount=150.0, category="Groceries", user_id=user.id, date=datetime(2025, 2, 1))
    e3 = Expense(amount=200.0, category="Groceries", user_id=user.id, date=datetime(2025, 3, 1))
    db_session.add_all([e1, e2, e3])
    db_session.commit()
    return user


def test_predict_expense_async(client, test_expense_data):
    token = create_access_token({"user_id": test_expense_data.id})
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/ai/predict/Groceries", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["category"] == "Groceries"
    assert "predicted_next_month_expense" in data
    assert data["predicted_next_month_expense"] == 250.0


def test_web_search_service():
    from backend.chats.services.web_search_service import clean_html_tags, perform_web_search, format_web_search_context

    # 1. Test clean_html_tags
    raw_html = "<p>Hello <b>World</b> &amp; &quot;Testing&quot;</p>"
    cleaned = clean_html_tags(raw_html)
    assert cleaned == 'Hello World & "Testing"'

    # 2. Test format_web_search_context
    sample_results = [
        {"title": "Sample Title 1", "snippet": "Sample Snippet 1", "url": "https://example.com/1"},
        {"title": "Sample Title 2", "snippet": "Sample Snippet 2", "url": "https://example.com/2"},
    ]
    formatted = format_web_search_context("Test Query", sample_results)
    assert 'LIVE REAL-TIME WEB SEARCH RESULTS FOR: "Test Query"' in formatted
    assert "Sample Title 1" in formatted
    assert "https://example.com/1" in formatted

    # 3. Test perform_web_search gracefully handles query
    results = perform_web_search("Python programming language", max_results=3)
    assert isinstance(results, list)
    if results:
        assert "title" in results[0]
        assert "snippet" in results[0]


def test_ai_image_service():
    from backend.chats.services.ai_image_service import clean_prompt_for_image_gen, generate_ai_image

    cleaned = clean_prompt_for_image_gen("A futuristic cyber city with neon lights @#$%!")
    assert "futuristic cyber city" in cleaned

    img_url_or_path = generate_ai_image("cyberpunk city landscape")
    assert isinstance(img_url_or_path, str)
    assert len(img_url_or_path) > 0


def test_rag_service_and_endpoints(client, test_expense_data):
    from backend.chats.services.rag_service import rag_store, extract_document_text, chunk_text, format_rag_context

    # 1. Test CSV Parsing & Chunking
    sample_csv = b"Date,Category,Amount\n2026-01-01,Marketing,1500\n2026-01-02,Engineering,3200\n"
    csv_text = extract_document_text("financial_report.csv", sample_csv)
    assert "Category: Marketing" in csv_text
    assert "Amount: 1500" in csv_text

    # 2. Test Chunking & RAG Store Search
    chunks = chunk_text(csv_text, "financial_report.csv", chunk_size=300)
    assert len(chunks) > 0

    doc_info = rag_store.index_document(999, "financial_report.csv", sample_csv)
    assert doc_info["filename"] == "financial_report.csv"
    assert doc_info["chunk_count"] > 0

    search_results = rag_store.search(999, "What was the Engineering amount?", top_k=2)
    assert len(search_results) > 0
    assert "financial_report.csv" in search_results[0]["filename"]

    rag_formatted = format_rag_context("Engineering amount", search_results)
    assert "MULTI-DOCUMENT RAG CONTEXT" in rag_formatted
    assert "financial_report.csv" in rag_formatted

    # 3. Test RAG API Upload Endpoint
    token = create_access_token({"user_id": test_expense_data.id})
    headers = {"Authorization": f"Bearer {token}"}
    files = [("files", ("q1_report.txt", b"Q1 Revenue was $500,000 and Net Profit was $120,000.", "text/plain"))]
    
    res = client.post("/api/rag/upload", headers=headers, files=files, data={"conversation_id": 999})
    assert res.status_code == 200
    data = res.json()
    assert len(data["documents"]) >= 1

    # Test GET documents
    res_get = client.get("/api/rag/documents?conversation_id=999", headers=headers)
    assert res_get.status_code == 200
    assert len(res_get.json()["documents"]) >= 1

    # Test DELETE documents
    res_del = client.delete("/api/rag/documents?conversation_id=999", headers=headers)
    assert res_del.status_code == 200


