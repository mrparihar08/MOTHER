from __future__ import annotations

import re
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from backend.api.models.vitya import Conversation, ChatMessage
from backend.chats.services.gemini_service import generate_response

logger = logging.getLogger(__name__)


def _extract_text_for_context(content: Any) -> str:
    """Extract human-readable text from raw string or JSON payload."""
    if not content:
        return ""
    trimmed = str(content).strip()
    if trimmed.startswith("{") and trimmed.endswith("}"):
        try:
            parsed = json.loads(trimmed)
            if isinstance(parsed, dict):
                return (
                    parsed.get("text_summary")
                    or parsed.get("reply")
                    or parsed.get("content")
                    or parsed.get("text")
                    or parsed.get("title")
                    or trimmed
                )
        except Exception:
            pass
    return trimmed


class ConversationContextManager:
    """
    Centralized Intelligent Context & Memory Manager for Vidya.AI.
    Unifies Chat Assistant and Voice Assistant so they share identical conversation history,
    database records, multi-turn memory, and context retrieval.
    """

    @staticmethod
    def get_next_user_conv_index(db: Session, user_id: int) -> int:
        """Calculate the next user-scoped conversation number (1, 2, 3...) for this user."""
        max_idx = (
            db.query(func.max(Conversation.user_conv_index))
            .filter(Conversation.user_id == user_id)
            .scalar()
        )
        return (max_idx or 0) + 1

    @classmethod
    def resolve_conversation(
        cls,
        db: Session,
        user_id: int,
        conversation_id: Optional[Union[int, str]] = None,
        initial_title: Optional[str] = None,
    ) -> Conversation:
        """
        Find an existing conversation by index, ID, or unique_id, or initialize a new unified conversation.
        Guarantees that both Chat and Voice operate on the exact same conversation entity.
        """
        conv = None
        if conversation_id is not None:
            # 1. Match numeric ID (user_conv_index or primary key id)
            if isinstance(conversation_id, int) or (isinstance(conversation_id, str) and str(conversation_id).isdigit()):
                target_int = int(conversation_id)
                conv = (
                    db.query(Conversation)
                    .filter(
                        Conversation.user_conv_index == target_int,
                        Conversation.user_id == user_id,
                    )
                    .first()
                )
                if not conv:
                    conv = (
                        db.query(Conversation)
                        .filter(
                            Conversation.id == target_int,
                            Conversation.user_id == user_id,
                        )
                        .first()
                    )

            # 2. Match unique string UUID
            if not conv and isinstance(conversation_id, str):
                conv = (
                    db.query(Conversation)
                    .filter(
                        Conversation.unique_id == conversation_id.strip(),
                        Conversation.user_id == user_id,
                    )
                    .first()
                )

        if not conv:
            # Create a new unified conversation
            next_idx = cls.get_next_user_conv_index(db, user_id)
            title = initial_title or "New Conversation"
            conv = Conversation(
                user_id=user_id,
                user_conv_index=next_idx,
                title=title,
            )
            db.add(conv)
            db.commit()
            db.refresh(conv)
            logger.info("Created new unified conversation: id=%s index=%s user_id=%s", conv.id, next_idx, user_id)

        return conv

    @classmethod
    def build_conversation_context(
        cls,
        db: Session,
        conversation: Conversation,
        current_query: str,
        max_recent_turns: int = 14,
    ) -> Dict[str, Any]:
        """
        Builds a comprehensive, token-aware context representation for LLM prompts.
        Merges:
        1. Progressive conversation summary (long-term memory)
        2. Relevant older messages matching entities/keywords in the query
        3. Recent short-term messages (both Chat and Voice) in strict chronological order
        """
        all_messages: List[ChatMessage] = (
            db.query(ChatMessage)
            .filter(ChatMessage.conversation_id == conversation.id)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
            .all()
        )

        summary_text = getattr(conversation, "conversation_summary", None) or ""

        if not all_messages:
            return {
                "context_prompt": "",
                "summary": summary_text,
                "history_lines": [],
                "message_count": 0,
            }

        # Partition into recent window and older archival history
        recent_msgs = all_messages[-max_recent_turns:]
        older_msgs = all_messages[:-max_recent_turns] if len(all_messages) > max_recent_turns else []

        relevant_older_lines: List[str] = []
        if older_msgs and current_query:
            query_words = set(re.findall(r"\w{3,}", current_query.lower()))
            for om in older_msgs:
                clean_text = _extract_text_for_context(om.content)
                text_words = set(re.findall(r"\w{3,}", clean_text.lower()))
                overlap = query_words.intersection(text_words)
                if overlap:
                    mode_label = f" ({om.input_mode.capitalize()})" if getattr(om, "input_mode", None) else ""
                    role_str = "User" if om.role == "user" else "Assistant"
                    relevant_older_lines.append(f"{role_str}{mode_label}: {clean_text}")
                if len(relevant_older_lines) >= 4:
                    break

        # Build chronological recent turns
        recent_lines: List[str] = []
        for m in recent_msgs:
            clean_text = _extract_text_for_context(m.content)
            if not clean_text or clean_text.startswith("Generated file download"):
                continue
            mode_tag = f" ({m.input_mode.capitalize()})" if getattr(m, "input_mode", None) else ""
            role_name = "User" if m.role == "user" else "Assistant"
            recent_lines.append(f"{role_name}{mode_tag}: {clean_text}")

        # Assemble unified context prompt
        context_parts: List[str] = []
        if summary_text.strip():
            context_parts.append(f"--- LONG-TERM CONVERSATION SUMMARY & USER FACTS ---\n{summary_text.strip()}")

        if relevant_older_lines:
            context_parts.append(
                "--- RELEVANT PRIOR EXCERPTS FROM OLDER MESSAGES ---\n" + "\n".join(relevant_older_lines)
            )

        if recent_lines:
            context_parts.append(
                "--- ACTIVE CONVERSATION HISTORY (CHRONOLOGICAL CHAT & VOICE) ---\n" + "\n".join(recent_lines)
            )

        context_prompt = "\n\n".join(context_parts) if context_parts else ""

        return {
            "context_prompt": context_prompt,
            "summary": summary_text,
            "history_lines": recent_lines,
            "message_count": len(all_messages),
        }

    @classmethod
    def save_turn(
        cls,
        db: Session,
        conversation: Conversation,
        user_id: int,
        user_content: str,
        assistant_content: str,
        input_mode: str = "chat",
        message_status: str = "completed",
        meta_info: Optional[Dict[str, Any]] = None,
    ) -> Tuple[ChatMessage, ChatMessage]:
        """
        Atomically saves both user message and assistant response to the shared conversation.
        Records input_mode ('chat' or 'voice'), metadata (e.g. voice used, audio_url),
        updates conversation timestamps, and refreshes the long-term summary when appropriate.
        """
        user_msg = ChatMessage(
            conversation_id=conversation.id,
            user_id=user_id,
            role="user",
            content=user_content,
            input_mode=input_mode,
            message_status="completed",
        )
        assistant_msg = ChatMessage(
            conversation_id=conversation.id,
            user_id=user_id,
            role="assistant",
            content=assistant_content,
            input_mode=input_mode,
            message_status=message_status,
            meta_info=json.dumps(meta_info) if meta_info else None,
        )

        db.add(user_msg)
        db.add(assistant_msg)

        if hasattr(conversation, "updated_at"):
            conversation.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(user_msg)
        db.refresh(assistant_msg)

        # Update title if it's currently generic
        if conversation.title in ("New Conversation", "New Chat", None) and user_content:
            from backend.chats.chat import generate_conversation_title
            new_title = generate_conversation_title(user_content)
            if new_title and new_title != conversation.title:
                conversation.title = new_title
                db.commit()

        # Periodically refresh progressive summary for long conversations
        try:
            total_count = (
                db.query(func.count(ChatMessage.id))
                .filter(ChatMessage.conversation_id == conversation.id)
                .scalar() or 0
            )
            # Update summary every 6 messages once count reaches 8
            if total_count >= 8 and total_count % 6 == 0:
                cls.update_summary(db, conversation)
        except Exception as e:
            logger.warning("Auto-summary update check notice: %s", e)

        return user_msg, assistant_msg

    @classmethod
    def update_summary(cls, db: Session, conversation: Conversation) -> Optional[str]:
        """
        Generates and persists a concise, fact-dense progressive summary
        of important entities, user facts, ongoing tasks, names, and topics.
        """
        messages: List[ChatMessage] = (
            db.query(ChatMessage)
            .filter(ChatMessage.conversation_id == conversation.id)
            .order_by(ChatMessage.created_at.asc())
            .limit(30)
            .all()
        )
        if len(messages) < 4:
            return None

        dialogue = []
        for m in messages:
            clean = _extract_text_for_context(m.content)
            if clean:
                dialogue.append(f"{m.role.capitalize()}: {clean[:200]}")

        prompt = (
            "Summarize the following ongoing multi-turn conversation into 3-5 concise bullet points. "
            "Extract critical facts: user name, primary project, preferences, topics discussed, and action items. "
            "Do NOT invent any facts.\n\n"
            + "\n".join(dialogue)
            + "\n\nSummary:"
        )

        try:
            summary = generate_response(prompt, temperature=0.3)
            if summary and not summary.startswith("Gemini error") and "not configured" not in summary.lower():
                conversation.conversation_summary = summary.strip()
                db.commit()
                logger.info("Updated progressive summary for conversation_id=%s", conversation.id)
                return summary.strip()
        except Exception as e:
            logger.warning("Summary generation skipped: %s", e)
        return None
