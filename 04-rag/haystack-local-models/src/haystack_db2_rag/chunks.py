"""Reading a stored chunk's own text.

Docling prepends the section headings to every chunk it stores, so the raw content
starts with them. Both metadata.py (previews) and search.py (excerpts) want the text
underneath, so it lives here once.
"""


def body(doc) -> str:
    """The chunk's text with Docling's prepended heading lines removed.

    `meta["headings"]` is the heading trail joined with " > ", so split it back apart
    and drop each heading that appears on a line of its own. Falls back to the raw
    content if that would leave nothing.
    """
    headings = doc.meta["headings"].split(" > ") if doc.meta["headings"] else []
    lines = [line for line in doc.content.splitlines() if line.strip() and line not in headings]
    return "\n".join(lines).strip() or doc.content.strip()
