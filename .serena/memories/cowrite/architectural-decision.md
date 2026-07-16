# LLM Co-Writing — Architectural Decision

Issue: https://github.com/Ron-RONZZ-org/lighterbird/issues/63
Date: 2026-06-30

## Prompt Architecture: Two Layers

### Layer 1: Protocol (hardcoded in engine.py)
- JSON format requirements
- "Return COMPLETE revised text for EVERY field"
- "Preserve ALL original fields"
- Field validation rules
- NEVER user-editable — breaking this breaks the feature

### Layer 2: Style (cowrite_style.md, user-editable)
- Tone guidance ("formal", "friendly", "terse")
- Writing conventions ("use Oxford comma", "avoid passive voice")
- Domain-specific rules ("for bug reports: include steps to reproduce")
- Optional — empty/missing file = no style guidance appended
- Auto-seeded on first run (mirrors system_prompt.md pattern)

### Merge at runtime
```python
def build_cowrite_messages(...):
    protocol = COWRITE_PROTOCOL  # hardcoded, never changes
    style = load_cowrite_style()  # from cowrite_style.md, or None
    system = protocol + ("\n\n" + style if style else "")
    ...
```

### Files
- `src/lighterbird/core/cowrite_style.py` — auto-seed, load/load_cowrite_style()
- `~/.config/lighterbird/cowrite_style.md` — user-editable style file
