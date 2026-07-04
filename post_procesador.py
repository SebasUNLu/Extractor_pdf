import json
import os
import sys
import re
import yaml # Requiere instalar la librería: pip install pyyaml

def extraer_codigo_desde_encabezado_md(contenido_md):
    """
    Prioriza encabezados formales del portal, por ejemplo:
    DISPOSICION ... DISPCD-T : 441 / 2024
    """
    lineas = [l.strip() for l in contenido_md.split('\n') if l.strip()]
    patron_encabezado_portal = re.compile(
        r'^\s*(?:#\s*)?(?:DISPOSICI[ÓO]N|RESOLUCI[ÓO]N)\b'
        r'.*?\b([A-Z]{2,}(?:-[A-Z0-9]+)*)\s*:\s*(\d+)\s*(?:[\/\-])\s*(\d{2,4})\b',
        re.IGNORECASE
    )
    patron_encabezado_generado = re.compile(
        r'^\s*(?:#\s*)?(?:DISPOSICI[ÓO]N|RESOLUCI[ÓO]N)\s+'
        r'([A-Z]{1,8}(?:\.[A-Z]{1,8})*|[A-Z]{2,}(?:-[A-Z0-9]+)*)'
        r'\s*[-:]\s*0*(\d+)\s*(?:[\/\-])\s*(\d{2,4})\b',
        re.IGNORECASE
    )

    for linea in lineas[:12]:
        if re.search(r'\b(VISTO|CONSIDERANDO|ART[IÍ]CULO)\b', linea, re.IGNORECASE):
            break

        match = patron_encabezado_portal.search(linea)
        if not match:
            match = patron_encabezado_generado.search(linea)
        if match:
            codigo = match.group(1).strip().rstrip(".")
            numero = match.group(2).strip()
            anio = match.group(3).strip()
            return codigo, f"{numero}/{anio}"

    return None, None

def normalizar_ciudad(valor):
    valor = re.sub(r'\s+', ' ', str(valor)).strip(" ,")
    if not valor:
        return "unknown"

    partes = [p.strip().upper() for p in valor.split(",") if p.strip()]
    partes_normalizadas = ["LUJÁN" if p == "LUJAN" else p for p in partes]
    return ", ".join(partes_normalizadas) if partes_normalizadas else "unknown"

def extraer_ciudad_desde_md(contenido_md):
    patron_ciudad = re.compile(
        r'^\s*(?:#\s*)?'
        #verificar que esto tome nombres completamente en mayusculas
        r'(Luj[aá]n|Campana|Chivilcoy|San\s+Miguel|CABA|Buenos\s+Aires|Capital\s+Federal)' 
        r'(?:\s*,\s*(Buenos\s+Aires))?'
        r'\s*,?\s*'
        r'(?:\d{1,2}\s*(?:de\s*)?(?:[a-zA-ZáéíóúÁÉÍÓÚ]{3,10})\s*(?:de\s*)?\d{2,4}'
        r'|[a-zA-ZáéíóúÁÉÍÓÚ]{3,10}\s*(?:de\s*)?\d{2,4}'
        r'|\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})?'
        r'\s*(?:\.-)?\s*$',
        re.IGNORECASE
    )

    for linea in contenido_md.splitlines()[:12]:
        match = patron_ciudad.search(linea.strip())
        if match:
            ciudad = normalizar_ciudad(match.group(1))
            provincia = normalizar_ciudad(match.group(2)) if match.group(2) else ""
            if provincia == "BUENOS AIRES" and ciudad != "BUENOS AIRES":
                return f"{ciudad}, BUENOS AIRES"
            return ciudad

    return "unknown"

