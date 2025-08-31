from rich.table import Table

def table_suggestions(title: str, items):
    t = Table(title=title, show_lines=False)
    if not items: return t
    # infer columns from keys in first dict
    for k in items[0].keys():
        t.add_column(k)
    for it in items:
        t.add_row(*[str(it[k]) for k in items[0].keys()])
    return t
