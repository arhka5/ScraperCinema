"""Normalización de títulos, idiomas y ciudades.

Cada cadena escribe los títulos a su manera ("AVENGERS ENDGAME [RE ESTRENO]",
"AVENGERS  ENDGAME (RE ESTRENO)", "DUNA PARTE 3 (DOB) (R)"). Para mostrar una
sola ficha por película se genera una clave que ignora esas variaciones.
"""
from __future__ import annotations

import re
import unicodedata

# Palabras que describen la función, no la película.
_NOISE = {
    "DOB", "DOBLADA", "DOBLADO", "SUB", "SUBTITULADA", "SUBTITULADO", "CAST",
    "2D", "3D", "4D", "XD", "IMAX", "4DX", "DBOX", "D-BOX", "PREMIUM", "PRIME",
    "PREVENTA", "ESTRENO", "REESTRENO", "RE-ESTRENO", "R", "BONUS",
}
_SMALL_WORDS = {
    "a", "al", "con", "de", "del", "el", "en", "la", "las", "lo", "los", "o",
    "para", "por", "un", "una", "y", "e", "of", "the", "and", "vs", "vs.",
}
# Solo I, V y X (secuelas: II, III, IV…): evita confundir "MIL" o "MIX".
_ROMAN = re.compile(r"^(?=[XVI])X{0,3}(IX|IV|V?I{0,3})$")


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def _remove_tags(title: str) -> str:
    """Quita lo que va entre () o [] cuando son etiquetas (DOB, RE ESTRENO…)."""
    def repl(match: re.Match) -> str:
        inner = strip_accents(match.group(1)).upper().replace("-", " ").split()
        return " " if all(w in _NOISE or w == "RE" for w in inner) else match.group(0)
    return re.sub(r"[\(\[]\s*([^\)\]]*)\s*[\)\]]", repl, title)


def clean_title(title: str) -> str:
    # Cinemark usa [] para anotaciones del ciclo o del año: "[TEMPORADA SINIESTRA]",
    # "[RE ESTRENO]", "[1988]". Nunca forman parte del título.
    title = re.sub(r"\[[^\]]*\]", " ", title)
    title = re.sub(r"^\s*RE\s*[:\-]\s*", "", title, flags=re.I)  # "RE: Cars" (reestreno)
    title = _remove_tags(title)
    # Etiquetas sueltas al final: "… - DOB", "… 3D"
    words = title.split()
    while words and strip_accents(words[-1]).upper().strip("-–") in _NOISE - {"R"}:
        words.pop()
    return re.sub(r"\s+", " ", " ".join(words)).strip(" -–")


_NUMBERS = {"UNO": "1", "UNA": "1", "DOS": "2", "TRES": "3", "CUATRO": "4", "CINCO": "5",
            "SEIS": "6", "SIETE": "7", "OCHO": "8", "NUEVE": "9", "DIEZ": "10",
            "ONE": "1", "TWO": "2", "THREE": "3", "FOUR": "4", "FIVE": "5",
            "I": "1", "II": "2", "III": "3", "IV": "4", "V": "5"}
_PART = r"(?:PARTE|PART|PT|CAPITULO|CHAPTER|CAP|VOLUMEN|VOL|EPISODIO)"


def movie_key(title: str) -> str:
    # Para la clave también se ignora lo que va entre paréntesis:
    # "CARS (20 años)" y "Cars (20 Aniversario)" son la misma película.
    text = re.sub(r"\([^)]*\)", " ", clean_title(title))
    text = strip_accents(text).upper().replace("&", " Y ")
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    # "Pt1", "Parte Tres", "Parte III" → "PARTE 1/3"
    text = re.sub(rf"\b{_PART}\s*(\d+)\b", r"PARTE \1", text)
    text = re.sub(rf"\b{_PART}\s+([A-Z]+)\b",
                  lambda m: f"PARTE {_NUMBERS.get(m.group(1), m.group(1))}", text)
    return "-".join(text.lower().split())


def display_title(title: str) -> str:
    """Pasa títulos en mayúsculas a formato de título en español."""
    title = clean_title(title)
    letters = [c for c in title if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) < 0.6:
        # Ya viene con mayúsculas y minúsculas; solo se corrigen palabras
        # sueltas en mayúsculas ("CARS (20 años)" → "Cars (20 años)").
        return " ".join(
            w[:1] + w[1:].lower() if len(w) > 3 and w.isupper() and re.search(r"[AEIOUÁÉÍÓÚ]", w)
            else w for w in title.split())
    words = []
    for i, word in enumerate(title.split()):
        lower = word.lower()
        bare = lower.strip(":,.!?¿¡\"'()[]<>")
        if len(bare) > 1 and _ROMAN.match(bare.upper()):
            words.append(word.upper())
        elif i > 0 and bare in _SMALL_WORDS and not words[-1].endswith(":"):
            words.append(lower)
        elif bare.isalpha() and len(bare) > 1 and not re.search(r"[aeiouyáéíóú]", bare):
            words.append(word.upper())  # siglas sin vocales: BTS, TXT
        else:
            j = next((k for k, c in enumerate(lower) if c.isalpha()), None)
            words.append(lower if j is None else lower[:j] + lower[j].upper() + lower[j + 1:])
    return " ".join(words)


