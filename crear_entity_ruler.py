import os
"""
Crea un EntityRuler spaCy con las entidades musicales de LexiMus.
Base: es_core_news_lg + reglas del CSV entidades_ner_leximus.csv

Uso:
    python3 crear_entity_ruler.py

Resultado:
    - Carpeta 'leximus_ner_model/' con el modelo listo para usar
    - Fichero 'demo_resultado.txt' con ejemplos de anotación

Cómo usar el modelo después:
    import spacy
    nlp = spacy.load("leximus_ner_model")
    doc = nlp("Actuó Isaac Albéniz junto a Fernández Arbós en el piano.")
    for ent in doc.ents:
        print(ent.text, ent.label_)
"""

import csv
import spacy
from spacy.language import Language

CSV_ENTRADA = "entidades_ner_leximus.csv"
MODELO_SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leximus_ner_model")

# Textos de prueba del corpus ONDAS para verificar resultados
TEXTOS_DEMO = [
    "La Orquesta Filarmónica de Madrid, bajo la dirección de Bartolomé Pérez Casas, interpretó obras de Manuel de Falla.",
    "Actuaron en el concierto Isaac Albéniz y Enrique Granados con piezas para piano.",
    "La bailarina Antonia Mercé «La Argentina» deslumbró al público con su actuación.",
    "Concha Piquer cantó las mejores coplas de la temporada en el Teatro de la Zarzuela.",
    "El director Bruno Walter presentó obras de Ludwig van Beethoven y Johannes Brahms.",
    "Raquel Meller interpretó canciones acompañada al piano por José Cubiles.",
    "Miguel Fleta actuó en el Real junto a la soprano Felisa Herrero.",
    "Joaquín Nin estrenó su obra con Wanda Landowska al clavicémbalo.",
    "La Orquesta Sinfónica de Madrid interpretó la Sinfonía en sol menor de Wolfgang Amadeus Mozart.",
    "Federico García Lorca colaboró con La Argentinita en la recopilación de canciones populares.",
]


def cargar_patrones(csv_path):
    """
    Lee el CSV y genera patrones para el EntityRuler.
    Cada entidad genera varios patrones:
      - Texto original
      - Variante limpia (sin apodos)
      - Apodo solo (si existe)
    """
    patrones = []
    vistos = set()

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for fila in reader:
            etiqueta = fila["etiqueta"]
            textos_patron = set()

            # Texto principal
            textos_patron.add(fila["texto"].strip())

            # Variante limpia
            if fila["variante_limpia"].strip():
                textos_patron.add(fila["variante_limpia"].strip())

            # Apodo extraído de notas
            notas = fila.get("notas", "")
            if "Apodo:" in notas:
                apodo = notas.split("Apodo:")[-1].split("|")[0].strip()
                if apodo:
                    textos_patron.add(apodo)

            for texto in textos_patron:
                if not texto or len(texto) < 2:
                    continue
                clave = (texto.lower(), etiqueta)
                if clave in vistos:
                    continue
                vistos.add(clave)
                patrones.append({"label": etiqueta, "pattern": texto})

    return patrones


def main():
    print("Cargando modelo base: es_core_news_lg...")
    nlp = spacy.load("es_core_news_lg")

    # Cargar patrones del CSV
    patrones = cargar_patrones(CSV_ENTRADA)
    print(f"Patrones cargados: {len(patrones)}")
    por_etiqueta = {}
    for p in patrones:
        por_etiqueta[p["label"]] = por_etiqueta.get(p["label"], 0) + 1
    for etiqueta, n in sorted(por_etiqueta.items()):
        print(f"  {etiqueta}: {n} patrones")

    # Añadir EntityRuler ANTES del NER existente
    # Así nuestras reglas tienen prioridad sobre el modelo base
    if "entity_ruler" in nlp.pipe_names:
        nlp.remove_pipe("entity_ruler")

    ruler = nlp.add_pipe("entity_ruler", before="ner", config={"overwrite_ents": True})
    ruler.add_patterns(patrones)

    # Guardar modelo
    nlp.to_disk(MODELO_SALIDA)
    print(f"\nModelo guardado en: {MODELO_SALIDA}/")

    # Demo: anotar textos de prueba
    print("\n" + "="*60)
    print("DEMO — Entidades detectadas en textos de prueba")
    print("="*60)

    lineas_demo = []
    for texto in TEXTOS_DEMO:
        doc = nlp(texto)
        entidades = [(e.text, e.label_) for e in doc.ents]
        linea = f"\nTEXTO: {texto}"
        linea += f"\nENTIDADES: {entidades}\n"
        print(linea)
        lineas_demo.append(linea)

    with open("demo_resultado.txt", "w", encoding="utf-8") as f:
        f.write("DEMO EntityRuler LexiMus — Corpus ONDAS (1925-1935)\n")
        f.write("="*60 + "\n")
        f.writelines(lineas_demo)

    print(f"Resultados guardados en: demo_resultado.txt")
    print("\nPara usar el modelo:")
    print('  import spacy')
    print(f'  nlp = spacy.load("{MODELO_SALIDA}")')
    print('  doc = nlp("tu texto aquí")')
    print('  for ent in doc.ents: print(ent.text, ent.label_)')


if __name__ == "__main__":
    main()