def procesar_metadatos(json_data, contenido_md):
    """
    Toma los 'hints' del JSON y el texto del Markdown para tomar
    las decisiones definitivas y normalizar la metadata.
    """
    # 1. Definir el tipo de documento (Resolución, Disposición o Unknown)
    doc_id_hint = json_data.get("document_id_hint", "unknown").lower()
    
    # NUEVA LÓGICA: Extraemos la primera línea relevante del MD para inspeccionarla
    lineas_md = [l.strip() for l in contenido_md.split('\n') if l.strip()]
    primera_linea = lineas_md[0].lower() if lineas_md else ""

    # Prioridad 1: Hint del ID de documento
    if doc_id_hint.startswith("res_"):
        document_type = "resolucion"
    elif doc_id_hint.startswith("disp_"):
        document_type = "disposicion"
    
    # Prioridad 2: Inspección de la primera línea del MD (títulos #)
    elif "resolución" in primera_linea or "resolucion" in primera_linea:
        document_type = "resolucion"
    elif "disposición" in primera_linea or "disposicion" in primera_linea:
        document_type = "disposicion"
    
    else:
        # Prioridad 3: Lógica de respaldo en candidatos detectados
        candidates = json_data.get("detected_entities", {}).get("document_code_candidates", [])
        if candidates:
            primer_cand = candidates[0].lower()
            if "resolución" in primer_cand or "resolucion" in primer_cand:
                document_type = "resolucion"
            elif "disposición" in primer_cand or "disposicion" in primer_cand:
                document_type = "disposicion"
            else:
                document_type = "unknown"
        else:
            document_type = "unknown"

    # 2. Extraer Código y Número del documento principal
    candidates = json_data.get("detected_entities", {}).get("document_code_candidates", [])
    document_code, document_number = extraer_codigo_desde_encabezado_md(contenido_md)

    if (not document_code or not document_number) and candidates:
        partes = candidates[0].split(":")
        if len(partes) >= 2:
            document_code = partes[0].split(" ")[-1].strip()
            document_number = partes[1].strip()

    document_code = document_code or "unknown"
    document_number = document_number or "unknown"

    # 3. Normalizar Fecha y Año
    date_cands = json_data.get("detected_entities", {}).get("date_candidates", [])
    date_issued = date_cands[0] if date_cands else "unknown"
    try:
        year = int(date_issued.split("-")[0]) if date_issued != "unknown" else "unknown"
    except ValueError:
        year = "unknown"

    # 4. Normalizar Ciudad
    city_cands = json_data.get("detected_entities", {}).get("city_candidates", [])
    city = normalizar_ciudad(city_cands[0]) if city_cands else extraer_ciudad_desde_md(contenido_md)

    # 5. Resolver Anexos
    has_annexes = json_data.get("global_hints", {}).get("has_annexes", False)
    annex_count = len(re.findall(r'^#\s*(ANEXO|Anexo)', contenido_md, re.MULTILINE))
    if has_annexes and annex_count == 0:
        annex_count = 1

    # 6. Códigos Auxiliares
    auxiliary_codes = json_data.get("global_hints", {}).get("auxiliary_codes", [])

    # 7. Notas de publicación
    publication_notes = []
    for page in json_data.get("pages", []):
        if page.get("has_web_disclaimer"):
            nota = "El texto publicado en el sitio web no tiene validez para su presentación en terceras instituciones y/o entidades, salvo que contaren con autenticación expedida por la Dir. de Gestión de Doc. y Actos Adm."
            if nota not in publication_notes:
                publication_notes.append(nota)

    # 8. Modalidad de firma
    source_system = json_data.get("source_system_hint", "unknown")
    has_sig_page = json_data.get("global_hints", {}).get("has_signature_page", False)
    
    if source_system == "electronic":
        signature_mode = "digital"
    elif has_sig_page:
        signature_mode = "separate_page"
    else:
        signature_mode = "embedded"

    # 9. Recuperar entidades faltantes del JSON
    entidades_brutas = json_data.get("detected_entities", {})

    issuing_cands = entidades_brutas.get("issuing_body_candidates", [])
    issuing_body = issuing_cands[0] if issuing_cands else "unknown"

    signers = entidades_brutas.get("signers_candidates", [])
    normative_references = entidades_brutas.get("normative_candidates", [])

    referenced_entities = {
        "persons": entidades_brutas.get("person_candidates", []),
        "academic_units": entidades_brutas.get("academic_unit_candidates", []),
        "careers": entidades_brutas.get("career_candidates", []),
        "courses": entidades_brutas.get("course_candidates", [])
    }
    
    # CONSTRUCCIÓN DEL DICCIONARIO CANÓNICO
    yaml_dict = {
        "document_id": json_data.get("document_id_hint", "unknown"),
        "source_pdf": json_data.get("source_pdf", "unknown"),
        "source_system": source_system,
        "document_type": document_type,
        "issuing_body": issuing_body,  # <-- CAMBIO
        "institution": "Universidad Nacional de Luján",
        "document_code": document_code,
        "document_number": document_number,
        "date_issued": date_issued,
        "year": year,
        "city": city,
        "has_annexes": has_annexes,
        "annex_count": annex_count,
        "has_signature_page": has_sig_page,
        "signature_mode": signature_mode,
        "signers": signers,  # <-- CAMBIO
        "referenced_entities": referenced_entities,  # <-- CAMBIO
        "normative_references": normative_references,  # <-- CAMBIO
        "auxiliary_codes": auxiliary_codes,
        "publication_notes": publication_notes,
        "extraction_version": "v1.4",
        "content_markdown": contenido_md 
    }

    return yaml_dict

