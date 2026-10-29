"""Lógica de ubicación: el examen se detiene en el primer nivel que NO se pasa."""

LEVELS = ["A1", "A2", "B1", "B2"]
MIN_PER_PART = 60   # cada parte (lectura, escritura, habla) debe sacar al menos esto
MIN_AVERAGE = 70    # y el promedio de las tres partes al menos esto


def level_passed(reading: float, writing: float, speaking: float | None = None) -> bool:
    """speaking=None significa que la parte de habla aún no se evalúa: se promedian solo las demás."""
    scores = [s for s in (reading, writing, speaking) if s is not None]
    return all(s >= MIN_PER_PART for s in scores) and sum(scores) / len(scores) >= MIN_AVERAGE


def next_step(level: str, passed: bool) -> dict:
    """Qué hacer después de rendir `level`.

    - Pasó y hay más niveles  -> examen del siguiente nivel.
    - Pasó B2                 -> terminó todo el currículo.
    - No pasó                 -> queda en enseñanza de ESE nivel.
    """
    i = LEVELS.index(level)
    if not passed:
        return {"action": "teach", "level": level}
    if i + 1 < len(LEVELS):
        return {"action": "exam", "level": LEVELS[i + 1]}
    return {"action": "done", "level": level}
