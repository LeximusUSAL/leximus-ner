#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
buscar_entidades_leximus.py
===========================
SoloLexiMus — Extractor de personas musicales históricas usando el CSV LexiMus.

Lee directamente entidades_ner_leximus.csv (sin spaCy ni modelo entrenado).
Búsqueda por expresiones regulares con soporte de:
  - Formas canónicas y alias (columna mismo_que)
  - Entidades Radio que requieren "orquesta" en el contexto próximo
  - Matching insensible a mayúsculas

Ventaja: cualquier cambio en el CSV se aplica sin regenerar ningún modelo.

USO:
    python3 buscar_entidades_leximus.py

    El script pedirá la ruta a la carpeta con los archivos .txt del corpus.
    Genera tres archivos de salida en esa misma carpeta:
      - resultados_leximus.json   → datos completos para análisis
      - resultados_leximus.txt    → listado legible por humanos
      - resultados_leximus.html   → interfaz web de revisión interactiva

REQUISITOS:
    Python 3.7+  — sin dependencias externas.

PROYECTO:
    LexiMus: Léxico y ontología de la música en español
    PID2022-139589NB-C33 (USAL / UCM / UR)
    https://github.com/LeximusUSAL/leximus-ner
"""

import os
import sys
import json
import re
import csv
import glob
from collections import defaultdict, Counter
from datetime import datetime
import html

# ─── RUTA AL CSV (mismo directorio que este script) ───────────────────────────
CSV_LEXIMUS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "entidades_ner_leximus.csv")


# ─── CARGA Y COMPILACIÓN DEL CSV ──────────────────────────────────────────────

def cargar_patrones(csv_path):
    """
    Lee el CSV y devuelve una lista de patrones compilados, ordenados de mayor
    a menor longitud para evitar coincidencias parciales.

    Cada patrón: {
        'regex':     compiled regex,
        'surface':   texto buscado,
        'canonical': nombre canónico (mismo_que si existe, si no variante_limpia),
        'etiqueta':  COMPOSITOR | INTERPRETE | CANTANTE | AGRUPACION | ...,
        'radio':     True si requiere "orquesta" cerca (notas: "requiere contexto Orquesta")
    }
    """
    filas = []
    try:
        with open(csv_path, encoding='utf-8') as f:
            filas = list(csv.DictReader(f))
    except FileNotFoundError:
        print(f"ERROR: No se encontró el CSV LexiMus en: {csv_path}")
        print("Asegúrate de que 'entidades_ner_leximus.csv' está en la misma carpeta que este script.")
        sys.exit(1)

    patrones = []
    seen = set()

    for row in filas:
        canonical = row.get('mismo_que', '').strip() or row['variante_limpia'].strip()
        etiqueta  = row['etiqueta'].strip()
        requiere_orquesta = 'requiere contexto Orquesta' in row.get('notas', '')

        for surface in dict.fromkeys([row['texto'].strip(), row['variante_limpia'].strip()]):
            if not surface or surface.lower() in seen:
                continue
            seen.add(surface.lower())

            # Word-boundary robusta para nombres con guión y acentos
            escaped = re.escape(surface)
            regex = re.compile(r'(?<!\w)' + escaped + r'(?!\w)', re.IGNORECASE)

            patrones.append({
                'regex':    regex,
                'surface':  surface,
                'canonical': canonical,
                'etiqueta': etiqueta,
                'radio':    requiere_orquesta,
            })

    # Más largo primero → evita que "Schubert" tape "Franz Schubert"
    patrones.sort(key=lambda p: -len(p['surface']))
    print(f"  CSV cargado: {len(filas)} entidades → {len(patrones)} patrones de búsqueda")
    return patrones


# ─── AUXILIARES ───────────────────────────────────────────────────────────────

def limpiar_ruta(ruta_raw):
    ruta = ruta_raw.strip().strip("'\"").replace("\\ ", " ").strip()
    ruta = os.path.expanduser(ruta)
    ruta = os.path.expandvars(ruta)
    return os.path.normpath(ruta)


def normalizar_fecha(nombre_archivo):
    base = os.path.basename(nombre_archivo)
    m = re.search(r'(\d{4})[_\-](\d{2})[_\-](\d{2})', base)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else base


def obtener_contexto(texto, inicio, fin, ventana=120):
    ctx_inicio = max(0, inicio - ventana)
    ctx_fin    = min(len(texto), fin + ventana)
    contexto   = texto[ctx_inicio:ctx_fin]
    offset     = inicio - ctx_inicio
    return contexto, offset, offset + (fin - inicio)


# ─── PROCESADO DEL CORPUS ─────────────────────────────────────────────────────

def procesar_corpus(carpeta, patrones):
    archivos = sorted(
        glob.glob(os.path.join(carpeta, "*.txt")) +
        glob.glob(os.path.join(carpeta, "**/*.txt"), recursive=True)
    )
    if not archivos:
        print(f"ERROR: No se encontraron archivos .txt en: {carpeta}")
        sys.exit(1)

    print(f"\n  {len(archivos)} archivos encontrados.")
    print("  Buscando entidades LexiMus...\n")

    entidades = defaultdict(lambda: {
        "menciones": [],
        "archivos":  set()
    })

    total = len(archivos)
    for i, ruta in enumerate(archivos, 1):
        fecha = normalizar_fecha(ruta)
        print(f"  [{i:03d}/{total}] {os.path.basename(ruta)}", end='\r', flush=True)

        try:
            with open(ruta, encoding='utf-8', errors='replace') as f:
                texto = f.read()
        except Exception as e:
            print(f"\n  AVISO: No se pudo leer {ruta}: {e}")
            continue

        # Búsqueda por regex sobre el texto completo del archivo
        # Usamos spans ya ocupados para no solapar coincidencias
        spans_ocupados = []

        for pat in patrones:
            for m in pat['regex'].finditer(texto):
                start, end = m.start(), m.end()

                # Descartar solapamiento con match anterior
                if any(s < end and start < e for s, e in spans_ocupados):
                    continue

                # Entidades Radio: exigir "orquesta" en los 60 caracteres previos
                if pat['radio']:
                    ventana_pre = texto[max(0, start - 60):start].lower()
                    if 'orquesta' not in ventana_pre:
                        continue

                spans_ocupados.append((start, end))
                canonical  = pat['canonical']
                etiqueta   = pat['etiqueta']
                nombre_key = canonical.lower()
                contexto_txt, c_ini, c_fin = obtener_contexto(texto, start, end)

                entidades[nombre_key]["menciones"].append({
                    "nombre_original": m.group(),
                    "nombre_canonico": canonical,
                    "etiqueta":        etiqueta,
                    "archivo":         os.path.basename(ruta),
                    "fecha":           fecha,
                    "contexto":        contexto_txt,
                    "ent_inicio":      c_ini,
                    "ent_fin":         c_fin,
                })
                entidades[nombre_key]["archivos"].add(os.path.basename(ruta))
                entidades[nombre_key]["etiqueta"]  = etiqueta
                entidades[nombre_key]["canonical"] = canonical

    print(f"\n\n  Búsqueda completada. {len(entidades)} entidades únicas encontradas.")
    return entidades, archivos


# ─── CLASIFICACIÓN ────────────────────────────────────────────────────────────

def agrupar_por_etiqueta(entidades):
    grupos = defaultdict(dict)

    for nombre_key, datos in entidades.items():
        nombre_canonico = datos.get("canonical") or \
            Counter(m["nombre_original"] for m in datos["menciones"]).most_common(1)[0][0]
        etiqueta = datos.get("etiqueta", datos["menciones"][0]["etiqueta"])

        formas = Counter(m["nombre_original"] for m in datos["menciones"])
        variantes = sorted(
            {f for f in formas if f.lower() != nombre_canonico.lower()},
            key=lambda f: -formas[f]
        )

        entrada = {
            "nombre":          nombre_canonico,
            "nombre_key":      nombre_key,
            "variantes":       variantes,
            "etiqueta":        etiqueta,
            "menciones":       len(datos["menciones"]),
            "archivos":        len(datos["archivos"]),
            "lista_menciones": datos["menciones"]
        }
        grupos[etiqueta][nombre_key] = entrada

    return grupos


# ─── SALIDA TXT ───────────────────────────────────────────────────────────────

def guardar_lista_txt(grupos, carpeta_salida):
    ruta = os.path.join(carpeta_salida, "resultados_leximus.txt")

    def fila(datos):
        lineas = [f"  • {datos['nombre']}"]
        if datos.get('variantes'):
            lineas.append(f"    También detectado como: {', '.join(datos['variantes'])}")
        lineas.append(f"    Menciones: {datos['menciones']} | Archivos: {datos['archivos']}")
        return "\n".join(lineas) + "\n"

    with open(ruta, 'w', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write("LexiMus — ENTIDADES MUSICALES DETECTADAS\n")
        f.write(f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write("=" * 70 + "\n\n")

        for etiqueta, cat_dict in sorted(grupos.items()):
            f.write(f"{etiqueta} ({len(cat_dict)})\n" + "-" * 40 + "\n")
            for d in sorted(cat_dict.values(), key=lambda x: -x['menciones']):
                f.write(fila(d))
            f.write("\n")

    print(f"  [OK] Lista TXT: {ruta}")
    return ruta


# ─── SALIDA JSON ──────────────────────────────────────────────────────────────

def guardar_json(grupos, carpeta_salida):
    datos = {
        "generado":  datetime.now().isoformat(),
        "herramienta": "LexiMus NER — buscar_entidades_leximus.py",
        "proyecto":  "PID2022-139589NB-C33 (USAL/UCM/UR)",
        "repositorio": "https://github.com/LeximusUSAL/leximus-ner",
        "entidades": {etiqueta: list(cat_dict.values()) for etiqueta, cat_dict in grupos.items()},
    }
    ruta = os.path.join(carpeta_salida, "resultados_leximus.json")
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(datos, f, ensure_ascii=False, indent=2, default=list)
    print(f"  [OK] JSON: {ruta}")
    return ruta


# ─── WEB REVISIÓN ─────────────────────────────────────────────────────────────

COLORES = {
    "COMPOSITOR": "#e74c3c",
    "INTERPRETE":  "#2980b9",
    "CANTANTE":    "#27ae60",
    "AGRUPACION":  "#8e44ad",
    "DIRECTOR":    "#d35400",
    "OBRA":        "#16a085",
}

def generar_web_revision(grupos, carpeta_salida, total_archivos):

    def cards_categoria(cat_dict, etiqueta):
        color = COLORES.get(etiqueta, "#555")
        cards = []
        for datos in sorted(cat_dict.values(), key=lambda x: -x['menciones']):
            nombre_esc     = html.escape(datos['nombre'])
            nombre_key_esc = html.escape(datos['nombre_key'])
            menciones_html = []
            for m in datos['lista_menciones'][:5]:
                ctx      = html.escape(m['contexto'])
                ent_text = html.escape(m['nombre_original'])
                ctx_marc = ctx.replace(ent_text, f'<mark>{ent_text}</mark>', 1)
                menciones_html.append(
                    f'<div class="ctx-item">'
                    f'<span class="ctx-meta">{html.escape(m["fecha"])} · {html.escape(m["archivo"])}</span>'
                    f'<p class="ctx-text">…{ctx_marc}…</p>'
                    f'</div>'
                )
            if len(datos['lista_menciones']) > 5:
                menciones_html.append(
                    f'<p class="ctx-more">+ {len(datos["lista_menciones"]) - 5} menciones más</p>'
                )
            variantes_html = ""
            if datos.get("variantes"):
                vars_esc = ", ".join(html.escape(v) for v in datos["variantes"])
                variantes_html = f'<span class="variantes">También: {vars_esc}</span>'

            cards.append(f"""
            <div class="card" data-nombre="{nombre_esc}" data-cat="{html.escape(etiqueta.lower())}" data-key="{nombre_key_esc}">
              <div class="card-header" style="border-left: 4px solid {color}">
                <div class="card-title">
                  <span class="nombre">{nombre_esc}</span>
                  {variantes_html}
                  <span class="menciones">{datos['menciones']} menciones · {datos['archivos']} archivos</span>
                </div>
                <div class="card-actions">
                  <button class="btn-ok" onclick="marcar(this,'ok')">✓ Correcto</button>
                  <button class="btn-fp" onclick="marcar(this,'fp')">✗ Falso positivo</button>
                  <button class="btn-toggle" onclick="toggleCtx(this)">▼ Contexto</button>
                </div>
              </div>
              <div class="card-body" style="display:none">{''.join(menciones_html)}</div>
            </div>""")
        return "\n".join(cards)

    total_entidades = sum(len(v) for v in grupos.values())
    tabs_html = ""
    contents_html = ""
    for i, (etiqueta, cat_dict) in enumerate(sorted(grupos.items())):
        color = COLORES.get(etiqueta, "#555")
        active = " active" if i == 0 else ""
        tabs_html += f'<div class="tab{active}" onclick="cambiarTab(\'{html.escape(etiqueta.lower())}\')" style="color:{color}">{html.escape(etiqueta)} ({len(cat_dict)})</div>\n'
        contents_html += f"""
