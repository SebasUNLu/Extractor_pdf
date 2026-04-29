import fitz
import pandas as pd
import sys
import os
import time
import re
import io

def aplanar_y_limpiar_avanzado(ruta_entrada):
    """
    Limpia el PDF de estructuras fantasmas y normaliza el texto.
    """
    if not os.path.exists(ruta_entrada):
        print(f"Error: El archivo '{ruta_entrada}' no existe.")
        return None

    doc_original = fitz.open(ruta_entrada)
    doc_limpio = fitz.open()

    for i, pagina in enumerate(doc_original):
        rect = pagina.rect
        nueva_pag = doc_limpio.new_page(width=rect.width, height=rect.height)
        
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
    Realiza la extracción jerarquizada (Visto, Considerando, Tablas).
    """
    print(f"--- Fase 2: Iniciando Extracción: {nombre_original} ---")
    doc = fitz.open("pdf", buffer_pdf)
    contenido_final = []

    patron_alfabetico = re.compile(r'^[a-zA-Z]\.\s')
    patron_visto = re.compile(r'^(VISTO|Visto)[:\s]*')
    patron_considerando = re.compile(r'^(CONSIDERANDO|Considerando)[:\s]*')
    patron_resuelve = re.compile(r'^(R\s*E\s*S\s*U\s*E\s*L\s*V\s*E|D\s*I\s*S\s*P\s*O\s*N\s*E|D\s*E\s*C\s*R\s*E\s*T\s*A)[:\s]*', re.IGNORECASE)
    patron_articulo = re.compile(r'^(ART[IÍ]CULO|Art[ií]culo)\s*(\d+)([:\s\.]*)')
    patron_folio = re.compile(r'^\s*-\s*\d+\s*-\s*$')
    patron_anexo_inicio = re.compile(r'^\s*(ANEXO|Anexo)\b', re.IGNORECASE)
    patron_titulo_norma = re.compile(r'(DISPOSICIÓN|RESOLUCIÓN)\s+([A-Z\-]+):\s*(\d+)-(\d+)', re.IGNORECASE)
    
    titulo_encontrado = None
    
    for i, pagina in enumerate(doc):
        cp = pagina.cropbox
        alto = cp.height
        margen_superior = cp.y0 + (alto * 0.15)
        margen_inferior = cp.y0 + (alto * 0.96)

        tabs = pagina.find_tables(strategy="lines", snap_tolerance=4)
        areas_tablas = [t.bbox for t in tabs.tables]
        tablas_procesadas = []

        bloques = pagina.get_text("dict")["blocks"]
        bloques.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))

        indices_saltados = set()

        for idx, b in enumerate(bloques):
            if b["type"] != 0 or idx in indices_saltados: continue
            
            x0, y0, x1, y1 = b["bbox"]
            centro_y = (y0 + y1) / 2

            lineas_temp = []
            for linea in b["lines"]:
                txt_temp = " ".join([s["text"].strip() for s in linea["spans"] if s["text"].strip()])
                if txt_temp and "///" not in txt_temp and not patron_folio.match(txt_temp):
                    lineas_temp.append(txt_temp)
            texto_temp = " ".join(lineas_temp).strip()
            texto_temp = re.sub(r'\s{2,}', ' ', texto_temp).strip()
            
            if not texto_temp: continue
            
            es_anexo = bool(patron_anexo_inicio.match(texto_temp))

            if not (margen_superior <= centro_y <= margen_inferior) and not es_anexo:
                continue

            esta_en_tabla = False
            for idx_tab, area in enumerate(areas_tablas):
                rect_tabla = fitz.Rect(area)
                rect_bloque = fitz.Rect(x0, y0, x1, y1)
                
                if rect_tabla.intersects(rect_bloque):
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
                
                if b["lines"] and b["lines"][0]["spans"]:
                    span_uno = b["lines"][0]["spans"][0]
                    if (span_uno.get("flags", 0) & 28) or (span_uno.get("char_flags", 0) & 24):
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

                # --- LÓGICA DE UNIÓN DE ANEXOS ---
                if es_anexo:
                    titulo_anexo_completo = [texto_unido]
                    cursor_idx = idx + 1
                    y1_prev = y1
                    
                    while cursor_idx < len(bloques):
                        b_sig = bloques[cursor_idx]
                        if b_sig["type"] != 0: break
                        
                        x0s, y0s, x1s, y1s = b_sig["bbox"]
                        rect_sig = fitz.Rect(x0s, y0s, x1s, y1s)
                        
                        en_tabla_sig = any(fitz.Rect(a).intersects(rect_sig) for a in areas_tablas)
                        if en_tabla_sig: break
                            
                        texto_sig = " ".join([" ".join([s["text"].strip() for s in l["spans"] if s["text"].strip()]) for l in b_sig["lines"]]).strip()
                        texto_sig = re.sub(r'\s{2,}', ' ', texto_sig).strip()

                        if "///" in texto_sig or patron_folio.match(texto_sig) or not texto_sig:
                            indices_saltados.add(cursor_idx)
                            cursor_idx += 1
                            continue

                        brecha_vertical = y0s - y1_prev
                        if brecha_vertical > 70: 
                            break
                            
                        if ":" in texto_sig: 
                            break

                        if re.search(r'^(DIVISI[OÓ]N|ÁREA|CARGO|ASIGNATURA|ART[IÍ]CULO|DNI|APELLIDO|NOMBRE|INTRODUCCI[OÓ]N)\b', texto_sig, re.IGNORECASE): 
                            break

                        es_conector = bool(re.search(r'^(DE\s+LA|DEL|PARA|DE|EN|FUNDAMENTACI[OÓ]N|PLAN\s+DE)\b', texto_sig, re.IGNORECASE))
                        
                        letras = [c for c in texto_sig if c.isalpha()]
                        es_casi_mayuscula = (sum(1 for c in letras if c.isupper()) / len(letras) > 0.8) if letras else False

                        if es_conector or texto_sig.isupper() or es_casi_mayuscula:
                            titulo_anexo_completo.append(texto_sig)
                            indices_saltados.add(cursor_idx)
                            y1_prev = y1s
                            cursor_idx += 1
                        else:
                            break
                    
                    # --- NUEVA LÓGICA PARA INSERTAR EL GUION ("-") DE FORMA INTELIGENTE ---
                    texto_unido = "# " + titulo_anexo_completo[0]
                    guion_puesto = False
                    for parte in titulo_anexo_completo[1:]:
                        # Evita poner guion a conectores como "DE LA RESOLUCION"
                        if not guion_puesto and not re.search(r'^(DE\s+LA|DEL)\b', parte, re.IGNORECASE):
                            texto_unido += " - " + parte
                            guion_puesto = True
                        else:
                            texto_unido += " " + parte
                    # ----------------------------------------------------------------------
                    
                    contenido_final.append(texto_unido)
                    continue
                # ----------------------------------------
                
                if not es_anexo:
                    if patron_visto.match(texto_unido):
                        texto_unido = "## Visto\n" + patron_visto.sub("", texto_unido).strip()
                    elif patron_considerando.match(texto_unido):
                        texto_unido = "## Considerando\n" + patron_considerando.sub("", texto_unido).strip()
                    elif m_res := patron_resuelve.match(texto_unido):
                        encabezado = "## Parte dispositiva" if "DISPONE" in m_res.group(1).upper() else "## Parte resolutiva"
                        texto_unido = f"{encabezado}\n" + patron_resuelve.sub("", texto_unido).strip()
                    elif m := patron_articulo.match(texto_unido):
                        texto_unido = f"### Artículo {m.group(2)}\n" + patron_articulo.sub("", texto_unido).strip()
                    elif not texto_unido.startswith("#"): 
                        if any(texto_unido.startswith(c) for c in ['·', '●', '•']) or patron_alfabetico.match(texto_unido):
                            linea_lista = texto_unido
                            for c in ['·', '●', '•']: linea_lista = linea_lista.replace(c, '', 1).strip()
                            texto_unido = "- " + linea_lista
                
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