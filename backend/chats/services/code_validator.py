import ast
import re
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def validate_python_syntax(code: str) -> Tuple[bool, Optional[str], str]:
    """
    Validates Python code syntax using ast.parse.
    If a SyntaxError is detected, attempts non-destructive indentation/structure fixes.
    Returns (is_valid, error_message_if_any, final_code).
    """
    if not code or not code.strip():
        return True, None, code

    clean_code = code.strip()

    # 1. Attempt standard AST parsing
    try:
        ast.parse(clean_code)
        return True, None, clean_code
    except SyntaxError as e:
        first_error = str(e)
        logger.debug("Initial Python AST parse error: %s", first_error)

    # 2. Attempt common auto-fixes for LLM formatting artifacts
    # Auto-fix A: Strip hallucinated "Copy" or language labels on the first line
    lines = clean_code.split("\n")
    if lines and lines[0].strip().lower() in ("copy", "python", "py"):
        candidate = "\n".join(lines[1:]).strip()
        try:
            ast.parse(candidate)
            return True, None, candidate
        except SyntaxError:
            pass

    # Auto-fix B: Misaligned unindented 'else:' or 'elif' or 'except' or 'finally'
    # e.g., if clean_text == reversed_text:\n return True\nelse:\n return False (unindented else)
    fixed_lines = []
    current_indent = 0
    modified = False

    for line in lines:
        stripped = line.strip()
        # If line starts with else: or elif or except: or finally: but has 0 indent inside a block
        if re.match(r"^(else\s*:|elif\s+|except(\s+.*)?\s*:|finally\s*:)", stripped):
            # Check if previous lines had indentation
            prev_indents = [len(l) - len(l.lstrip()) for l in fixed_lines if l.strip()]
            if prev_indents and (len(line) - len(line.lstrip())) == 0:
                # Find matching indent level of preceding if/try
                target_indent = 4  # default standard indent
                for prev in reversed(fixed_lines):
                    if re.match(r"^\s*(if\s+|try\s*:)", prev):
                        target_indent = len(prev) - len(prev.lstrip())
                        break
                line = (" " * target_indent) + stripped
                modified = True
        fixed_lines.append(line)

    if modified:
        candidate = "\n".join(fixed_lines)
        try:
            ast.parse(candidate)
            return True, None, candidate
        except SyntaxError:
            pass

    # Auto-fix C: Dedent if the entire snippet was accidentally indented
    import textwrap
    dedented = textwrap.dedent(clean_code)
    if dedented != clean_code:
        try:
            ast.parse(dedented)
            return True, None, dedented
        except SyntaxError:
            pass

    return False, first_error, clean_code


def validate_json_syntax(code: str) -> Tuple[bool, Optional[str], str]:
    """Validate JSON code snippet."""
    if not code or not code.strip():
        return True, None, code
    try:
        json.loads(code.strip())
        return True, None, code.strip()
    except Exception as e:
        return False, str(e), code


def sanitize_code_block_content(lang: str, code: str) -> Tuple[str, bool, Optional[str]]:
    """
    Sanitizes and validates a code block based strictly on its language identifier.
    Does NOT apply Python-specific rules to other languages.
    """
    lang_lower = (lang or "").lower().strip()

    # Clean hallucinated copy buttons inside code fences
    cleaned_code = re.sub(r"^(?:copy|python|javascript|bash|sh|sql)\s*\n", "", code, flags=re.IGNORECASE)

    if lang_lower in ("python", "py"):
        is_valid, err, validated_code = validate_python_syntax(cleaned_code)
        return validated_code, is_valid, err

    elif lang_lower == "json":
        is_valid, err, validated_code = validate_json_syntax(cleaned_code)
        return validated_code, is_valid, err

    # For other languages (javascript, typescript, bash, sql, html, css), preserve as-is without Python parsing
    return cleaned_code, True, None


def sanitize_markdown_response(text: str, user_name: Optional[str] = None) -> str:
    """
    Post-processes and sanitizes chatbot Markdown output:
    1. Validates & corrects Python code blocks using AST parsing.
    2. Strips repetitive user name salutations in every paragraph.
    3. Eliminates formulaic robotic closing questions.
    4. Cleans literal <br> tags in markdown tables.
    """
    if not text:
        return ""

    # 1. Process fenced code blocks
    code_block_regex = re.compile(r"```(\w+)?\n([\s\S]*?)```")

    def replace_code_block(match: re.Match) -> str:
        lang = match.group(1) or ""
        raw_code = match.group(2)
        sanitized_code, is_valid, _ = sanitize_code_block_content(lang, raw_code)
        return f"```{lang}\n{sanitized_code}\n```"

    result = code_block_regex.sub(replace_code_block, text)

    # 2. Clean literal <br> or <br/> tags in markdown table rows (preserving normal line breaks)
    lines = result.split("\n")
    cleaned_lines = []
    for line in lines:
        if line.strip().startswith("|") and line.strip().endswith("|"):
            # Replace <br> inside table cells with a space or clean separator
            clean_cell_line = re.sub(r"<br\s*/?>", " ", line, flags=re.IGNORECASE)
            cleaned_lines.append(clean_cell_line)
        else:
            cleaned_lines.append(line)
    result = "\n".join(cleaned_lines)

    # 3. Strip repetitive user name mentions (e.g. "Pradeep ji, " appearing at start of multiple paragraphs)
    if user_name:
        name_pat = rf"\b{re.escape(user_name)}\s*(?:ji|bhaiya|sir)?\s*[,:;-]?\s*"
        paragraphs = result.split("\n\n")
        if len(paragraphs) > 1:
            sanitized_paragraphs = []
            for i, p in enumerate(paragraphs):
                if i > 0:
                    # Strip leading greeting name from subsequent paragraphs
                    p = re.sub(rf"^{name_pat}", "", p.strip(), flags=re.IGNORECASE)
                sanitized_paragraphs.append(p)
            result = "\n\n".join(sanitized_paragraphs)

    # 4. Eliminate robotic formulaic closing questions at the end of responses
    # e.g., "Pradeep ji, kya aapko ... Mujhe batayein!" or "Mujhe batayein!"
    closing_patterns = [
        r"\n*(?:(?:\w+)\s*(?:ji)?,\s*)?kya\s+aap(?:ko)?\s+[^.?!]+?(?:chahiye|samajhna\s+hai|janna\s+chahte\s+hain)\s*\??\s*Mujhe\s+batayein!?\s*$",
        r"\n*Mujhe\s+batayein!?\s*$",
        r"\n*Bataiye,\s*[^.?!]+?\?\s*$",
    ]
    for pat in closing_patterns:
        result = re.sub(pat, "", result, flags=re.IGNORECASE).strip()

    return result
