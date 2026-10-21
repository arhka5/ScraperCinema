import pytest

from scraper.normalize import (display_title, guess_city, language_from, movie_key,
                               parse_minutes, similar_keys, to_24h)


@pytest.mark.parametrize("a, b", [
    ("AVENGERS ENDGAME [RE ESTRENO]", "AVENGERS  ENDGAME (RE ESTRENO)"),
    ("Avengers: Endgame Bonus", "AVENGERS ENDGAME"),
    ("DUNA PARTE 3 (DOB) (R)", "Duna: Parte Tres"),
    ("Los Juegos del Hambre: Sinsajo Pt1 [2014]", "Los juegos del Hambre: Sinsajo parte 1 [2014]"),
    ("MADRE SINIESTRA [TEMPORADA SINIESTRA]", "Madre Siniestra"),
    ("CARS (20 años)", "Cars (20 Aniversario)"),
    ("RE: Cars", "CARS"),
    ("LA HORA DE LA DESAPARICIÓN (DOB)", "La hora de la desaparicion"),
    ("Resident Evil: Noche Cero", "RESIDENT EVIL NOCHE CERO"),
])
def test_misma_pelicula_misma_clave(a, b):
    assert movie_key(a) == movie_key(b)


def test_partes_distintas_no_se_unen():
    assert movie_key("Sinsajo Parte 1") != movie_key("Sinsajo Parte 2")
    assert not similar_keys("los-juegos-del-hambre-sinsajo-parte-1",
                            "los-juegos-del-hambre-sinsajo-parte-2")


def test_errores_de_tipeo():
    assert similar_keys("street-fighter", "street-figther")
    assert not similar_keys("clayface", "street-fighter")


@pytest.mark.parametrize("raw, expected", [
    ("EL CORAZÓN DE LA BESTIA", "El Corazón de la Bestia"),
    ("BTS WORLD TOUR", "BTS World Tour"),
    ("COYOTE VS ACME", "Coyote vs Acme"),
    ("ROCKY III", "Rocky III"),
    ("LAS MIL Y UNA NOCHES", "Las Mil y una Noches"),  # "Mil", no "MIL" (romano)
    ("CARS (20 años)", "Cars (20 años)"),
    ("Yo Narciso", "Yo Narciso"),
])
def test_display_title(raw, expected):
    assert display_title(raw) == expected


def test_idioma_hora_duracion_ciudad():
    assert language_from("DUNA (DOB)") == "Doblada"
    assert language_from("Subtitulada") == "Subtitulada"
    assert language_from("Akira") == ""
    assert to_24h("9:30PM") == "21:30"
    assert to_24h("12:05 AM") == "00:05"
    assert to_24h("12:15 PM") == "12:15"
    assert to_24h("15:00:00") == "15:00"
    assert parse_minutes("1 hrs 38 mins") == 98
    assert parse_minutes("95 min") == 95
    assert guess_city("SUR", "Av. los Héroes 240, San Juan de Miraflores") == "Lima"
    assert guess_city("UVK TUMBES", "Costamar Plaza") == "Tumbes"
    assert guess_city("X", "Calle sin pistas") == "Otras"
