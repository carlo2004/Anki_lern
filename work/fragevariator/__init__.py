"""Variator – alternative formulations for existing Anki cards.

The guarded import keeps the pure-Python core importable in the test suite
without requiring Anki to be installed.
"""

try:
    import aqt  # type: ignore  # noqa: F401
except ImportError:
    pass
else:
    from .addon import register

    register()
