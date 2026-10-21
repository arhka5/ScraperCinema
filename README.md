# ScraperCinema · Cartelera Perú

Reúne en una sola web los horarios de **Cinemark, Cinépolis, Cinestar, UVK y
Cinerama** (Perú): qué películas hay y a qué hora en cada cine, con enlace a la
compra en el sitio oficial.

```
GitHub Actions (4 veces al día)          Netlify (sitio estático)
┌──────────────────────────────┐         ┌───────────────────────────┐
│ scraper/ (Python)            │         │ web/ index.html + app.js  │
│  cinemark · cinepolis ·      │ publica │                           │
│  cinestar · uvk · cinerama   ├────────►│  lee cartelera.json desde │
│  → cartelera.json            │ rama    │  raw.githubusercontent    │
└──────────────────────────────┘ "data"  └───────────────────────────┘
```

Los datos **no** se publican en Netlify: viven en la rama `data` y la web los
descarga desde GitHub. Así, actualizar la cartelera no consume publicaciones del
plan gratis de Netlify (cada una cuesta 15 de sus 300 créditos mensuales), y
Netlify solo publica cuando cambia algo en `web/`.

## Fuentes

| Cadena | Cómo se obtiene | Particularidades |
|---|---|---|
| Cinemark | API que usa su web (`bff.cinemark-peru.com`) | Horas con sufijo `Z` que en realidad son **hora local** |
| Cinépolis | Endpoints de su página de cartelera | `TimeFilter` serializado en **UTC-6** (servidor en México), no UTC |
| Cinestar | `__data.json` de SvelteKit (formato *devalue*) | Fecha de calendario: la trasnoche se pasa al día anterior |
| UVK | HTML de cada película | Fechas `dd/mm` sin año: se deduce |
| Cinerama | JSON de su web + HTML de cada película | **Sin fecha**: se toma como hoy (o el día de estreno si es preventa) |
| Cineplanet | — | No incluido: bloquea el acceso automatizado (ver abajo) |

**Convención de fechas:** las funciones entre las 00:00 y las 04:59 son
"trasnoche" y cuentan para el día anterior, como las anuncian los cines.

Las películas se unen entre cadenas con una clave normalizada que ignora
etiquetas (`[RE ESTRENO]`, `(DOB)`, `RE:`…), tildes y variantes ("Pt1" =
"Parte 1", "Parte Tres" = "Parte 3"). Además tolera errores de tipeo
("Street Figther") si la duración coincide, pero nunca une partes distintas.

## Scraping responsable

- Se identifica con un User-Agent propio: `CarteleraPeruBot/1.0 (+repo)`.
- Respeta `robots.txt`: no se consultan rutas prohibidas, como las de Cinépolis
  `/_CARTELERA/` y `/cartelera/aspx/`.
- Espera al menos 1 s entre peticiones a un mismo sitio y reintenta con
  calma ante errores. Son unas 70 peticiones por corrida, 4 corridas al día.
- **No esquiva protecciones anti-bots.** Cineplanet bloquea los navegadores
  automatizados (firewall de Azure) y ofusca su código, así que no se incluye.
  Se agregaría solo con su autorización.
- Los afiches se enlazan desde los servidores de cada cadena; no se copian.

**Aviso:** los términos de uso de Cinemark prohíben reproducir el contenido de
su sitio sin autorización. Los horarios son datos de hecho y cada función
enlaza a la compra oficial, pero publicar esto de forma abierta o comercial
conlleva ese riesgo. Pensado para uso personal; ante un pedido de retiro, se
retira (ver `web/legal.html`).

## Uso local

```bash
python -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
pip install -r scraper/requirements.txt

python -m pytest -q scraper/tests              # pruebas con respuestas reales guardadas
python -m scraper --output out/cartelera.json  # scraping real (~2 min)
python -m scraper --only uvk --output out/uvk.json

# Probar la web con esos datos (en localhost la web lee /cartelera.json)
copy out\cartelera.json web\cartelera.json     # Linux/macOS: cp
python -m http.server 8000 --directory web
```

Si una cadena falla, `--previous` reutiliza sus datos de la corrida anterior y
la web avisa que están desactualizados.

## Despliegue

1. **GitHub Actions** (`.github/workflows/scrape.yml`) corre solo a las 06:00,
   10:00, 14:00 y 18:00 de Lima, y también con cada cambio en `scraper/` o a
   mano desde *Actions → Actualizar cartelera → Run workflow*. Antes de
   publicar ejecuta las pruebas.
2. **Netlify:** *Add new project → Import from Git → ScraperCinema*. No hace
   falta configurar nada: `netlify.toml` indica `publish = "web"`.

GitHub desactiva los workflows programados de repos públicos tras 60 días sin
actividad en el repo. Si pasa, basta con reactivarlo en *Actions*.

## Estructura

```
scraper/
  client.py      HTTP educado (User-Agent, pausas, reintentos)
  normalize.py   títulos, idiomas, ciudades, horas
  cinemark.py · cinepolis.py · cinestar.py · uvk.py · cinerama.py
  __main__.py    une todo, respaldo por cadena, escribe cartelera.json
  tests/         pruebas + fixtures con respuestas reales
web/             sitio estático (sin dependencias ni compilación)
```