def similar_keys(a: str, b: str) -> bool:
    """Tolera errores de tipeo ('street-figther') pero no cambios de número
    ('sinsajo-parte-1' frente a 'sinsajo-parte-2')."""
    from difflib import SequenceMatcher
    if re.findall(r"\d+", a) != re.findall(r"\d+", b):
        return False
    return SequenceMatcher(None, a, b).ratio() >= 0.9


def language_from(text: str) -> str:
    t = strip_accents(text or "").upper()
    if re.search(r"\b(SUB|SUBTITULAD[AO]|SUBT)\b", t):
        return "Subtitulada"
    if re.search(r"\b(DOB|DOBLAD[AO]|CAST|ESPANOL)\b", t):
        return "Doblada"
    return ""


# Ciudades y distritos para ubicar cines cuyas fichas no traen la ciudad.
_LIMA_HINTS = [
    "LIMA", "SAN JUAN DE MIRAFLORES", "SAN JUAN DE LURIGANCHO", "SJL", "LURIGANCHO",
    "CHOSICA", "COMAS", "CHORRILLOS", "EL AGUSTINO", "AGUSTINO", "INDEPENDENCIA",
    "LOS OLIVOS", "SAN MIGUEL", "SURCO", "SURQUILLO", "MIRAFLORES", "ATE", "SANTA ANITA",
    "VILLA EL SALVADOR", "VILLA MARIA DEL TRIUNFO", "PUENTE PIEDRA", "CARABAYLLO",
    "SAN MARTIN DE PORRES", "BRENA", "LINCE", "JESUS MARIA", "BARRANCO", "LA MOLINA",
    "SAN BORJA", "PUEBLO LIBRE", "RIMAC", "CALLAO", "BELLAVISTA", "VENTANILLA",
    "HUACHO", "CANETE", "UNI", "ARENALES", "PORTENO", "EXCELSIOR", "EXELSIOR",
]
_CITIES = [
    "AREQUIPA", "TRUJILLO", "CHICLAYO", "PIURA", "SULLANA", "TUMBES", "CHIMBOTE",
    "HUANCAYO", "HUANUCO", "TINGO MARIA", "TARAPOTO", "IQUITOS", "PUCALLPA", "CUSCO",
    "PUNO", "JULIACA", "TACNA", "MOQUEGUA", "ILO", "AYACUCHO", "ICA", "CHINCHA", "PISCO",
    "CAJAMARCA", "HUARAZ", "JAEN", "MOYOBAMBA", "ABANCAY", "ANDAHUAYLAS", "HUACHO",
    "BARRANCA", "TALARA", "PAITA", "CERRO DE PASCO", "HUANCAVELICA", "PUERTO MALDONADO",
]


def guess_city(*texts: str) -> str:
    t = " " + re.sub(r"[^A-Z0-9]+", " ", strip_accents(" ".join(texts)).upper()) + " "
    for city in _CITIES:
        if f" {city} " in t:
            return city.title().replace("De ", "de ")
    for hint in _LIMA_HINTS:
        if f" {hint} " in t:
            return "Lima"
    return "Otras"


def parse_minutes(text: str) -> int | None:
    """'1 hrs 38 mins' → 98; '98 min' → 98."""
    t = (text or "").lower()
    h = re.search(r"(\d+)\s*h", t)
    m = re.search(r"(\d+)\s*m", t)
    if not h and not m:
        return None
    return (int(h.group(1)) if h else 0) * 60 + (int(m.group(1)) if m else 0)


def to_24h(text: str) -> str | None:
    """'9:30PM' → '21:30'; '12:05 am' → '00:05'; '15:00:00' → '15:00'."""
    m = re.search(r"(\d{1,2}):(\d{2})(?::\d{2})?\s*([AaPp]\.?\s*[Mm]\.?)?", text or "")
    if not m:
        return None
    hour, minute = int(m.group(1)), m.group(2)
    suffix = (m.group(3) or "").lower().replace(".", "").replace(" ", "")
    if suffix == "pm" and hour != 12:
        hour += 12
    elif suffix == "am" and hour == 12:
        hour = 0
    if hour > 23:
        return None
    return f"{hour:02d}:{minute}"
