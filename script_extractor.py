import fitz
import pandas as pd
import sys
import os
import time
import re
import io

def aplanar_y_limpiar_avanzado(ruta_entrada):
    """
    Limpia el PDF de estructuras fantasmas y normaliza el texto[cite: 5].
    """
    if not os.path.exists(ruta_entrada):
        print(f"Error: El archivo '{ruta_entrada}' no existe.")
        return None

    doc_original = fitz.open(ruta_entrada)
    doc_limpio = fitz.open()

    for i, pagina in enumerate(doc_original):
        rect = pagina.rect
        nueva_pag = doc_limpio.new_page(width=rect.width, height=rect.height)
        
        # Transferencia de Texto (Normalización)[cite: 5]
        diccionario_texto = pagina.get_text("dict")
        for bloque in diccionario_texto["blocks"]:
            if bloque["type"] == 0:
                for linea in bloque["lines"]:
                    for span in linea["spans"]:
                        nueva_pag.insert_text(
                            span["origin"], 
                            span["text"], 
                            fontsize=span["size"],
                            fontname="helv",
                            color=(0,0,0)
                        )
        
        # Eliminación de gráficos/tablas para evitar ruido en el texto[cite: 5]
        tabs = pagina.find_tables()
        for t in tabs.tables:
            nueva_pag.draw_rect(t.bbox, color=(1,1,1), fill=(1,1,1))

    buffer_pdf = io.BytesIO()
    doc_original.save(buffer_pdf, garbage=4, deflate=True, clean=True)
    doc_original.close()
    doc_limpio.close()
    buffer_pdf.seek(0)
    print(f"--- Fase 1: PDF Normalizado en Memoria ---")
    return buffer_pdf