<div class="tab-content{active}" id="tab-{html.escape(etiqueta.lower())}">
  <div class="section-title" style="color:{color}">{html.escape(etiqueta)} — {len(cat_dict)} entidades</div>
  {cards_categoria(cat_dict, etiqueta)}
</div>"""

    html_out = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LexiMus NER — Resultados</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', sans-serif; background: #f4f6f9; color: #222; }}
    header {{
      background: linear-gradient(135deg, #1a1a2e, #16213e);
      color: #fff; padding: 20px 30px;
    }}
    header h1 {{ font-size: 1.4rem; }}
    header .sub {{ font-size: 0.82rem; opacity: 0.65; margin-top: 4px; }}
    .notice {{
      background: #eafaf1; border-left: 5px solid #27ae60;
      padding: 12px 30px; font-size: 0.88rem; color: #1e5e34; font-weight: 600;
    }}
    .toolbar {{
      background: #fff; border-bottom: 1px solid #ddd;
      padding: 12px 30px; display: flex; gap: 12px; align-items: center;
      flex-wrap: wrap; position: sticky; top: 0; z-index: 100;
    }}
    .toolbar input, .toolbar select {{
      border: 1px solid #ccc; border-radius: 6px; padding: 7px 12px;
      font-size: 0.9rem; background: #fff;
    }}
    .toolbar input {{ width: 240px; }}
    .toolbar button {{
      border: none; border-radius: 6px; padding: 7px 14px;
      font-size: 0.85rem; cursor: pointer;
    }}
    .btn-export {{ background: #2ecc71; color: #fff; font-weight: bold; }}
    .btn-clear  {{ background: #e74c3c; color: #fff; }}
    .progress-bar  {{ width: 100%; height: 6px; background: #eee; border-radius: 3px; margin-top: 4px; }}
    .progress-fill {{ height: 100%; background: #2ecc71; border-radius: 3px; transition: width .3s; }}
    .progress-label {{ font-size: 0.8rem; color: #666; }}
    .stats-bar {{
      display: flex; gap: 16px; flex-wrap: wrap; padding: 12px 30px;
      background: #fff; border-bottom: 1px solid #eee; font-size: 0.85rem;
    }}
    .stat-item {{ text-align: center; }}
    .stat-num {{ font-size: 1.2rem; font-weight: 700; }}
    .tabs {{
      display: flex; gap: 4px; padding: 16px 30px 0;
      border-bottom: 2px solid #ddd; background: #f4f6f9; flex-wrap: wrap;
    }}
    .tab {{
      padding: 8px 20px; border-radius: 8px 8px 0 0; cursor: pointer;
      font-weight: 600; font-size: 0.9rem; background: #e0e0e0;
      border: 1px solid #ccc; border-bottom: none;
    }}
    .tab.active {{ background: #fff; }}
    .tab-content {{ display: none; padding: 20px 30px; }}
    .tab-content.active {{ display: block; }}
    .section-title {{
      font-size: 1.1rem; font-weight: 700; margin-bottom: 16px;
      padding-bottom: 8px; border-bottom: 2px solid #eee;
    }}
    .card {{
      background: #fff; border-radius: 8px; margin-bottom: 10px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    }}
    .card.marcado-ok {{ background: #f0fff4; }}
    .card.marcado-fp {{ background: #fff5f5; opacity: 0.7; }}
    .card-header {{
      padding: 12px 16px; display: flex; align-items: center;
      gap: 12px; flex-wrap: wrap;
    }}
    .card-title {{ flex: 1; min-width: 150px; }}
    .nombre {{ font-weight: 700; font-size: 1rem; }}
    .variantes {{ display: block; font-size: 0.75rem; color: #7c6a00; background: #fffbe6;
                  border: 1px solid #f0c040; border-radius: 4px; padding: 1px 7px;
                  margin-top: 3px; width: fit-content; }}
    .menciones {{ display: block; font-size: 0.78rem; color: #888; margin-top: 2px; }}
    .card-actions {{ display: flex; gap: 6px; flex-wrap: wrap; }}
    .card-actions button {{
      border: none; border-radius: 5px; padding: 5px 11px;
      font-size: 0.8rem; cursor: pointer;
    }}
    .btn-ok {{ background: #d5f5e3; color: #1e8449; }}
    .btn-ok:hover {{ background: #abebc6; }}
    .btn-fp {{ background: #fadbd8; color: #c0392b; }}
    .btn-fp:hover {{ background: #f1948a; }}
    .btn-toggle {{ background: #f2f3f4; color: #555; }}
    .card-body {{ padding: 12px 16px; border-top: 1px solid #f0f0f0; }}
    .ctx-item {{
      margin-bottom: 10px; padding: 8px 12px; background: #fafafa;
      border-radius: 6px; border-left: 3px solid #ccc;
    }}
    .ctx-meta  {{ font-size: 0.75rem; color: #888; display: block; margin-bottom: 4px; }}
    .ctx-text  {{ font-size: 0.85rem; line-height: 1.5; }}
    .ctx-text mark {{ background: #fff3cd; padding: 0 2px; border-radius: 2px; }}
    .ctx-more  {{ font-size: 0.8rem; color: #888; font-style: italic; margin-top: 8px; }}
    .toast {{
      position: fixed; bottom: 24px; right: 24px; background: #2c3e50;
      color: #fff; padding: 12px 20px; border-radius: 8px; font-size: 0.85rem;
      opacity: 0; transition: opacity .3s; pointer-events: none; z-index: 9999;
    }}
    .toast.show {{ opacity: 1; }}
  </style>
</head>
<body>

<header>
  <h1>LexiMus NER — Entidades musicales detectadas</h1>
  <div class="sub">Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')} · {total_archivos} archivos analizados · Proyecto LexiMus (PID2022-139589NB-C33)</div>
</header>

<div class="notice">
  ✓ Búsqueda basada exclusivamente en el listado LexiMus (entidades_ner_leximus.csv).
  Si falta alguna persona, añádela al CSV y vuelve a ejecutar el script.
</div>

<div class="stats-bar">
  <div class="stat-item"><div class="stat-num" style="color:#555">{total_entidades}</div><div>Entidades únicas</div></div>
  <div class="stat-item"><div class="stat-num" style="color:#888">{total_archivos}</div><div>Archivos corpus</div></div>
  <div class="stat-item"><div class="stat-num c-ok" id="cnt-ok">0</div><div>✓ Correctos</div></div>
  <div class="stat-item"><div class="stat-num c-fp" id="cnt-fp">0</div><div>✗ Falsos positivos</div></div>
  <div class="stat-item" style="flex:1; min-width:150px;">
    <div class="progress-label">Revisión: <span id="pct-rev">0%</span></div>
    <div class="progress-bar"><div class="progress-fill" id="prog-fill" style="width:0%"></div></div>
  </div>
</div>

<div class="toolbar">
  <input type="text" id="buscador" placeholder="🔍 Buscar nombre…" oninput="filtrar()">
  <select id="filtro-estado" onchange="filtrar()">
    <option value="todos">Todos los estados</option>
    <option value="pendiente">Sin revisar</option>
    <option value="ok">Correctos</option>
    <option value="fp">Falsos positivos</option>
  </select>
  <button class="btn-export" onclick="exportar()">⬇ Exportar revisión JSON</button>
  <button class="btn-clear"  onclick="limpiar()">↺ Limpiar revisión</button>
</div>

<div class="tabs">
{tabs_html}
</div>

{contents_html}

<div class="toast" id="toast"></div>

<script>
const TOTAL = {total_entidades};
let revisiones = {{}};

function cambiarTab(id) {{
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => {{
    if (t.getAttribute('onclick').includes("'" + id + "'")) t.classList.add('active');
  }});
  const content = document.getElementById('tab-' + id);
  if (content) content.classList.add('active');
}}

function marcar(btn, estado) {{
  const card = btn.closest('.card');
  const key  = card.dataset.key;
  card.classList.remove('marcado-ok','marcado-fp');
  if (estado === 'ok') card.classList.add('marcado-ok');
  if (estado === 'fp') card.classList.add('marcado-fp');
  revisiones[key] = estado;
  actualizarContadores();
}}

function toggleCtx(btn) {{
  const body = btn.closest('.card').querySelector('.card-body');
  if (!body) return;
  const visible = body.style.display !== 'none';
  body.style.display = visible ? 'none' : 'block';
  btn.textContent = visible ? '▼ Contexto' : '▲ Ocultar';
}}

function filtrar() {{
  const q      = document.getElementById('buscador').value.toLowerCase();
  const estado = document.getElementById('filtro-estado').value;
  document.querySelectorAll('.card').forEach(card => {{
    const nombre  = card.dataset.nombre.toLowerCase();
    const key     = card.dataset.key;
    const rev     = revisiones[key] || 'pendiente';
    const matchQ  = nombre.includes(q);
    const matchE  = estado === 'todos' || rev === estado;
    card.style.display = (matchQ && matchE) ? '' : 'none';
  }});
}}

function actualizarContadores() {{
  const ok = Object.values(revisiones).filter(v => v === 'ok').length;
  const fp = Object.values(revisiones).filter(v => v === 'fp').length;
  document.getElementById('cnt-ok').textContent = ok;
  document.getElementById('cnt-fp').textContent = fp;
  const pct = Math.round((ok + fp) / TOTAL * 100);
  document.getElementById('pct-rev').textContent = pct + '%';
  document.getElementById('prog-fill').style.width = pct + '%';
}}

function exportar() {{
  const blob = new Blob([JSON.stringify(revisiones, null, 2)], {{type: 'application/json'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'revision_leximus.json';
  a.click();
  toast('Revisión exportada como revision_leximus.json');
}}

function limpiar() {{
  if (!confirm('¿Borrar toda la revisión?')) return;
  revisiones = {{}};
  document.querySelectorAll('.card').forEach(c => c.classList.remove('marcado-ok','marcado-fp'));
  actualizarContadores();
}}

function toast(msg) {{
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}}
</script>
</body>
</html>"""

    ruta = os.path.join(carpeta_salida, "resultados_leximus.html")
    with open(ruta, 'w', encoding='utf-8') as f:
        f.write(html_out)
    print(f"  [OK] Web revisión: {ruta}")
    return ruta


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("LexiMus NER — Extractor de entidades musicales")
    print("Proyecto PID2022-139589NB-C33 (USAL/UCM/UR)")
    print("=" * 60)

    print(f"\nCargando entidades del CSV: {CSV_LEXIMUS}")
    patrones = cargar_patrones(CSV_LEXIMUS)

    print("\nIntroduce la ruta a la carpeta con los archivos .txt del corpus.")
    print("Ejemplo: /Users/maria/corpus/ondas_txt")
    carpeta_raw = input("\nRuta al corpus: ").strip()
    carpeta = limpiar_ruta(carpeta_raw)

    if not os.path.isdir(carpeta):
        print(f"ERROR: No existe la carpeta: {carpeta}")
        sys.exit(1)

    entidades, archivos = procesar_corpus(carpeta, patrones)
    grupos = agrupar_por_etiqueta(entidades)

    print(f"\nResultados por tipo de entidad:")
    for etiqueta, cat_dict in sorted(grupos.items()):
        print(f"  {etiqueta}: {len(cat_dict)} entidades únicas")

    print("\nGuardando resultados...")
    guardar_lista_txt(grupos, carpeta)
    guardar_json(grupos, carpeta)
    generar_web_revision(grupos, carpeta, len(archivos))

    print(f"\nListo. Archivos generados en: {carpeta}")
    print("  - resultados_leximus.txt   → listado de texto")
    print("  - resultados_leximus.json  → datos completos")
    print("  - resultados_leximus.html  → revisión interactiva (abrir en navegador)")


if __name__ == "__main__":
    main()
