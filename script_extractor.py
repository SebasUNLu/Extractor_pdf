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
        margen_superior = cp.y0 + (alto * 0.20)
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
                textos_subtitulo = []
                textos_cuerpo = []
                leyendo_subtitulo = False
                
                primer_span = None
                for linea in b["lines"]:
                    for span in linea["spans"]:
                        txt_limpio = span["text"].strip()
                        if txt_limpio and "///" not in txt_limpio and not patron_folio.match(txt_limpio):
                            primer_span = span
                            break
                    if primer_span: break
                
                if primer_span:
                    flags = primer_span.get("flags", 0)
                    font = primer_span.get("font", "").lower()
                    if (flags & 16) != 0 or "bold" in font or "black" in font or "heavy" in font:
                        leyendo_subtitulo = True

                for linea in b["lines"]:
                    for span in linea["spans"]:
                        txt_raw = span["text"]
                        txt_strip = txt_raw.strip()
                        
                        if "///" in txt_strip or patron_folio.match(txt_strip):
                            continue
                            
                        if not txt_strip:
                            if leyendo_subtitulo: textos_subtitulo.append(txt_raw)
                            else: textos_cuerpo.append(txt_raw)
                            continue
                        
                        flags = span.get("flags", 0)
                        font = span.get("font", "").lower()
                        es_bold = (flags & 16) != 0 or "bold" in font or "black" in font or "heavy" in font
                        
                        if leyendo_subtitulo:
                            if es_bold:
                                textos_subtitulo.append(txt_raw)
                            else:
                                leyendo_subtitulo = False
                                textos_cuerpo.append(txt_raw)
                        else:
                            textos_cuerpo.append(txt_raw)

                texto_sub = "".join(textos_subtitulo).strip()
                texto_cuerpo = "".join(textos_cuerpo).strip()
                texto_sub = re.sub(r'\s{2,}', ' ', texto_sub).strip()
                texto_cuerpo = re.sub(r'\s{2,}', ' ', texto_cuerpo).strip()
                
                texto_unido_plano = " ".join([texto_sub, texto_cuerpo]).strip()
                texto_unido_plano = re.sub(r'\s{2,}', ' ', texto_unido_plano).strip()

                if not titulo_encontrado:
                    match = patron_titulo_norma.search(texto_unido_plano)
                    if match:
                        titulo_encontrado = f"# {match.group(1).capitalize()} {match.group(2)} - {int(match.group(3))}/{match.group(4)}"
                        continue

                # --- LÓGICA DE UNIÓN DE ANEXOS ---
                if es_anexo:
                    titulo_anexo_completo = [texto_unido_plano]
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
                    
                    texto_unido = "# " + titulo_anexo_completo[0]
                    guion_puesto = False
                    for parte in titulo_anexo_completo[1:]:
                        if not guion_puesto and not re.search(r'^(DE\s+LA|DEL)\b', parte, re.IGNORECASE):
                            texto_unido += " - " + parte
                            guion_puesto = True
                        else:
                            texto_unido += " " + parte
                    
                    contenido_final.append(texto_unido)
                    continue
                # ----------------------------------------
                
                if not es_anexo:
                    if patron_visto.match(texto_unido_plano):
                        texto_unido = "## Visto\n" + patron_visto.sub("", texto_unido_plano).strip()
                    elif patron_considerando.match(texto_unido_plano):
                        texto_unido = "## Considerando\n" + patron_considerando.sub("", texto_unido_plano).strip()
                    elif m_res := patron_resuelve.match(texto_unido_plano):
                        encabezado = "## Parte dispositiva" if "DISPONE" in m_res.group(1).upper() else "## Parte resolutiva"
                        texto_unido = f"{encabezado}\n" + patron_resuelve.sub("", texto_unido_plano).strip()
                    elif m := patron_articulo.match(texto_unido_plano):
                        texto_unido = f"### Artículo {m.group(2)}\n" + patron_articulo.sub("", texto_unido_plano).strip()
                    else:
                        
                        # --- NUEVA LÓGICA DE LISTAS INLINE ---
                        # NUEVA FUNCIÓN INTERNA: Evalúa y separa el texto en listas si detecta viñetas
                        def procesar_vinetas_inline(texto):
                            if any(c in texto for c in ['·', '●', '•']):
                                # NUEVA VARIABLE: fragmentos (separa el string por el símbolo de viñeta)
                                fragmentos = re.split(r'[·●•]', texto)
                                # NUEVA VARIABLE: lineas_procesadas (lista donde agruparemos los items resultantes)
                                lineas_procesadas = []
                                
                                frag_inicial = fragmentos[0].strip()
                                if frag_inicial:
                                    if patron_alfabetico.match(frag_inicial):
                                        lineas_procesadas.append("- " + frag_inicial)
                                    else:
                                        # Texto introductorio que venía antes del primer punto
                                        lineas_procesadas.append(frag_inicial)
                                
                                for frag in fragmentos[1:]:
                                    frag_limpio = frag.strip()
                                    if frag_limpio:
                                        lineas_procesadas.append("- " + frag_limpio)
                                
                                return "\n".join(lineas_procesadas)
                            elif patron_alfabetico.match(texto):
                                return "- " + texto
                            return texto
                        # ------------------------------------

                        if texto_sub and len(texto_sub) > 2:
                            if texto_cuerpo:
                                # NUEVA VARIABLE: cuerpo_procesado (Aplica el formateo de listas solo al cuerpo)
                                cuerpo_procesado = procesar_vinetas_inline(texto_cuerpo)
                                texto_unido = f"## {texto_sub}\n\n{cuerpo_procesado}"
                            elif len(texto_sub) < 150 and not texto_sub.endswith('.'):
                                texto_unido = f"## {texto_sub}"
                            else:
                                texto_unido = procesar_vinetas_inline(texto_unido_plano)
                        else:
                            texto_unido = procesar_vinetas_inline(texto_unido_plano)
                
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