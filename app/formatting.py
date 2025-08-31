import shutil

def _term_width(default=100):
    try:
        return shutil.get_terminal_size().columns
    except Exception:
        return default

def _crop(s, width):
    if s is None:
        return ""
    s = str(s)
    return s if len(s) <= width else s[: max(0, width - 1)] + "…"

def print_table(rows, columns, max_width=120):
    if not rows:
        print("(no results)")
        return

    term_w = min(_term_width(), max_width)

    # Allocate naive widths
    col_widths = {c: max(len(c), 4) for c in columns}
    for r in rows[:200]:
        for c in columns:
            col_widths[c] = min(max(col_widths[c], len(str(r.get(c, "")))), max_width // 2)

    # Normalize to terminal width (simple greedy shrink)
    total = sum(col_widths.values()) + 3 * (len(columns) - 1)
    while total > term_w:
        # shrink the widest column > 8
        widest = max(columns, key=lambda c: col_widths[c])
        if col_widths[widest] <= 8:
            break
        col_widths[widest] -= 1
        total = sum(col_widths.values()) + 3 * (len(columns) - 1)

    # Header
    header = " | ".join(_crop(c, col_widths[c]).ljust(col_widths[c]) for c in columns)
    sep = "-+-".join("-" * col_widths[c] for c in columns)
    print(header)
    print(sep)
    # Rows
    for r in rows:
        line = " | ".join(_crop(r.get(c, ""), col_widths[c]).ljust(col_widths[c]) for c in columns)
        print(line)
