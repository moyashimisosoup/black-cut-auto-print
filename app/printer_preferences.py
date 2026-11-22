"""Choose a printer queue without silently changing printing authorization."""
from __future__ import annotations


def prefer_canon_queue(queues: list[str], previously_selected: str = "") -> str:
    """Retain an existing queue, else choose a unique Canon MF240/MF244 queue.

    Never choose 'Microsoft Print to PDF' or arbitrarily select between queues.
    This is ONLY a UI suggestion; it cannot arm printing.
    """
    if previously_selected and previously_selected in queues:
        return previously_selected
    canon = [s for s in queues if "canon" in s.casefold() and
             ("mf240" in s.casefold() or "mf244" in s.casefold())]
    return canon[0] if len(canon) == 1 else ""
