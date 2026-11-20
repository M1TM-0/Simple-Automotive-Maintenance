def author_display_name(name: str | None) -> str | None:
    """DP-15: autor exibido como primeiro nome + inicial do último ("Ana Souza Lima" → "Ana L.")."""
    parts = (name or "").split()
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[-1][0].upper()}."
