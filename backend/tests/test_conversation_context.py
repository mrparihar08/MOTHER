import json
import pytest
from unittest.mock import MagicMock

from backend.chats.utils.intent_router import classify_intent, Intent
from backend.chats.services.news_service import is_news_summary_query
from backend.chats.handlers.chatbot_handler import (
    _extract_display_text,
    _build_history_context,
    _build_system_instruction,
)


class TestFollowUpContextRouting:
    """
    Ensure multi-turn conversational follow-up questions are NOT hijacked by news summary routing.
    Queries like 'Day 1 ko detail mein samjhao' or 'Is code ko explain karo' should route to general knowledge / chatbot.
    """

    @pytest.mark.parametrize(
        "query",
        [
            "Is topic ko simple language mein samjhao",
            "Is topic ko beginner-friendly Hinglish mein samjhao",
            "Iska example do",
            "Is code ko explain karo",
            "Day 1 ko detail mein samjhao",
            "Pichhle answer ka short summary banao",
            "Python mein iska alternative kya hai?",
            "Is concept ko real world example ke saath samjhao",
        ],
    )
    def test_technical_followup_is_not_news_summary(self, query):
        assert not is_news_summary_query(query)
        intent = classify_intent(query)
        assert intent != Intent.NEWS and intent != Intent.NEWS_SUMMARY

    @pytest.mark.parametrize(
        "query",
        [
            "Is news ko simple Hindi mein samjhao",
            "Is news ka short summary banao",
            "Is khabar ka source aur publication date batao",
            "Is article ko summarize karo",
        ],
    )
    def test_actual_news_followup_is_detected(self, query):
        assert is_news_summary_query(query) or classify_intent(query) in (Intent.NEWS, Intent.NEWS_SUMMARY)


class TestHistoryContextFormatting:
    """
    Verify that structured responses (JSON containing news, text, widgets) are cleanly
    unpacked so LLM history receives clean human-readable conversation text.
    """

    def test_extract_display_text_plain_string(self):
        assert _extract_display_text("Hello Vitya") == "Hello Vitya"

    def test_extract_display_text_json_with_content(self):
        raw = json.dumps({"type": "text", "content": "Python is an interpreted language."})
        assert _extract_display_text(raw) == "Python is an interpreted language."

    def test_extract_display_text_json_with_news_summary(self):
        raw = json.dumps({"type": "news", "text_summary": "Top headlines of today in India."})
        assert _extract_display_text(raw) == "Top headlines of today in India."

    def test_extract_display_text_json_with_intro(self):
        raw = json.dumps({"type": "news", "intro": "Breaking news updates across Madhya Pradesh."})
        assert _extract_display_text(raw) == "Breaking news updates across Madhya Pradesh."

    def test_build_history_context_empty_db(self):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        result = _build_history_context(mock_db, conversation_id="conv-123")
        assert result == ""

    def test_build_history_context_with_turns(self):
        mock_db = MagicMock()
        turn1_user = MagicMock(role="user", content="Python mein list aur tuple ka difference samjhao")
        turn1_bot = MagicMock(
            role="assistant",
            content=json.dumps({"type": "text", "content": "List mutable hai aur tuple immutable hai."}),
        )
        # Reversed order as queried from DB (descending)
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            turn1_bot,
            turn1_user,
        ]

        context = _build_history_context(mock_db, conversation_id="conv-123")
        assert "User: Python mein list aur tuple ka difference samjhao" in context
        assert "Assistant: List mutable hai aur tuple immutable hai." in context
        assert '{"type": "text"' not in context  # Raw JSON must NOT leak into prompt history


class TestSystemInstructionQuality:
    """
    Verify that system instructions enforce:
    1. Multi-turn context awareness (no generic clarification loops)
    2. Elimination of repetitive user name mentions
    3. Elimination of robotic formulaic closing questions
    4. Secure FastAPI JWT authentication practices (Passlib bcrypt, signed JWT with exp)
    """

    def test_system_instruction_directives(self):
        instruction = _build_system_instruction(user_name="Pradeep")

        # Context awareness
        assert "CONVERSATION CONTEXT & FOLLOW-UP RESOLUTION" in instruction
        assert "ALWAYS resolve 'this topic' / 'iska' / 'is code' / 'Day 1'" in instruction

        # Tone & style directives
        assert "AVOID NAME REPETITION" in instruction
        assert "NO FORMULAIC FILLER" in instruction

        # Secure coding directives
        assert "signed JWT" in instruction
        assert "python-jose" in instruction or "PyJWT" in instruction
        assert "bcrypt" in instruction

        # API testing directives
        assert "assert response.status_code == 200" in instruction
        assert "app.dependency_overrides" in instruction
        assert "NEVER write ambiguous assertions" in instruction

        # Safe optimization directives
        assert "Follow safe refactoring" in instruction
        assert "Never make unsubstantiated claims" in instruction