def generar_documento_yaml_final(ruta_json, ruta_md):
    if not os.path.exists(ruta_json) or not os.path.exists(ruta_md):
        print(f"Error: No se encontraron los archivos base para {ruta_md}")
        return

    with open(ruta_json, 'r', encoding='utf-8') as f:
        json_data = json.load(f)

    with open(ruta_md, 'r', encoding='utf-8') as f:
        contenido_md = f.read()

    datos_completos = procesar_metadatos(json_data, contenido_md)

    # =========================================================================
    # NUEVA LÓGICA DE VALIDACIÓN Y DETECCIÓN DE ERRORES
    # =========================================================================
    campos_erroneos = []

    # 1. Campos simples que no deben ser vacíos ni "unknown"
    campos_basicos = [
        "document_id", "source_pdf", "source_system", "document_type", 
        "issuing_body", "document_code", "document_number", 
        "date_issued", "year", "city", "signature_mode"
    ]
    
    for campo in campos_basicos:
        valor = datos_completos.get(campo)
        if valor is None or str(valor).strip() == "" or str(valor).lower() == "unknown":
            campos_erroneos.append(campo)

    # 2. Validación específica de 'signers'
    # Debe haber mínimo 1, y ningún name o role debe ser "unknown" o vacío
    signers = datos_completos.get("signers", [])
    if not signers or not isinstance(signers, list):
        campos_erroneos.append("signers")
    else:
        for s in signers:
            if isinstance(s, dict):
                name = str(s.get("name", "")).lower()
                role = str(s.get("role", "")).lower()
                if name in ["unknown", ""]:
                    campos_erroneos.append("signers")
                    break
                if role in ["unknown", ""]:
                    campos_erroneos.append("role")
                    break
    # 3. Validación específica de 'auxiliary_codes'
    # Debe tener algo (no estar vacío ni poseer elementos "unknown")
    aux_codes = datos_completos.get("auxiliary_codes", [])
    if not aux_codes or not isinstance(aux_codes, list) or len(aux_codes) == 0:
        campos_erroneos.append("auxiliary_codes")
    else:
        if any(str(c).lower() in ["unknown", ""] for c in aux_codes):
            campos_erroneos.append("auxiliary_codes")

    # Si se detectaron fallos, se registran en docus_error.txt
    if campos_erroneos:
        nombre_documento = datos_completos.get("source_pdf", os.path.basename(ruta_md))
        # Modo 'a' abre el archivo para añadir líneas al final sin pisar lo anterior
        with open("docus_error.txt", "a", encoding="utf-8") as f_err:
            f_err.write(f"Documento: {nombre_documento} | Campos faltantes/erróneos: {', '.join(campos_erroneos)}\n")
        print(f"Aviso: El documento se marcó con errores en 'docus_error.txt' debido a: {', '.join(campos_erroneos)}")
    # =========================================================================

    nombre_base = os.path.splitext(os.path.basename(ruta_md))[0]
    ruta_salida = os.path.join(os.path.dirname(ruta_md), f"{nombre_base}_canonico.yaml")

    with open(ruta_salida, "w", encoding="utf-8") as f:
        yaml.dump(datos_completos, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    
    print(f"Éxito: Documento YAML consolidado generado en '{ruta_salida}'")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python post_procesador.py <archivo.json> <archivo.md>")
    else:
        ruta_json = sys.argv[1]
        ruta_md = sys.argv[2]
        generar_documento_yaml_final(ruta_json, ruta_md)
