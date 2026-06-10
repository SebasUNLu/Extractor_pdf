import fitz
import pandas as pd
import sys
import os
import time
import re
import io
import json

TITULOS_FIRMA = r'Prof\.|Lic\.|Dr\.|Dra\.|Ing\.|Bioq\.|Esp\.|Mg\.|Mgter\.|Mag\.|Abog\.'
NOMBRE_FIRMANTE = r'((?:(?:[A-ZÁÉÍÓÚÑ][a-záéíóúüñ]+|[A-ZÁÉÍÓÚÑ]\.)\s+)*(?:[A-ZÁÉÍÓÚÑ]{2,}|[A-ZÁÉÍÓÚÑ][a-záéíóúüñ]{2,})(?:\s+(?:[A-ZÁÉÍÓÚÑ]{2,}|[A-ZÁÉÍÓÚÑ][a-záéíóúüñ]{2,}))*)'
ROL_FIRMANTE_KEYWORDS = r'(?:presidente|rector(?:a)?|secretari[oa]|subsecretari[oa]|director(?:a)?|decano|coordinador(?:a)?|jefe|responsable|vicedirector(?:a)?)'

def normalizar_fecha(dia, mes_str, anio):
    """
    Normaliza fechas al formato ISO (YYYY-MM-DD) requerido por el YAML.
    """
    if len(anio) == 2:
        anio = "20" + anio 
    elif len(anio) != 4:
        return None
        
    meses = {
        'ene': '01', 'feb': '02', 'mar': '03', 'abr': '04',
        'may': '05', 'jun': '06', 'jul': '07', 'ago': '08',
        'sep': '09', 'set': '09', 'oct': '10', 'nov': '11', 'dic': '12'
    }
    
    if mes_str.isdigit():
        mes = mes_str.zfill(2)
    else:
        mes_clean = mes_str.lower()[:3]
        mes = meses.get(mes_clean, None)
        
    if mes is None:
        return None
        
    dia = dia.zfill(2)
    
    try:
        if int(dia) > 31 or int(mes) > 12 or int(dia) == 0 or int(mes) == 0:
            return None
    except ValueError:
        return None
        
    return f"{anio}-{mes}-{dia}"

def limpiar_rol_firmante(rol):
    """
    Normaliza cargos detectados cerca de las firmas.
    """
    if not rol:
        return ""

    rol = re.sub(r'\s+', ' ', rol).strip(" .:-\t")
    if not rol:
        return ""

    return rol[:1].upper() + rol[1:]

def es_rol_firmante_valido(rol):
    rol = limpiar_rol_firmante(rol)
    if not rol or rol.lower() == "unknown":
        return False

    if len(rol) > 180:
        return False

    if re.search(r'(https?://|doi\.org|[•●]|bibliograf|revista|jornadas|tesis|anexo|art[ií]culo)', rol, re.IGNORECASE):
        return False

    return bool(re.search(
        rf'\b{ROL_FIRMANTE_KEYWORDS}\b',
        rol,
        re.IGNORECASE
    ))

def extraer_nombre_y_rol_firmante(match):
    nombre = re.sub(r'\s+', ' ', match.group(1)).strip()
    rol_bruto = re.sub(r'\s+', ' ', match.group(2)).strip() if match.group(2) else ""
    rol = limpiar_rol_firmante(rol_bruto)

    partes_nombre = nombre.split()
    if rol and partes_nombre and re.fullmatch(ROL_FIRMANTE_KEYWORDS, partes_nombre[-1], re.IGNORECASE):
        rol = limpiar_rol_firmante(f"{partes_nombre[-1]} {rol_bruto}")
        nombre = " ".join(partes_nombre[:-1]).strip()

    return nombre, rol

