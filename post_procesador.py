import json
import os
import sys
import re
import yaml # Requiere instalar la librería: pip install pyyaml

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
    document_code = "unknown"
    document_number = "unknown"
    if candidates:
        partes = candidates[0].split(":")
        if len(partes) >= 2:
            document_code = partes[0].split(" ")[-1].strip()
            document_number = partes[1].strip()

    # 3. Normalizar Fecha y Año
    date_cands = json_data.get("detected_entities", {}).get("date_candidates", [])
    date_issued = date_cands[0] if date_cands else "unknown"
    try:
        year = int(date_issued.split("-")[0]) if date_issued != "unknown" else "unknown"
    except ValueError:
        year = "unknown"

    # 4. Normalizar Ciudad
    city_cands = json_data.get("detected_entities", {}).get("city_candidates", [])
    city = city_cands[0].capitalize() if city_cands else "unknown"

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
                if name in ["unknown", ""] or role in ["unknown", ""]:
                    campos_erroneos.append("signers")
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