class TestPythonCodeQualityAndValidation:
    """Verify AST-based Python syntax validation and error detection."""

    def test_valid_palindrome_code_syntax(self):
        from backend.chats.services.code_validator import validate_python_syntax
        palindrome_code = """
def check_palindrome(text: str) -> bool:
    clean_text = ''.join(c.lower() for c in text if c.isalnum())
    return clean_text == clean_text[::-1]

assert check_palindrome("Madam") is True
assert check_palindrome("hello") is False
"""
        is_valid, err, code = validate_python_syntax(palindrome_code)
        assert is_valid is True
        assert err is None

    def test_auto_fix_unindented_else_block(self):
        from backend.chats.services.code_validator import validate_python_syntax
        # Typical LLM syntax bug: unindented else block relative to if
        broken_code = """
def is_even(n):
    if n % 2 == 0:
        return True
else:
        return False
"""
        is_valid, err, fixed_code = validate_python_syntax(broken_code)
        assert is_valid is True
        assert "    else:" in fixed_code or "else:" in fixed_code

    def test_invalid_syntax_detected_honestly(self):
        from backend.chats.services.code_validator import validate_python_syntax
        invalid_code = "def broken_func(:\n    return 42"
        is_valid, err, _ = validate_python_syntax(invalid_code)
        assert is_valid is False
        assert err is not None

    def test_non_python_languages_not_subject_to_python_ast(self):
        from backend.chats.services.code_validator import sanitize_code_block_content
        # JavaScript syntax is valid JS but would fail Python ast.parse
        js_code = "const greet = (name) => { console.log(`Hello ${name}`); };"
        code, is_valid, err = sanitize_code_block_content("javascript", js_code)
        assert is_valid is True
        assert err is None
        assert "const greet" in code


class TestMarkdownAndCodeSanitization:
    """Verify post-processing sanitization for markdown, code headers, and repeated phrases."""

    def test_remove_hallucinated_copy_button_in_code_block(self):
        from backend.chats.services.code_validator import sanitize_markdown_response
        raw_markdown = """Here is the solution:
```python
Copy
def add(a, b):
    return a + b
```
"""
        cleaned = sanitize_markdown_response(raw_markdown)
        assert "Copy\ndef" not in cleaned
        assert "def add(a, b):" in cleaned

    def test_clean_literal_br_tags_in_markdown_tables(self):
        from backend.chats.services.code_validator import sanitize_markdown_response
        table_markdown = """
| Feature | List | Tuple |
| --- | --- | --- |
| Mutability | Mutable<br>Can change | Immutable<br>Cannot change |
"""
        cleaned = sanitize_markdown_response(table_markdown)
        assert "<br>" not in cleaned.lower()
        assert "| Feature | List | Tuple |" in cleaned

    def test_strip_repeated_user_names_in_subsequent_paragraphs(self):
        from backend.chats.services.code_validator import sanitize_markdown_response
        multi_para = (
            "Pradeep ji, Python mein slicing bohot useful feature hai.\n\n"
            "Pradeep ji, isko samajhne ke liye hum ek example dekhte hain.\n\n"
            "Pradeep ji, ab aap isko run karke dekh sakte hain."
        )
        cleaned = sanitize_markdown_response(multi_para, user_name="Pradeep")
        # First paragraph greeting preserved
        assert cleaned.startswith("Pradeep ji,")
        # Subsequent paragraphs stripped of redundant greeting
        assert "Pradeep ji, isko" not in cleaned
        assert "Pradeep ji, ab" not in cleaned

    def test_strip_robotic_formulaic_closing_questions(self):
        from backend.chats.services.code_validator import sanitize_markdown_response
        raw_text = """def square(x):
    return x * x

Pradeep ji, kya aapko iske baare mein aur detail chahiye? Mujhe batayein!"""
        cleaned = sanitize_markdown_response(raw_text, user_name="Pradeep")
        assert "Mujhe batayein!" not in cleaned


class TestTechnicalConceptRouting:
    """
    Verify common technical concepts are classified as GENERAL_KNOWLEDGE / coding
    and never hijacked by news, charts, or financial rules.
    """

    @pytest.mark.parametrize(
        "query",
        [
            "Python mein palindrome check karne ka code likho",
            "HTTP 401 aur 403 mein kya difference hai?",
            "Mere API endpoint ko test karne ke liye test cases banao",
            "Environment variables ko .env file mein kaise use karte hain?",
            "Mere code ke liye unit tests likho",
            "Mere code ko optimize karo, lekin existing functionality mat todo",
            "FastAPI authentication JWT example samjhao",
            "REST API aur GraphQL mein difference kya hai",
        ],
    )
    def test_technical_queries_are_general_knowledge(self, query):
        intent = classify_intent(query)
        assert intent == Intent.GENERAL_KNOWLEDGE
        assert not is_news_summary_query(query)

