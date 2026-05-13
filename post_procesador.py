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
    # 1. Definir el tipo de documento
    doc_id_hint = json_data.get("document_id_hint", "unknown")
    if "res_" in doc_id_hint:
        document_type = "resolucion"
    elif "disp_" in doc_id_hint:
        document_type = "disposicion"
    else:
        document_type = "unknown"

    # 2. Extraer Código y Número del documento principal
    candidates = json_data.get("detected_entities", {}).get("document_code_candidates", [])
    document_code = "unknown"
    document_number = "unknown"
    if candidates:
        # Ejemplo esperado: "RESOLUCIÓN RESHCS-LUJ: 0000206-24"
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

    # 5. Resolver Anexos (Cruzando JSON con el Markdown)
    has_annexes = json_data.get("global_hints", {}).get("has_annexes", False)
    # Contamos exactamente cuántas veces aparece un título de anexo en el MD
    annex_count = len(re.findall(r'^#\s*(ANEXO|Anexo)', contenido_md, re.MULTILINE))
    if has_annexes and annex_count == 0:
        annex_count = 1

    # 6. Códigos Auxiliares
    # CAMBIO: Ahora los tomamos directamente del array 'auxiliary_codes' que generó el extractor
    auxiliary_codes = json_data.get("global_hints", {}).get("auxiliary_codes", [])

    # 7. Notas de publicación (Disclaimer web)
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

    # CONSTRUCCIÓN DEL DICCIONARIO CANÓNICO
    yaml_dict = {
        "document_id": doc_id_hint,
        "source_pdf": json_data.get("source_pdf", "unknown"),
        "source_system": source_system,
        "document_type": document_type,
        "issuing_body": "unknown",
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
        "signers": [], 
        "referenced_entities": {
            "persons": [],
            "academic_units": [],
            "careers": [],
            "courses": []
        },
        "normative_references": [],
        "auxiliary_codes": auxiliary_codes,
        "publication_notes": publication_notes,
        "extraction_version": "v1.2", # Versión actualizada
        "content_markdown": contenido_md 
    }

    return yaml_dict

def generar_documento_yaml_final(ruta_json, ruta_md):
    # Validar archivos
    if not os.path.exists(ruta_json) or not os.path.exists(ruta_md):
        print(f"Error: No se encontraron los archivos base para {ruta_md}")
        return

    # Leer JSON
    with open(ruta_json, 'r', encoding='utf-8') as f:
        json_data = json.load(f)

    # Leer Markdown
    with open(ruta_md, 'r', encoding='utf-8') as f:
        contenido_md = f.read()

    # Generar la metadata consolidada con el contenido incluido
    datos_completos = procesar_metadatos(json_data, contenido_md)

    # Definir nombre de salida .yaml
    nombre_base = os.path.splitext(os.path.basename(ruta_md))[0].replace("_jerarquizado", "")
    ruta_salida = os.path.join(os.path.dirname(ruta_md), f"{nombre_base}_canonico.yaml")

    # Guardar el archivo YAML
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