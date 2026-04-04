import re
from typing import Dict, List, Tuple, Optional

def normalize_text(text: Optional[str]) -> str:
        return (text or "").strip()

def extract_title(text: str, user_title: Optional[str] = None) -> str:
    """
    Title priority:
    1) user_title if provided
    2) first sentence from input text
    3) first non-empty line
    4) default title
    """
    if user_title and user_title.strip():
        return user_title.strip()[:120]

    text = normalize_text(text)
    if not text:
        return "Chat Data Report"

    # First sentence
    sentence_match = re.search(r"(.+?[\.\!\?])(\s|$)", text, flags=re.S)
    if sentence_match:
        return sentence_match.group(1).strip()[:120]

    # First line
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return first_line[:120] if first_line else "Chat Data Report"

def make_safe_filename(title: str, default: str = "chat_data") -> str:
    title = normalize_text(title)
    if not title:
        return default

    title = re.sub(r"[^\w\s\-]", "", title, flags=re.UNICODE)
    title = re.sub(r"\s+", "_", title).strip("_")
    return title[:60] if title else default

def is_bullet_line(line: str) -> bool:
    """
    Detects standard bullets or numbered lists (1. , 2) , etc)
    """
    return bool(re.match(r"^\s*([-*•]|\d+[.)])\s+", line or ""))

def split_cell_values(raw_value: str) -> List[str]:
    """
    Split on strong separators only.
    Example:
    "a, b, c" -> ["a", "b", "c"]
    "John Doe" -> ["John Doe"]
    """
    raw_value = normalize_text(raw_value)
    if not raw_value:
        return [""]

    parts = re.split(r"\s*[,;\n|]\s*", raw_value)
    parts = [p.strip() for p in parts if p.strip()]
    return parts if parts else [raw_value]

def split_text_into_chunks(text: str, max_chars: int = 350) -> List[str]:
    """
    Split long text into readable chunks by paragraph and sentence.
    """
    text = normalize_text(text)
    if not text:
        return []

    paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
    chunks: List[str] = []

    for para in paragraphs:
        if len(para) <= max_chars:
            chunks.append(para)
            continue

        sentences = re.split(r"(?<=[.!?])\s+", para)
        current = ""

        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue

            if not current:
                current = sent
                continue

            if len(current) + len(sent) + 1 <= max_chars:
                current = f"{current} {sent}"
            else:
                chunks.append(current.strip())
                current = sent

        if current.strip():
            chunks.append(current.strip())

    return chunks

def text_to_bullets(text: str) -> List[str]:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    bullets: List[str] = []

    for line in lines:
        if is_bullet_line(line):
            bullets.append(re.sub(r"^\s*[-*•]\s+", "", line).strip())
        else:
            bullets.append(line)

    return bullets

def safe_placeholder_text(slide, index: int, value: str) -> bool:
    try:
        if len(slide.placeholders) > index:
            slide.placeholders[index].text = value
            return True
    except Exception:
        pass
    return False

def _looks_like_key_value_text(text: str) -> bool:
    """
    Avoid false positives on ordinary sentences that contain a colon.
    We treat text as structured when there are 2+ key:value lines.
    """
    lines = [line.strip() for line in normalize_text(text).splitlines() if line.strip()]
    key_value_lines = 0

    for line in lines:
        if re.match(r"^[^:\n]{1,80}\s*:\s*.+$", line):
            key_value_lines += 1

    return key_value_lines >= 2

def get_table_header_and_rows(text: str) -> Tuple[List[str], List[List[str]]]:
    """
    Parse:
    - key:value structured text into table headers + rows
    - otherwise fallback to single-column content rows
    """
    text = normalize_text(text)
    if not text:
        return ["Content"], [[""]]

    if _looks_like_key_value_text(text):
        pattern = re.compile(
            r"([^\n:]+?)\s*:\s*(.*?)(?=(?:\n\s*[^\n:]+?\s*:)|\Z)",
            flags=re.S,
        )
        matches = list(pattern.finditer(text))

        if matches:
            data: Dict[str, List[str]] = {}
            max_len = 0

            for match in matches:
                key = match.group(1).strip()
                value = match.group(2).strip()
                values = split_cell_values(value)
                data[key] = values
                max_len = max(max_len, len(values))

            headers = list(data.keys())
            rows: List[List[str]] = []

            for i in range(max_len):
                row = []
                for key in headers:
                    values = data.get(key, [])
                    row.append(values[i] if i < len(values) else "")
                rows.append(row)

            return headers, rows

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ["Content"], [[""]]

    # One paragraph -> split into sentences for better readability
    if len(lines) == 1:
        parts = re.split(r"(?<=[.!?])\s+", lines[0])
        parts = [p.strip() for p in parts if p.strip()]
        if not parts:
            parts = [lines[0]]
        return ["Content"], [[p] for p in parts]

    return ["Content"], [[line] for line in lines]

def parse_structured_slides(text: str) -> List[Tuple[str, List[str]]]:
    """
    Advanced parser that looks for 'Slide X: Title' or 'X. Heading' patterns.
    Returns [(Slide Title, [Bullets])]
    """
    text = normalize_text(text)
    # Robust regex to find slide headers (Slide X, Numbered Headings, Markdown ###, or Bold **Titles**)
    # Catches: "Slide 1: Intro", "1. Background", "### Methodology", "**Conclusion**"
    slide_pattern = re.compile(r"(?m)^(?:Slide\s*\d+\s*[:\-]\s*|\d+[\.\)]\s*|#{1,3}\s*|\*{2})([^\n\*]+)(?:\*{2})?$", re.I)

    blocks = slide_pattern.split(text)
    # First block is usually noise or the main title
    headers = slide_pattern.findall(text)
    bodies = [b.strip() for b in blocks[1:]]

    slides = []
    for i in range(len(headers)):
        title = headers[i].strip()
        content = bodies[i] if i < len(bodies) else ""

        # Clean bullets from content
        bullets = [re.sub(r"^\s*[-*•\d\.\)]\s+", "", line).strip() 
                for line in content.splitlines() if line.strip()]

        # Limit bullets to 6 per slide for readability
        slides.append((title, bullets[:8])) # Increased limit slightly for research/academic decks

    return slides
