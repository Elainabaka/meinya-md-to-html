"""Meinya Mind Map: checks what your docs claim about your code.

Docs (README, AGENTS.md, CLAUDE.md, decision logs...) make claims about the
code: this file exists, that command runs, this flag is supported, decision
MD65 still holds. Mind Map extracts each checkable claim and verifies it
against the working tree and git history. The machine finds evidence; an AI
(if any) only explains and fixes.
"""

__version__ = "1.0.0"
