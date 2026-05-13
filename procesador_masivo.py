# Script para procesar todos los PDFs de una carpeta en lote con manejo de errores y logs.

import os
import subprocess
import logging
import sys

# Configuración del log de errores
logging.basicConfig(
    filename='errores_extraccion.log',
    level=logging.ERROR,
    format='%(asctime)s - Archivo: %(message)s'
)

def procesar_carpeta(ruta_destino):
    # Definir las rutas ABSOLUTAS de los scripts para no perderlos de vista
    directorio_actual = os.getcwd()
    script_extractor = os.path.abspath("script_extractor.py")
    script_post_procesador = os.path.abspath("post_procesador.py")
    
    # Validar que la carpeta con PDFs existe
    if not os.path.exists(ruta_destino):
        print(f"Error: La ruta '{ruta_destino}' no existe.")
        return

    # Crear carpeta de resultados y obtener su ruta absoluta
    carpeta_resultados = os.path.abspath(os.path.join(directorio_actual, "resultados_extractor"))
    if not os.path.exists(carpeta_resultados):
        os.makedirs(carpeta_resultados)
    
    # Obtener lista de archivos PDF
    ruta_origen_abs = os.path.abspath(ruta_destino)
    archivos = [f for f in os.listdir(ruta_origen_abs) if f.lower().endswith('.pdf')]
    
    if not archivos:
        print(f"No se encontraron archivos PDF en '{ruta_destino}'.")
        return

    print(f"--- Se encontraron {len(archivos)} archivos. Iniciando proceso masivo ---")
    
    exitos = 0
    errores = 0

    for archivo in archivos:
        # Usamos la ruta absoluta al PDF para que el extractor lo encuentre sin problemas
        ruta_completa_pdf = os.path.join(ruta_origen_abs, archivo)
        print(f"Procesando: {archivo}...".ljust(60), end="\r")
        
        try:
            # ==========================================
            # FASE 1: EXTRACCIÓN (Genera MD y JSON nativamente en la carpeta final)
            # ==========================================
            # Al pasarle cwd=carpeta_resultados, el script se ejecuta "allí dentro" 
            # y los archivos se guardan solos en el directorio correcto.
            subprocess.run(
                ["python", script_extractor, ruta_completa_pdf], 
                cwd=carpeta_resultados, 
                check=True, 
                capture_output=True,
                text=True
            )
            
            # Nombres esperados de los archivos generados
            nombre_base = os.path.splitext(archivo)[0]
            nombre_md = f"{nombre_base}.md"
            nombre_json = f"{nombre_base}.json"
            
            # ==========================================
            # FASE 2: POST-PROCESAMIENTO (Genera MD Canónico con YAML)
            # ==========================================
            # Verificamos que la Fase 1 haya creado los archivos en la carpeta de resultados
            if os.path.exists(os.path.join(carpeta_resultados, nombre_md)) and os.path.exists(os.path.join(carpeta_resultados, nombre_json)):
                # Ejecutamos el post-procesador también desde adentro de la carpeta
                subprocess.run(
                    ["python", script_post_procesador, nombre_json, nombre_md], 
                    cwd=carpeta_resultados,
                    check=True, 
                    capture_output=True,
                    text=True
                )
                exitos += 1
            else:
                raise Exception("El extractor no generó los archivos MD o JSON esperados.")
            
        except subprocess.CalledProcessError as e:
            # Si falla alguno de los dos scripts (ej: falta pip install pyyaml o el PDF está roto)
            error_msg = f"{archivo} | Error del script: {e.stderr.strip()}"
            logging.error(error_msg)
            print(f"\n[ERROR] Falló el procesamiento de: {archivo}. Revisa errores_extraccion.log")
            errores += 1
            
        except Exception as e:
            # Cualquier otro error del sistema
            logging.error(f"{archivo} | Error inesperado: {str(e)}")
            print(f"\n[ERROR CRÍTICO] en {archivo}: {str(e)}")
            errores += 1

    print(f"\n\n--- Proceso finalizado ---".ljust(60))
    print(f"Exitosos: {exitos}")
    print(f"Fallidos: {errores}")
    print(f"Resultados guardados en: {carpeta_resultados}")
    if errores > 0:
        print("Revisa el archivo 'errores_extraccion.log' para más detalles.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python procesador_masivo.py <ruta_de_la_carpeta_con_pdfs>")
    else:
        procesar_carpeta(sys.argv[1])