def es_texto_firma_tradicional_valido(texto_firma, match):
    texto = re.sub(r'\s+', ' ', texto_firma).strip()
    if len(texto) > 220 or re.search(r'[•●|]|https?://|doi\.org', texto, re.IGNORECASE):
        return False

    nombre, rol_en_linea = extraer_nombre_y_rol_firmante(match)
    tiene_titulo = bool(re.match(rf'^(?:(?:{TITULOS_FIRMA})\s+)', texto, re.IGNORECASE))
    if not tiene_titulo:
        if len(texto) > 130:
            return False
        if re.search(r'[\d/:]', texto):
            return False
        if not re.search(r'\b[A-ZÁÉÍÓÚÑ]\.', nombre):
            return False
        if re.match(r'^(que|la|el|los|las|designar|resoluci[oó]n|disposici[oó]n|art[ií]culo|sr|sra|se[ñn]or)\b', nombre, re.IGNORECASE):
            return False

    if rol_en_linea:
        return es_rol_firmante_valido(rol_en_linea)

    return len(texto) <= 100 and not re.search(r'\d{4}|[,;()]', texto)

def buscar_firmantes_sin_titulo(texto, patron_firmante_sin_titulo):
    texto_limpio = re.sub(r'\s+', ' ', texto).strip()
    if len(texto_limpio) > 160:
        return []
    if not re.search(rf'\b{ROL_FIRMANTE_KEYWORDS}\b', texto_limpio, re.IGNORECASE):
        return []
    return list(patron_firmante_sin_titulo.finditer(texto_limpio))

def buscar_firmante_por_texto(texto_firma, firmantes):
    texto_norm = re.sub(r'\s+', ' ', texto_firma).strip().lower()
    for firmante in firmantes:
        nombre = firmante.get("name", "")
        if nombre and nombre.lower() in texto_norm:
            return firmante
    return None

def nombre_con_titulo_desde_firma(texto_firma, nombre):
    patron = re.compile(
        rf'((?:(?:{TITULOS_FIRMA})\s+)*)' + re.escape(nombre),
        re.IGNORECASE
    )
    match = patron.search(texto_firma)
    if match:
        return re.sub(r'\s+', ' ', match.group(0)).strip()
    return nombre

def formatear_bloque_firmas_md(bloque, firmantes):
    """
    Reescribe el bloque ## Firmas usando los roles ya consolidados en el JSON.
    """
    lineas_formateadas = []

    for linea in bloque.split('\n'):
        linea_limpia = linea.strip()
        if not linea_limpia.startswith("- "):
            continue

        firma_original = linea_limpia[2:].strip()
        firmante = buscar_firmante_por_texto(firma_original, firmantes)
        if not firmante:
            lineas_formateadas.append(f"- {firma_original}")
            continue

        nombre = firmante.get("name", "").strip()
        rol = limpiar_rol_firmante(firmante.get("role", ""))
        nombre_visible = nombre_con_titulo_desde_firma(firma_original, nombre)

        if es_rol_firmante_valido(rol):
            lineas_formateadas.append(f"- {nombre_visible} - {rol}")
        else:
            lineas_formateadas.append(f"- {nombre_visible}")

    if not lineas_formateadas:
        return bloque

    return "## Firmas\n" + "\n".join(lineas_formateadas)