def extraer_a_markdown_directo(buffer_pdf, nombre_original):
    """
    Realiza la extracción jerarquizada (Visto, Considerando, Tablas)[cite: 5].
    """
    print(f"--- Fase 2: Iniciando Extracción: {nombre_original} ---")
    doc = fitz.open("pdf", buffer_pdf)
    contenido_final = []

    # Patrones para jerarquización[cite: 5]
    patron_alfabetico = re.compile(r'^[a-zA-Z]\.\s')
    patron_visto = re.compile(r'^(VISTO|Visto)[:\s]*')
    patron_considerando = re.compile(r'^(CONSIDERANDO|Considerando)[:\s]*')
    patron_resuelve = re.compile(r'^(R\s*E\s*S\s*U\s*E\s*L\s*V\s*E|D\s*I\s*S\s*P\s*O\s*N\s*E|D\s*E\s*C\s*R\s*E\s*T\s*A)[:\s]*', re.IGNORECASE)
    patron_articulo = re.compile(r'^(ART[IÍ]CULO|Art[ií]culo)\s*(\d+)([:\s\.]*)')
    patron_folio = re.compile(r'^\s*-\s*\d+\s*-\s*$')
    patron_anexo = re.compile(r'^(ANEXO|Anexo)\s*(\d+|[IVXLCDM]+)?')
    patron_titulo_norma = re.compile(r'(DISPOSICIÓN|RESOLUCIÓN)\s+([A-Z\-]+):\s*(\d+)-(\d+)', re.IGNORECASE)
    
    titulo_encontrado = None
    
    for i, pagina in enumerate(doc):
        # Configuración de márgenes[cite: 5]
        cp = pagina.cropbox
        alto = cp.height
        margen_superior = cp.y0 + (alto * 0.20)
        margen_inferior = cp.y0 + (alto * 0.96)

        # Detección de Tablas[cite: 5]
        tabs = pagina.find_tables(strategy="lines", snap_tolerance=4)
        areas_tablas = [t.bbox for t in tabs.tables]
        tablas_procesadas = []

        bloques = pagina.get_text("dict")["blocks"]
        bloques.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))

        for idx, b in enumerate(bloques):
            if b["type"] != 0: continue
            
            x0, y0, x1, y1 = b["bbox"]
            centro_y = (y0 + y1) / 2

            # Filtro de márgenes[cite: 5]
            if not (margen_superior <= centro_y <= margen_inferior):
                continue

            # Procesamiento de Tablas[cite: 5]
            esta_en_tabla = False
            for idx_tab, area in enumerate(areas_tablas):
                if x0 >= area[0]-3 and y0 >= area[1]-3 and x1 <= area[2]+3 and y1 <= area[3]+3:
                    if idx_tab not in tablas_procesadas:
                        df = tabs.tables[idx_tab].to_pandas().fillna("")
                        if not (df.empty or len(df.columns) < 2):
                            try:
                                contenido_final.append("\n" + df.to_markdown(index=False) + "\n")
                            except:
                                contenido_final.append("\n" + df.to_csv(sep="|", index=False) + "\n")
                        tablas_procesadas.append(idx_tab)
                    esta_en_tabla = True
                    break
            
            if not esta_en_tabla:
                lineas_bloque = []
                es_negrita = False
                
                # Detección simple de negrita en la primera línea[cite: 5]
                if b["lines"] and b["lines"][0]["spans"]:
                    span_uno = b["lines"][0]["spans"][0]
                    if (span_uno.get("flags", 0) & 16) or (span_uno.get("char_flags", 0) & 16):
                        es_negrita = True

                for linea in b["lines"]:
                    txt = " ".join([s["text"].strip() for s in linea["spans"] if s["text"].strip()])
                    if txt and "///" not in txt and not patron_folio.match(txt):
                        lineas_bloque.append(txt)
                
                if not lineas_bloque: continue

                texto_unido = " ".join(lineas_bloque).strip()
                texto_unido = re.sub(r'\s{2,}', ' ', texto_unido).strip()

                if not titulo_encontrado:
                    match = patron_titulo_norma.search(texto_unido)
                    if match:
                        titulo_encontrado = f"# {match.group(1).capitalize()} {match.group(2)} - {int(match.group(3))}/{match.group(4)}"
                        continue
                
                if patron_visto.match(texto_unido):
                    texto_unido = "## Visto\n" + patron_visto.sub("", texto_unido).strip()
                elif patron_considerando.match(texto_unido):
                    texto_unido = "## Considerando\n" + patron_considerando.sub("", texto_unido).strip()
                elif m_res := patron_resuelve.match(texto_unido):
                    encabezado = "## Parte dispositiva" if "DISPONE" in m_res.group(1).upper() else "## Parte resolutiva"
                    texto_unido = f"{encabezado}\n" + patron_resuelve.sub("", texto_unido).strip()
                elif m := patron_articulo.match(texto_unido):
                    texto_unido = f"### Artículo {m.group(2)}\n" + patron_articulo.sub("", texto_unido).strip()
                elif patron_anexo.match(texto_unido):
                    texto_unido = "# " + texto_unido
                
                
                # Formato de listas[cite: 5]
                if any(texto_unido.startswith(c) for c in ['·', '●', '•']) or patron_alfabetico.match(texto_unido):
                    linea_lista = texto_unido
                    for c in ['·', '●', '•']: linea_lista = linea_lista.replace(c, '', 1).strip()
                    contenido_final.append("- " + linea_lista)
                else:
                    contenido_final.append(texto_unido)

        contenido_final.append("\n")

    doc.close()
    if titulo_encontrado: contenido_final.insert(0, titulo_encontrado)

    nombre_salida = f"{os.path.splitext(nombre_original)[0]}_jerarquizado.md"
    with open(nombre_salida, "w", encoding="utf-8") as f:
        f.write("\n\n".join(contenido_final))
    return nombre_salida

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python script.py archivo.pdf")
    else:
        ruta_archivo = sys.argv[1]
        inicio = time.time()
        pdf_limpio = aplanar_y_limpiar_avanzado(ruta_archivo)
        if pdf_limpio:
            extraer_a_markdown_directo(pdf_limpio, os.path.basename(ruta_archivo))
            print(f"Proceso terminado en {time.time() - inicio:.2f} s.")