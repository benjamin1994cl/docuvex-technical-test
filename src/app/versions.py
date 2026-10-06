"""Regla de versión vigente (sección 8 del enunciado)."""


def resolve_current(versions: list[dict]) -> tuple[int, bool]:
    """Devuelve (número de la versión vigente, hay_conflicto).

    Entre las versiones marcadas is_current se elige la de effective_date más
    reciente y, si empatan, la de número mayor. Si ninguna está marcada, se
    aplica el mismo orden sobre todas. Hay conflicto cuando más de una versión
    está marcada como vigente.
    """
    flagged = [v for v in versions if v["is_current"]]
    candidates = flagged or versions
    chosen = max(candidates, key=lambda v: (str(v["effective_date"]), v["version"]))
    return chosen["version"], len(flagged) > 1