def quitar_roles_sueltos_antes_de_firmas(contenido_final, firmantes):
    """
    Quita lineas de cargos que ya van a quedar representadas dentro de ## Firmas.
    """
    roles = {
        limpiar_rol_firmante(f.get("role", "")).lower()
        for f in firmantes
        if es_rol_firmante_valido(f.get("role", ""))
    }

    if not roles:
        return contenido_final

    resultado = []
    for bloque in contenido_final:
        if isinstance(bloque, str) and bloque.lstrip().startswith("## Firmas") and resultado:
            while resultado:
                lineas_previas = resultado[-1].split('\n')
                hubo_cambios = False

                while lineas_previas:
                    while lineas_previas and not lineas_previas[-1].strip():
                        lineas_previas.pop()
                        hubo_cambios = True
                    if lineas_previas and lineas_previas[-1].strip().lower() in roles:
                        lineas_previas.pop()
                        hubo_cambios = True
                        continue
                    break

                bloque_limpio = "\n".join(lineas_previas).rstrip()
                if not bloque_limpio:
                    resultado.pop()
                    continue

                resultado[-1] = bloque_limpio
                if not hubo_cambios:
                    break
                break
        resultado.append(bloque)

    return resultado

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
                        if span["text"].strip():
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
    patron_titulo_norma = re.compile(
        r'\b(DISPOSICI[ÓO]N|RESOLUCI[ÓO]N)\b'
        r'(?:\s+(?:(?!\bVISTO\b|\bCONSIDERANDO\b|\bART[IÍ]CULO\b).){0,180}?)?'
        r'\b([A-Z]{2,}(?:-[A-Z0-9]+)*)\s*:\s*0*(\d+)\s*(?:[\/\-])\s*(\d{2,4})\b',
        re.IGNORECASE
    )
    
    patron_fecha_num = re.compile(r'\b(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})\b')
    patron_fecha_texto = re.compile(r'\b(\d{1,2})\s*(?:de\s*)?([a-zA-Z]{3,10})\s*(?:de\s*)?(\d{2,4})\b', re.IGNORECASE)

    # OPTIMIZACIÓN: Captura EXP-LUJ, ACTDB-LUJ, EXPP, DISPCD-TLUJ, DISPCD-T, RESHCS, etc.
    patron_codigo_auxiliar = re.compile(
        r'\b(EXP-LUJ|ACTDB-LUJ|EXPP|DISPCD-TLUJ|DISPCD-T|RESHCS-LUJ|RESPHCS|SEACAD|[A-Z]{3,}(?:-[A-Z0-9]+)*)\s*(?:[:\-–—]|N[°º.\s]+)?\s*\d+[\/\-]\d{2,4}\b', 
        re.IGNORECASE
    )
    
    patron_ciudad_emision = re.compile(
        r'\b(Luj[aá]n|Campana|Chivilcoy|San\s+Miguel|CABA|Buenos\s+Aires|Capital\s+Federal)\b'
        r'(?:\s*,\s*(Buenos\s+Aires))?'
        r'\s*,?\s*'
        r'(?=(?:\d{1,2}\s*(?:de\s*)?(?:[a-zA-ZáéíóúÁÉÍÓÚ]{3,10})\s*(?:de\s*)?\d{2,4}'
        r'|\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}'
        r'|\bVISTO\b|$))',
        re.IGNORECASE
    )
    
    patron_disclaimer_web = re.compile(r'(texto de los documentos publicados|validez para su presentación en terceras|de gestión de doc\. y actos adm)', re.IGNORECASE)
    
    # Patrones para entidades específicas
    patron_emisor = re.compile(r'\b(H\.\s*CONSEJO\s+SUPERIOR|CONSEJO\s+DIRECTIVO|RECTORADO|DEPARTAMENTO\s+DE\s+[A-Z\sÁÉÍÓÚ]+)\b', re.IGNORECASE)
    patron_firmante = re.compile(rf'(?:(?:{TITULOS_FIRMA})\s+)+{NOMBRE_FIRMANTE}(?:[\s\.\-:]+(.*))?')
    patron_firmante_sin_titulo = re.compile(rf'\b{NOMBRE_FIRMANTE}[\s\.\-:]+({ROL_FIRMANTE_KEYWORDS}\b.*)', re.IGNORECASE)
       
    patron_firma_sudocu = re.compile(r'\b(Cargado por|Autorizado por|Firmado por)\s*:\s*([A-ZÁÉÍÓÚÑa-záéíóúüñ\s]+)', re.IGNORECASE)
    
    patron_persona = re.compile(r'([A-Z][a-záéíóúüñ]+(?:\s+[A-Z][a-záéíóúüñ]+)*\s+[A-ZÁÉÍÓÚÑ]+(?:\s+[A-ZÁÉÍÓÚÑ]+)*)\s*(?:\(D\.N\.I|\(Legajo|D\.N\.I|Legajo)')
    patron_normativa = re.compile(r'\b(Ley\s+N?[°º]?\s*\d+\.?\d*|(?:Resolución|Disposición)\s+(?:RESHCS|DISPPCD|DISPSECADM|RES|DISP)[A-Z\-]*[:\s]*\d+[-/]\d+)\b', re.IGNORECASE)
    patron_carrera = re.compile(r'\b(Licenciatura\s+en\s+[A-Za-záéíóúüñ\s]+|Ingeniería\s+[A-Za-záéíóúüñ\s]+|Profesorado\s+en\s+[A-Za-záéíóúüñ\s]+)\b', re.IGNORECASE)
    patron_curso = re.compile(r'\b(?:Asignatura|Materia|Curso)?\s*[:\-]?\s*\(?(\d{5})\)?\s*[\-\.\–]?\s*([A-ZÁÉÍÓÚ][A-Za-záéíóúüñI\s]+)(?=[,;\.\n]|$)', re.IGNORECASE)
    
    patron_hoja_firmas = re.compile(r'\bHoja\s+de\s+firmas\b', re.IGNORECASE)
    
    titulo_encontrado = None

    metadata_json = {
        "source_pdf": nombre_original,
        "document_id_hint": "unknown",
        "source_system_hint": "legacy",
        "pages": [],
        "global_hints": {
            "has_signature_page": False,
            "has_annexes": False,
            "has_auxiliary_codes": False,
            "auxiliary_codes": []
        },
        "detected_entities": {
            "document_code_candidates": [],
            "date_candidates": [],
            "city_candidates": [],
            "issuing_body_candidates": [],
            "signers_candidates": [],
            "person_candidates": [],
            "academic_unit_candidates": [],
            "career_candidates": [],
            "course_candidates": [],
            "normative_candidates": []
        },
        "warnings": []
    }
    
    for i, pagina in enumerate(doc):
        cp = pagina.cropbox
        alto = cp.height

        for widget in pagina.widgets(): 
            if widget.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                metadata_json["source_system_hint"] = "electronic"
        
        margen_superior = cp.y0 + (alto * 0.20)
        margen_inferior = alto

        tabs = pagina.find_tables(strategy="lines_strict", snap_tolerance=4)
        areas_tablas = []
        for t in tabs.tables:
            if t.row_count > 1 and t.col_count <= 8:
                areas_tablas.append(t.bbox)
        tablas_procesadas = []

        bloques_crudos = pagina.get_text("dict")["blocks"]
        
        bloques_ordenados_y = sorted(bloques_crudos, key=lambda b: (b["bbox"][1], b["bbox"][0]))
        
        grupos = []
        for b in bloques_ordenados_y:
            if b.get("type", 1) != 0: 
                grupos.append([b])
                continue
                
            añadido = False
            for g in grupos:
                if g[-1].get("type", 1) != 0: continue
                ultimo_b = g[-1]
                
                dist_y = b["bbox"][1] - ultimo_b["bbox"][3]
                x_overlap = max(0, min(b["bbox"][2], ultimo_b["bbox"][2]) - max(b["bbox"][0], ultimo_b["bbox"][0]))
                
                if -15 <= dist_y <= 60 and x_overlap > 10:
                    g.append(b)
                    añadido = True
                    break
            
            if not añadido:
                grupos.append([b])

        grupos.sort(key=lambda g: (g[0]["bbox"][1] // 20, g[0]["bbox"][0]))
        bloques = [b for g in grupos for b in g]

        indices_saltados = set()
        primer_bloque_pagina = True

        info_pagina = {
            "page_number": i + 1,
            "text": "",
            "markers": set(),
            "has_signature_block": False,
            "has_annex_start": False,
            "has_web_disclaimer": False
        }
        
        textos_bloques_pagina = []
        firmas_pagina = [] 

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
            es_hoja_firmas = bool(patron_hoja_firmas.search(texto_temp))
            es_firma_bloque = (
                bool(patron_firmante.search(texto_temp)) or
                bool(buscar_firmantes_sin_titulo(texto_temp, patron_firmante_sin_titulo)) or
                bool(patron_firma_sudocu.search(texto_temp))
            )

            if not (margen_superior <= centro_y <= margen_inferior) and not es_anexo and not es_hoja_firmas and not es_firma_bloque:
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

                es_bloque_firma = False

                if texto_unido_plano:
                    
                    if patron_hoja_firmas.search(texto_unido_plano):
                        metadata_json["global_hints"]["has_signature_page"] = True

                    if patron_disclaimer_web.search(texto_unido_plano):
                        info_pagina["has_web_disclaimer"] = True
                        primer_bloque_pagina = False
                        continue

                    textos_bloques_pagina.append(texto_unido_plano)
                    
                    match_norma = patron_titulo_norma.search(texto_unido_plano)
                    if match_norma:
                        candidato_codigo = f"{match_norma.group(1)} {match_norma.group(2)}: {match_norma.group(3)}/{match_norma.group(4)}"
                        if candidato_codigo not in metadata_json["detected_entities"]["document_code_candidates"]:
                            metadata_json["detected_entities"]["document_code_candidates"].append(candidato_codigo)
                    
                    for match in patron_fecha_num.finditer(texto_unido_plano):
                        d, m, a = match.groups()
                        fecha_norm = normalizar_fecha(d, m, a)
                        if fecha_norm and fecha_norm not in metadata_json["detected_entities"]["date_candidates"]:
                            metadata_json["detected_entities"]["date_candidates"].append(fecha_norm)

                    for match in patron_fecha_texto.finditer(texto_unido_plano):
                        d, m, a = match.groups()
                        fecha_norm = normalizar_fecha(d, m, a)
                        if fecha_norm and fecha_norm not in metadata_json["detected_entities"]["date_candidates"]:
                            metadata_json["detected_entities"]["date_candidates"].append(fecha_norm)
                    
                    for match in patron_ciudad_emision.finditer(texto_unido_plano):
                        ciudad_detectada = match.group(1).upper()
                        provincia_detectada = match.group(2).upper() if match.group(2) else ""
                        if ciudad_detectada in ["LUJAN", "LUJÁN"]:
                            ciudad_detectada = "LUJÁN"
                        if provincia_detectada == "BUENOS AIRES" and ciudad_detectada != "BUENOS AIRES":
                            ciudad_detectada = f"{ciudad_detectada}, BUENOS AIRES"
                            
                        if ciudad_detectada not in metadata_json["detected_entities"]["city_candidates"]:
                            metadata_json["detected_entities"]["city_candidates"].append(ciudad_detectada)

                    for match in patron_emisor.finditer(texto_unido_plano):
                        emisor = match.group(1).strip().title()
                        if emisor not in metadata_json["detected_entities"]["issuing_body_candidates"]:
                            metadata_json["detected_entities"]["issuing_body_candidates"].append(emisor)
                        if "Departamento" in emisor and emisor not in metadata_json["detected_entities"]["academic_unit_candidates"]:
                            metadata_json["detected_entities"]["academic_unit_candidates"].append(emisor)

                    es_firma_tradicional = False
                    matches_firmantes = list(patron_firmante.finditer(texto_unido_plano))
                    matches_firmantes.extend(buscar_firmantes_sin_titulo(texto_unido_plano, patron_firmante_sin_titulo))
                    for match in matches_firmantes:
                        if not es_texto_firma_tradicional_valido(texto_unido_plano, match):
                            continue
                        firmante, rol_en_linea = extraer_nombre_y_rol_firmante(match)
                        if not any(f.get("name") == firmante for f in metadata_json["detected_entities"]["signers_candidates"]):
                            metadata_json["detected_entities"]["signers_candidates"].append({
                                "name": firmante,
                                "role": rol_en_linea if es_rol_firmante_valido(rol_en_linea) else "unknown"
                            })
                        es_bloque_firma = True
                        es_firma_tradicional = True

                    if es_firma_tradicional:
                        texto_firma_limpio = texto_unido_plano.replace('\n', ' ')
                        if texto_firma_limpio not in firmas_pagina:
                            firmas_pagina.append(texto_firma_limpio)
                            
                    for match in patron_firma_sudocu.finditer(texto_unido_plano):
                        nombre = match.group(2).strip()
                        if not any(f.get("name") == nombre for f in metadata_json["detected_entities"]["signers_candidates"]):
                            metadata_json["detected_entities"]["signers_candidates"].append({"name": nombre, "role": "unknown"})
                            
                        if nombre not in firmas_pagina:
                            firmas_pagina.append(nombre)
                            
                        es_bloque_firma = True
                        
                    if metadata_json["global_hints"].get("has_signature_page"):
                        if re.search(r'\b(Sistema:\s*sudocu|Fecha:\s*\d{2}/\d{2}/\d{4})\b', texto_unido_plano, re.IGNORECASE):
                            es_bloque_firma = True 

                    for match in patron_persona.finditer(texto_unido_plano):
                        persona = match.group(1).strip()
                        if persona not in metadata_json["detected_entities"]["person_candidates"]:
                            metadata_json["detected_entities"]["person_candidates"].append(persona)

                    for match in patron_normativa.finditer(texto_unido_plano):
                        norma = match.group(1).strip()
                        if norma not in metadata_json["detected_entities"]["normative_candidates"]:
                            metadata_json["detected_entities"]["normative_candidates"].append(norma)

                    for match in patron_carrera.finditer(texto_unido_plano):
                        carrera = match.group(1).strip()
                        if carrera not in metadata_json["detected_entities"]["career_candidates"]:
                            metadata_json["detected_entities"]["career_candidates"].append(carrera)
                            
                    for linea_individual in lineas_temp:
                        for match in patron_curso.finditer(linea_individual):
                            codigo_curso = match.group(1).strip()
                            nombre_curso_bruto = match.group(2).strip()
                            
                            nombre_limpio = re.sub(r'\s+(?:para|del?|con|y|que|por|el|la|los|las|de)\s*$', '', nombre_curso_bruto, flags=re.IGNORECASE).strip()
                            nombre_title = nombre_limpio.title()
                            nombre_title = nombre_title.replace(" En ", " en ").replace(" De ", " de ").replace(" Del ", " del ").replace(" Y ", " y ")
                            nombre_title = re.sub(r'\bIi+\b', lambda x: x.group().upper(), nombre_title) 
                            nombre_title = re.sub(r'\bIv\b|\bVi+\b|\bIx\b', lambda x: x.group().upper(), nombre_title)

                            curso_obj = {
                                "code": codigo_curso,
                                "name": nombre_title
                            }
                            
                            if not any(c.get("code") == codigo_curso for c in metadata_json["detected_entities"]["course_candidates"]):
                                metadata_json["detected_entities"]["course_candidates"].append(curso_obj)

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
                        
                    # PROCESAMIENTO REESCRITO: Almacena el código completo encontrado (ej: DISPCD-TLUJ: 0000352-23)
                    matches_aux = patron_codigo_auxiliar.finditer(texto_unido_plano)
                    for m in matches_aux:
                        cod = m.group(0).strip()
                        if cod not in metadata_json["global_hints"]["auxiliary_codes"]:
                            metadata_json["global_hints"]["auxiliary_codes"].append(cod)
                            metadata_json["global_hints"]["has_auxiliary_codes"] = True

                if not titulo_encontrado:
                    match = patron_titulo_norma.search(texto_unido_plano)
                    if match:
                        titulo_encontrado = f"# {match.group(1).capitalize()} {match.group(2)} - {int(match.group(3))}/{match.group(4)}"
                        continue

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
                
                if not es_bloque_firma:
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

        if firmas_pagina:
            info_pagina["has_signature_block"] = True
            bloque_firmas = "## Firmas\n" + "\n".join([f"- {f}" for f in firmas_pagina])
            contenido_final.append(bloque_firmas)

        info_pagina["text"] = "\n".join(textos_bloques_pagina)
        info_pagina["markers"] = list(info_pagina["markers"])
        metadata_json["pages"].append(info_pagina)

    doc.close()
    
    for pagina_info in metadata_json["pages"]:
        if pagina_info.get("has_signature_block"):
            lineas = [l.strip() for l in pagina_info["text"].split('\n') if l.strip()]
            
            for idx, linea in enumerate(lineas):
                match = patron_firmante.search(linea)
                if not match:
                    matches_sin_titulo = buscar_firmantes_sin_titulo(linea, patron_firmante_sin_titulo)
                    match = matches_sin_titulo[0] if matches_sin_titulo else None
                if match:
                    if not es_texto_firma_tradicional_valido(linea, match):
                        continue
                    nombre, rol = extraer_nombre_y_rol_firmante(match)
                    
                    if not rol:
                        candidatos_rol = []
                        if idx + 1 < len(lineas): candidatos_rol.append(lineas[idx + 1])
                        if idx - 1 >= 0: candidatos_rol.append(lineas[idx - 1])
                        
                        for posible_rol in candidatos_rol:
                            if patron_firmante.search(posible_rol) or buscar_firmantes_sin_titulo(posible_rol, patron_firmante_sin_titulo): continue
                            if re.search(r'^(ART[IÍ]CULO|RESOLUCI[OÓ]N|DISPOSICI[OÓ]N|LUJ[AÁ]N|///|#|EXP-|VISTO|CONSIDERANDO)', posible_rol, re.IGNORECASE): continue
                            if len(posible_rol) < 4: continue
                            if not es_rol_firmante_valido(posible_rol): continue
                            
                            rol = limpiar_rol_firmante(posible_rol.title())
                            break
                    
                    if es_rol_firmante_valido(rol):
                        for candidato in metadata_json["detected_entities"]["signers_candidates"]:
                            if candidato["name"] == nombre and candidato["role"] == "unknown":
                                candidato["role"] = rol

    firmantes_detectados = metadata_json["detected_entities"]["signers_candidates"]
    contenido_final = quitar_roles_sueltos_antes_de_firmas(contenido_final, firmantes_detectados)
    contenido_final = [
        formatear_bloque_firmas_md(bloque, firmantes_detectados)
        if isinstance(bloque, str) and bloque.lstrip().startswith("## Firmas")
        else bloque
        for bloque in contenido_final
    ]
    contenido_final = [bloque for bloque in contenido_final if not (isinstance(bloque, str) and not bloque.strip())]
    
    if titulo_encontrado: 
        contenido_final.insert(0, titulo_encontrado)
        
        m_hint = re.search(r'#\s*(Resolución|Disposición|Resolucion|Disposicion)\s+(.*)', titulo_encontrado, re.IGNORECASE)
        if m_hint:
            palabra_clave = m_hint.group(1).lower()
            tipo_doc = "res" if "res" in palabra_clave else "disp"
            resto_doc = m_hint.group(2).lower()
            resto_doc = re.sub(r'[\s\/\-\:]+', '_', resto_doc).strip('_')
            
            metadata_json["document_id_hint"] = f"{tipo_doc}_{resto_doc}"

    nombre_salida = f"{os.path.splitext(nombre_original)[0]}.md"
    with open(nombre_salida, "w", encoding="utf-8") as f:
        f.write("\n\n".join(contenido_final))

    nombre_salida_json = f"{os.path.splitext(nombre_original)[0]}.json"
    with open(nombre_salida_json, "w", encoding="utf-8") as f_json:
        json.dump(metadata_json, f_json, ensure_ascii=False, indent=4)

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
