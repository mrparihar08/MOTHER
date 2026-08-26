# wikipedia_utils.py
import wikipedia


def detect_language(text: str) -> str:
    text = text or ""

    for ch in text:
        if '\u0900' <= ch <= '\u097F':
            return "hi"

    return "en"


def set_language(text: str):
    lang = detect_language(text)
    wikipedia.set_lang(lang)
    return lang


def search(query: str):
    query = (query or "").strip()
    if not query:
        return {"error": "Query missing", "results": []}

    lang = set_language(query)

    try:
        results = wikipedia.search(query)
        return {
            "query": query,
            "language": lang,
            "results": results
        }
    except Exception as e:
        return {"error": str(e), "results": []}


def get_summary(title: str, sentences: int = 3):
    title = (title or "").strip()
    if not title:
        return {"error": "Title missing"}

    lang = set_language(title)

    try:
        summary = wikipedia.summary(title, sentences=sentences)
        page = wikipedia.page(title)

        return {
            "title": page.title,
            "summary": summary,
            "url": page.url,
            "language": lang
        }

    except wikipedia.exceptions.DisambiguationError as e:
        return {
            "error": "Disambiguation error",
            "options": e.options[:5],
            "language": lang
        }

    except wikipedia.exceptions.PageError:
        return {"error": "Page not found", "language": lang}

    except Exception as e:
        return {"error": str(e), "language": lang}


def get_page(title: str):
    title = (title or "").strip()
    if not title:
        return {"error": "Title missing"}

    lang = set_language(title)

    try:
        page = wikipedia.page(title)

        return {
            "title": page.title,
            "url": page.url,
            "content": page.content[:2000] if page.content else "",
            "language": lang
        }

    except wikipedia.exceptions.DisambiguationError as e:
        return {
            "error": "Disambiguation error",
            "options": e.options[:5],
            "language": lang
        }

    except wikipedia.exceptions.PageError:
        return {"error": "Page not found", "language": lang}

    except Exception as e:
        return {"error": str(e), "language": lang}


def get_complete(title: str):
    title = (title or "").strip()
    if not title:
        return {"error": "Title missing"}

    lang = set_language(title)

    try:
        page = wikipedia.page(title)
        summary = wikipedia.summary(title, sentences=2)

        return {
            "title": page.title,
            "summary": summary,
            "url": page.url,
            "images": page.images[:3] if page.images else [],
            "language": lang
        }

    except wikipedia.exceptions.DisambiguationError as e:
        return {
            "error": "Disambiguation error",
            "options": e.options[:5],
            "language": lang
        }

    except wikipedia.exceptions.PageError:
        return {"error": "Page not found", "language": lang}

    except Exception as e:
        return {"error": str(e), "language": lang}