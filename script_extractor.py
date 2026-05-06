import fitz
import pandas as pd
import sys
import os
import time
import re
import io
import json  # NUEVO: Importamos json para la creación del metadata

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
    
    patron_visto = re.compile(r'\b(VISTO\b[\s:]*|Visto\b\s*:[\s]*)')
    patron_considerando = re.compile(r'\b(CONSIDERANDO\b[\s:]*|Considerando\b\s*:[\s]*)')
    patron_resuelve = re.compile(r'\b(R\s*E\s*S\s*U\s*E\s*L\s*V\s*E\b[\s:]*|D\s*I\s*S\s*P\s*O\s*N\s*E\b[\s:]*|D\s*E\s*C\s*R\s*E\s*T\s*A\b[\s:]*|RESUELVE\b[\s:]*|DISPONE\b[\s:]*|DECRETA\b[\s:]*|Resuelve\b\s*:[\s]*|Dispone\b\s*:[\s]*|Decreta\b\s*:[\s]*)')
    
    patron_articulo = re.compile(r'(?:^|\n)\s*(ART[IÍ]CULO|Art[ií]culo)\s*(\d+)([:\.\-]*\s*)')
    
    patron_folio = re.compile(r'^\s*-\s*\d+\s*-\s*$')
    patron_paginacion = re.compile(r'^\s*\d+\s*/\s*\d+\s*$')
    patron_anexo_inicio = re.compile(r'^\s*(ANEXO|Anexo)\b', re.IGNORECASE)
    patron_titulo_norma = re.compile(r'(DISPOSICIÓN|RESOLUCIÓN)\s+([A-Z\-]+):\s*(\d+)-(\d+)', re.IGNORECASE)
    
    titulo_encontrado = None

    # --- NUEVO: Inicialización del diccionario JSON de metadata ---
    metadata_json = {
        "source_pdf": nombre_original,
        "document_id_hint": os.path.splitext(nombre_original)[0].lower(),
        "source_system_hint": "unknown",
        "pages": [],
        "global_hints": {
            "has_signature_page": False,
            "has_annexes": False,
            "has_auxiliary_codes": False
        },
        "detected_entities": {
            "document_code_candidates": [],
            "date_candidates": [],
            "city_candidates": [],
            "issuing_body_candidates": []
        },
        "warnings": []
    }
    # --------------------------------------------------------------
    
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
        primer_bloque_pagina = True

        # --- NUEVO: Estructuras para recolectar información de la página actual ---
        info_pagina = {
            "page_number": i + 1,
            "text": "",
            "markers": set(),
            "has_signature_block": False,
            "has_annex_start": False,
            "has_web_disclaimer": False
        }
        textos_bloques_pagina = []
        # -------------------------------------------------------------------------

        for idx, b in enumerate(bloques):
            if b["type"] != 0 or idx in indices_saltados: continue
            
            x0, y0, x1, y1 = b["bbox"]
            centro_y = (y0 + y1) / 2

            lineas_temp = []
            for linea in b["lines"]:
                txt_temp = " ".join([s["text"].strip() for s in linea["spans"] if s["text"].strip()])
                if txt_temp and "///" not in txt_temp and not patron_folio.match(txt_temp) and not patron_paginacion.match(txt_temp):
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
                    primer_bloque_pagina = False
                    break
            
            if not esta_en_tabla:
                textos_subtitulo = []
                textos_cuerpo = []
                leyendo_subtitulo = False
                
                primer_span = None
                for linea in b["lines"]:
                    for span in linea["spans"]:
                        txt_limpio = span["text"].strip()
                        if txt_limpio and "///" not in txt_limpio and not patron_folio.match(txt_limpio) and not patron_paginacion.match(txt_limpio):
                            primer_span = span
                            break
                    if primer_span: break
                
                if primer_span:
                    flags = primer_span.get("flags", 0)
                    font = primer_span.get("font", "").lower()
                    if (flags & 16) != 0 or "bold" in font or "black" in font or "heavy" in font:
                        leyendo_subtitulo = True

                for linea in b["lines"]:
                    sub_linea_actual = []
                    cuerpo_linea_actual = []

                    for span in linea["spans"]:
                        txt_raw = span["text"]
                        txt_strip = txt_raw.strip()
                        
                        if "///" in txt_strip or patron_folio.match(txt_strip) or patron_paginacion.match(txt_strip):
                            continue
                            
                        if not txt_strip:
                            if leyendo_subtitulo: sub_linea_actual.append(txt_raw)
                            else: cuerpo_linea_actual.append(txt_raw)
                            continue
                        
                        flags = span.get("flags", 0)
                        font = span.get("font", "").lower()
                        es_bold = (flags & 16) != 0 or "bold" in font or "black" in font or "heavy" in font
                        
                        if leyendo_subtitulo:
                            if es_bold:
                                sub_linea_actual.append(txt_raw)
                            else:
                                leyendo_subtitulo = False
                                cuerpo_linea_actual.append(txt_raw)
                        else:
                            cuerpo_linea_actual.append(txt_raw)
                    
                    if sub_linea_actual:
                        textos_subtitulo.append("".join(sub_linea_actual).strip())
                    if cuerpo_linea_actual:
                        textos_cuerpo.append("".join(cuerpo_linea_actual).strip())

                texto_sub = " ".join(textos_subtitulo).strip()
                texto_cuerpo = " ".join(textos_cuerpo).strip()
                texto_sub = re.sub(r'\s{2,}', ' ', texto_sub).strip()
                texto_cuerpo = re.sub(r'\s{2,}', ' ', texto_cuerpo).strip()
                
                texto_unido_plano = " ".join([texto_sub, texto_cuerpo]).strip()
                texto_unido_plano = re.sub(r'\s{2,}', ' ', texto_unido_plano).strip()

                # --- NUEVO: Recolección de metadatos del bloque actual ---
                if texto_unido_plano:
                    textos_bloques_pagina.append(texto_unido_plano)
                    
                    match_norma = patron_titulo_norma.search(texto_unido_plano)
                    if match_norma:
                        candidato_codigo = f"{match_norma.group(1)} {match_norma.group(2)}: {match_norma.group(3)}/{match_norma.group(4)}"
                        if candidato_codigo not in metadata_json["detected_entities"]["document_code_candidates"]:
                            metadata_json["detected_entities"]["document_code_candidates"].append(candidato_codigo)
                    
                    if patron_visto.search(texto_unido_plano):
                        info_pagina["markers"].add("VISTO")
                    if patron_considerando.search(texto_unido_plano):
                        info_pagina["markers"].add("CONSIDERANDO")
                    if patron_resuelve.search(texto_unido_plano):
                        info_pagina["markers"].add("RESUELVE")
                    if patron_articulo.search(texto_unido_plano):
                        info_pagina["markers"].add("ARTÍCULO")
                        
                    if es_anexo:
                        info_pagina["has_annex_start"] = True
                        metadata_json["global_hints"]["has_annexes"] = True
                        
                    if "validez para presentación ante terceros" in texto_unido_plano.lower():
                        info_pagina["has_web_disclaimer"] = True
                # --------------------------------------------------------

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

                        if "///" in texto_sig or patron_folio.match(texto_sig) or patron_paginacion.match(texto_sig) or not texto_sig:
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
                    primer_bloque_pagina = False
                    continue
                # ----------------------------------------
                
                if not es_anexo:
                    tiene_encabezado_conocido = bool(
                        patron_visto.search(texto_unido_plano) or 
                        patron_considerando.search(texto_unido_plano) or 
                        patron_resuelve.search(texto_unido_plano) or 
                        patron_articulo.search(texto_unido_plano)
                    )

                    def procesar_vinetas_inline(texto):
                        if any(c in texto for c in ['·', '●', '•']):
                            fragmentos = re.split(r'[·●•]', texto)
                            lineas_procesadas = []
                            
                            frag_inicial = fragmentos[0].strip()
                            if frag_inicial:
                                if patron_alfabetico.match(frag_inicial):
                                    lineas_procesadas.append("- " + frag_inicial)
                                else:
                                    lineas_procesadas.append(frag_inicial)
                            
                            for frag in fragmentos[1:]:
                                frag_limpio = frag.strip()
                                if frag_limpio:
                                    lineas_procesadas.append("- " + frag_limpio)
                            
                            return "\n".join(lineas_procesadas)
                        elif patron_alfabetico.match(texto):
                            return "- " + texto
                        return texto

                    if tiene_encabezado_conocido:
                        def procesar_encabezados(texto):
                            t = patron_visto.sub(r'\n\n## Visto\n', texto)
                            t = patron_considerando.sub(r'\n\n## Considerando\n', t)
                            
                            def reemplazo_resuelve(m):
                                palabra = m.group(1).upper().replace(" ", "")
                                encabezado = "dispositiva" if "DISPONE" in palabra else "resolutiva"
                                return f"\n\n## Parte {encabezado}\n"
                                
                            t = patron_resuelve.sub(reemplazo_resuelve, t)
                            t = patron_articulo.sub(r'\n\n### Artículo \2\n', t)
                            
                            t = re.sub(r'\n{3,}', '\n\n', t)
                            return t.strip()
                            
                        texto_unido = procesar_encabezados(texto_unido_plano)
                        texto_unido = procesar_vinetas_inline(texto_unido)
                    
                    else:
                        if texto_sub and len(texto_sub) > 2:
                            if texto_cuerpo:
                                cuerpo_procesado = procesar_vinetas_inline(texto_cuerpo)
                                texto_unido = f"## {texto_sub}\n\n{cuerpo_procesado}"
                            elif len(texto_sub) < 150 and not texto_sub.endswith('.'):
                                texto_unido = f"## {texto_sub}"
                            else:
                                texto_unido = procesar_vinetas_inline(texto_unido_plano)
                        else:
                            texto_unido = procesar_vinetas_inline(texto_unido_plano)
                
                if primer_bloque_pagina and contenido_final:
                    ultimo_bloque = contenido_final[-1].rstrip()
                    lineas_ultimo = [l for l in ultimo_bloque.split('\n') if l.strip()]
                    
                    if lineas_ultimo:
                        ultima_linea = lineas_ultimo[-1].strip()
                        
                        if (not ultima_linea.endswith('.') and 
                            not ultima_linea.endswith(':') and 
                            not ultima_linea.startswith('#') and 
                            not ultima_linea.startswith('|') and 
                            not texto_unido.startswith('#') and 
                            not texto_unido.startswith('|') and 
                            not texto_unido.startswith('- ') and 
                            '\n## ' not in texto_unido):
                            
                            contenido_final[-1] = ultimo_bloque + " " + texto_unido
                            primer_bloque_pagina = False
                            continue
                
                contenido_final.append(texto_unido)
                primer_bloque_pagina = False

        # --- NUEVO: Al finalizar de iterar la página, consolidamos su información para el JSON ---
        info_pagina["text"] = "\n".join(textos_bloques_pagina)
        info_pagina["markers"] = list(info_pagina["markers"])  # Convertimos a lista para que sea serializable
        metadata_json["pages"].append(info_pagina)
        # ------------------------------------------------------------------------------------------

    doc.close()
    if titulo_encontrado: contenido_final.insert(0, titulo_encontrado)

    nombre_salida = f"{os.path.splitext(nombre_original)[0]}_jerarquizado.md"
    with open(nombre_salida, "w", encoding="utf-8") as f:
        f.write("\n\n".join(contenido_final))

    # --- NUEVO: Exportación del metadata JSON ---
    nombre_salida_json = f"{os.path.splitext(nombre_original)[0]}_auxiliar.json"
    with open(nombre_salida_json, "w", encoding="utf-8") as f_json:
        json.dump(metadata_json, f_json, ensure_ascii=False, indent=4)
    # --------------------------------------------

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