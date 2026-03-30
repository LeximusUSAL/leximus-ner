# LexiMus NER — Extractor de entidades musicales

**Proyecto LexiMus: Léxico y ontología de la música en español**
PID2022-139589NB-C33 · Universidad de Salamanca / UCM / Universidad de La Rioja

---

Extractor de personas y agrupaciones musicales históricas en corpus español.
El CSV reúne **984 entidades únicas** (1.035 filas incluyendo alias y variantes ortográficas), curadas y revisadas manualmente a partir de la prensa histórica musical del corpus LexiMus USAL, así como de programas de conciertos de la Sociedad Filarmónica de Madrid y de la Asociación de Cultura Musical. El **script Python** busca todas esas entidades en cualquier carpeta de archivos `.txt` mediante expresiones regulares, sin dependencias externas.

→ **[Ver guía completa en la web](https://leximususal.github.io/leximus-ner)**

## Archivos

| Archivo | Descripción |
|---|---|
| `entidades_ner_leximus.csv` | 984 entidades únicas (1.035 filas con alias y variantes) |
| `buscar_entidades_leximus.py` | Script de búsqueda por regex (sin dependencias) |
| `crear_entity_ruler.py` | Crea un modelo EntityRuler de spaCy a partir del CSV |
| `index.html` | Web de presentación con guía de uso |

## Uso rápido

```bash
# 1. Clona el repositorio
git clone https://github.com/LeximusUSAL/leximus-ner.git
cd leximus-ner

# 2. Ejecuta el script
python3 buscar_entidades_leximus.py

# 3. Cuando lo pida, escribe la ruta a tu carpeta de archivos .txt
Ruta al corpus: /ruta/a/tu/corpus
```

El script genera tres archivos en la carpeta del corpus:
- `resultados_leximus.txt` — listado de texto legible
- `resultados_leximus.json` — datos completos con contextos
- `resultados_leximus.html` — interfaz web de revisión interactiva

## Requisitos

- Python 3.7 o superior
- Sin dependencias externas (solo biblioteca estándar)
- Archivos `.txt` en codificación UTF-8

Para usar `crear_entity_ruler.py` (opcional):
```bash
pip install spacy
python3 -m spacy download es_core_news_lg
```

## Categorías de entidades

| Etiqueta | Descripción | Entidades únicas |
|---|---|---|
| `COMPOSITOR` | Compositores de música clásica, zarzuela y popular | 293 |
| `INTERPRETE` | Instrumentistas, concertistas y directores de orquesta | 317 |
| `CANTANTE` | Voces líricas, populares, cupletistas | 286 |
| `AGRUPACION` | Orquestas, bandas, coros, cuartetos | 88 |
| **Total** | | **984** |

## Estructura del CSV

El CSV tiene 1.035 filas porque una misma persona puede aparecer en el corpus con grafías distintas (errores de OCR, apellido solo, apodos…). Cada variante ocupa su propia fila para que el script la detecte, y la columna `mismo_que` la vincula a la forma canónica. Las 51 filas extra son esos alias.

```
texto,etiqueta,variante_limpia,instrumento_rol,notas,mismo_que
Manuel de Falla,COMPOSITOR,Manuel de Falla,,,
Falla,COMPOSITOR,Manuel de Falla,,,mismo_que=Manuel de Falla
banda Creatone,AGRUPACION,banda Creatone,,,Banda Creatore
Orquesta Filarmónica de Madrid,AGRUPACION,Orquesta Filarmónica de Madrid,,,
```

## Cómo ampliar el CSV

Abre `entidades_ner_leximus.csv` con Excel o LibreOffice Calc y añade filas.
El script lee el CSV en cada ejecución, no hace falta regenerar ningún modelo.

## Citar

```
LexiMus-USAL (2026). LexiMus NER: Extractor de entidades musicales
para corpus histórico español [Software y datos]. GitHub.
https://github.com/LeximusUSAL/leximus-ner

Proyecto LexiMus: Léxico y ontología de la música en español (PID2022-139589NB-C33).
Universidad de Salamanca / UCM / Universidad de La Rioja.
```

## Licencia

[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) — libre para uso académico y comercial con atribución.
