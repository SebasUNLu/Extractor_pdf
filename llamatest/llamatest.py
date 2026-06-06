import os
import sys
import json
import argparse
from pathlib import Path
from llama_parse import LlamaParse

# === AQUÍ ESTÁ EL CAMBIO CRUCIAL ===
from dotenv import load_dotenv
load_dotenv()  # Esto busca el archivo .env en la misma carpeta y carga sus variables
# ===================================

# =====================================================================
# CONFIGURACIÓN DE INSTRUCCIONES EN BASE A TU TUTORIAL DE MARKDOWN
# =====================================================================
# Pasamos las directrices del PDF directamente al motor visual de LlamaParse
INSTRUCCIONES_JERARQUIZACION = """
Eres un extractor de documentos experto. Tu objetivo es convertir este PDF a un Markdown limpio y perfectamente estructurado siguiendo estas reglas estrictas:
1. ESTRUCTURA: Usa '#' solo para el título principal del documento. Usa '##' para los títulos de las secciones principales (Artículos, Capítulos) y '###' para las subsecciones.
2. LIMPIEZA: Elimina los números de página, los nombres del documento que aparecen en el margen superior y cualquier pie de página repetitivo.
3. TABLAS: Transforma cada tabla en una tabla de Markdown limpia. No uses código HTML para las tablas.
4. DESTACADOS: Si encuentras un texto que actúa como advertencia, nota importante o resolución final, encuadrado en un bloque de cita de Markdown (>).
5. MANTÉN EL ORDEN: No saltes ningún párrafo ni resumas el contenido. Transcribe todo el texto relevante.
"""

# =====================================================================
# PROCESAMIENTO POR LOTE (SÓLO LLAMAPARSE)
# =====================================================================
def procesar_carpeta_solo_llamaparse(ruta_carpeta: str):
    directorio = Path(ruta_carpeta)
    
    if not directorio.exists() or not directorio.is_dir():
        print(f"[FATAL] La ruta '{ruta_carpeta}' no es una carpeta válida.")
        sys.exit(1)
        
    archivos_pdf = list(directorio.glob("*.pdf"))
    if not archivos_pdf:
        print(f"[AVISO] No se encontraron archivos .pdf en '{directorio.resolve()}'.")
        return

    api_key_llama = os.environ.get("LLAMA_CLOUD_API_KEY")
    if not api_key_llama:
        print("[FATAL] Falta la variable de entorno 'LLAMA_CLOUD_API_KEY'.")
        sys.exit(1)

    # Inicializamos LlamaParse configurando las instrucciones del tutorial
    parser = LlamaParse(
        api_key=api_key_llama,
        result_type="markdown",
        parsing_instruction=INSTRUCCIONES_JERARQUIZACION,
        verbose=False
    )

    print(f"================================================================")
    print(f"Iniciando procesamiento solo con LlamaParse")
    print(f"Carpeta: {directorio.resolve()}")
    print(f"Total de archivos PDF: {len(archivos_pdf)}")
    print(f"================================================================")

    exitos = 0
    errores = 0

    for i, ruta_pdf in enumerate(archivos_pdf, start=1):
        nombre_base = ruta_pdf.stem
        archivo_md_salida = directorio / f"{nombre_base}.md"
        archivo_json_salida = directorio / f"{nombre_base}.json"

        print(f"\n[{i}/{len(archivos_pdf)}] Procesando: {ruta_pdf.name}")

        # Control para evitar reprocesar si ya existen las salidas
        if archivo_md_salida.exists() and archivo_json_salida.exists():
            print(" -> [OMITIDO] Las salidas .md y .json ya existen.")
            exitos += 1
            continue

        try:
            # Llamada única: Extrae toda la metadata y el markdown estructurado en un solo viaje
            json_result = parser.get_json_result(str(ruta_pdf))
            
            # 1. Guardar el JSON nativo de LlamaParse (contiene hojas, tablas, bloques de texto)
            with open(archivo_json_salida, "w", encoding="utf-8") as f:
                json.dump(json_result, f, indent=4, ensure_ascii=False)
            
            # 2. Extraer el Markdown jerarquizado que LlamaParse procesó bajo nuestra instrucción
            # Generalmente viene consolidado en el primer elemento de la lista devuelta
            if json_result and "markdown" in json_result[0]:
                markdown_final = json_result[0]["markdown"]
            else:
                # Reconstrucción de respaldo página por página si no viene consolidado arriba
                paginas = json_result[0].get("pages", [])
                markdown_final = "\n\n".join([pag.get("markdown", pag.get("text", "")) for pag in paginas])

            # Guardar el archivo Markdown
            with open(archivo_md_salida, "w", encoding="utf-8") as f:
                f.write(markdown_final)

            print(f" -> [ÉXITO] Archivos creados: {nombre_base}.md y {nombre_base}.json")
            exitos += 1

        except Exception as e:
            print(f" -> [ERROR] No se pudo procesar el archivo debido a: {e}")
            errores += 1

    print(f"\n================================================================")
    print(f"Procesamiento Finalizado:")
    print(f" Completados con éxito: {exitos}")
    print(f" Con errores técnicos:  {errores}")
    print(f"================================================================")

# =====================================================================
# ENTRADA DE ARGUMENTOS POR CONSOLA
# =====================================================================
if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(
        description="Extractor normativo optimizado: Genera MD y JSON usando exclusivamente la API de LlamaParse."
    )
    arg_parser.add_argument(
        "carpeta",
        type=str,
        help="Ruta del directorio donde están los archivos PDF a procesar."
    )
    
    args = arg_parser.parse_args()
    procesar_carpeta_solo_llamaparse(args.carpeta)