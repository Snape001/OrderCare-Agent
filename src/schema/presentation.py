"""Pure-text filtering shared by the API and lightweight Streamlit client."""

import re


class ThinkingFilter:
    """Buffer a response before release so split or orphan think tags cannot leak."""

    def __init__(self) -> None:
        self._parts: list[str] = []

    def feed(self, part: str) -> None:
        self._parts.append(part)

    def finish(self) -> str:
        text = "".join(self._parts)
        output: list[str] = []
        position = 0
        inside = False
        while position < len(text):
            opening = text.find("<think>", position)
            closing = text.find("</think>", position)
            if inside:
                if closing < 0:
                    break
                inside = False
                position = closing + len("</think>")
            elif closing >= 0 and (opening < 0 or closing < opening):
                # A model may omit the opening tag but still close its thinking.
                output.clear()
                position = closing + len("</think>")
            elif opening >= 0:
                output.append(text[position:opening])
                inside = True
                position = opening + len("<think>")
            else:
                output.append(text[position:])
                break
        return "".join(output).strip()


def public_answer(content: str) -> str | None:
    """Return a completed user-facing answer, rejecting raw tool transcripts."""
    filtered = ThinkingFilter()
    filtered.feed(content)
    answer = filtered.finish()
    if not answer or re.search(r"(?im)^\s*Tool Call\s*:", answer):
        return None
    return answer
