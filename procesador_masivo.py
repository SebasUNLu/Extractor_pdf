# Script para procesar todos los PDFs de una carpeta en lote con manejo de errores y logs.

import os
import subprocess
import time
import logging
import sys
import shutil

# Configuración del log de errores
logging.basicConfig(
    filename='errores_extraccion.log',
    level=logging.ERROR,
    format='%(asctime)s - Archivo: %(message)s'
)

def procesar_carpeta(ruta_destino):
    # Nombre del script de extracción
    script_extractor = "script_extractor.py"
    
    # Validar que la ruta existe
    if not os.path.exists(ruta_destino):
        print(f"Error: La ruta '{ruta_destino}' no existe.")
        return

    # Crear carpeta de resultados donde están los scripts
    carpeta_resultados = os.path.join(os.getcwd(), "resultados_extractor")
    if not os.path.exists(carpeta_resultados):
        os.makedirs(carpeta_resultados)
    
    # Obtener lista de archivos PDF en la ruta especificada
    archivos = [f for f in os.listdir(ruta_destino) if f.lower().endswith('.pdf')]
    
    if not archivos:
        print(f"No se encontraron archivos PDF en '{ruta_destino}'.")
        return

    print(f"--- Se encontraron {len(archivos)} archivos. Iniciando proceso masivo ---")
    
    exitos = 0
    errores = 0

    for archivo in archivos:
        ruta_completa_pdf = os.path.join(ruta_destino, archivo)
        print(f"Procesando: {archivo}...", end="\r")
        
        try:
            # Ejecutamos el extractor
            # Nota: El extractor genera el .md y el .json en la carpeta donde se ejecuta el script
            subprocess.run(["python", script_extractor, ruta_completa_pdf], check=True, capture_output=True)
            
            # Identificar el nombre del archivo Markdown generado
            nombre_md = f"{os.path.splitext(archivo)[0]}_jerarquizado.md"
            
            # Si el archivo se generó, lo movemos a la carpeta de resultados
            if os.path.exists(nombre_md):
                shutil.move(nombre_md, os.path.join(carpeta_resultados, nombre_md))
            
            # Identificar el nombre del archivo JSON generado
            nombre_json = f"{os.path.splitext(archivo)[0]}_auxiliar.json"
            
            # Si el archivo JSON se generó, lo movemos a la misma carpeta de resultados
            if os.path.exists(nombre_json):
                shutil.move(nombre_json, os.path.join(carpeta_resultados, nombre_json))
                
            exitos += 1
            
        except subprocess.CalledProcessError as e:
            # Capturamos el error específico del script
            error_msg = f"{archivo} | Error: {e.stderr.decode().strip()}"
            logging.error(error_msg)
            print(f"\n[ERROR] Falló la extracción de: {archivo} (ver log)")
            errores += 1
            
        except Exception as e:
            # Capturamos cualquier otro error inesperado
            logging.error(f"{archivo} | Error inesperado: {str(e)}")
            print(f"\n[ERROR CRÍTICO] en {archivo}")
            errores += 1

    print(f"\n\n--- Proceso finalizado ---")
    print(f"Exitosos: {exitos}")
    print(f"Fallidos: {errores}")
    print(f"Resultados guardados en: {carpeta_resultados}")
    if errores > 0:
        print("Revisa 'errores_extraccion.log' para más detalles.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python procesador_masivo.py <ruta_de_la_carpeta_con_pdfs>")
    else:
        procesar_carpeta(sys.argv[1])