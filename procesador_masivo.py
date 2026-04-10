# Script para procesar todos los PDFs de una carpeta en lote con manejo de errores y logs.

import os
import subprocess
import time
import logging

# Configuración del log de errores
logging.basicConfig(
    filename='errores_extraccion.log',
    level=logging.ERROR,
    format='%(asctime)s - Archivo: %(message)s'
)

def procesar_carpeta():
    # Nombre de tu script de extracción (asegúrate de que coincida)
    script_extractor = "script_extractor.py"
    
    # Obtener lista de archivos PDF en la carpeta actual
    archivos = [f for f in os.listdir('.') if f.lower().endswith('.pdf')]
    
    if not archivos:
        print("No se encontraron archivos PDF en esta carpeta.")
        return

    print(f"--- Se encontraron {len(archivos)} archivos. Iniciando proceso masivo ---")
    
    exitos = 0
    errores = 0

    for archivo in archivos:
        print(f"Procesando: {archivo}...", end="\r")
        
        try:
            # Ejecutamos el script anterior pasando el archivo como argumento
            # check=True hace que lance una excepción si el script falla
            subprocess.run(["python", script_extractor, archivo], check=True, capture_output=True)
            exitos += 1
            
        except subprocess.CalledProcessError as e:
            # Capturamos el error específico del script
            error_msg = f"{archivo} | Error: {e.stderr.decode().strip()}"
            logging.error(error_msg)
            print(f"\n[ERROR] Falló la extracción de: {archivo} (ver log)")
            errores += 1
            
        except Exception as e:
            # Capturamos cualquier otro error inesperado (permisos, etc.)
            logging.error(f"{archivo} | Error inesperado: {str(e)}")
            print(f"\n[ERROR CRÍTICO] en {archivo}")
            errores += 1

    print(f"\n\n--- Proceso finalizado ---")
    print(f"Exitosos: {exitos}")
    print(f"Fallidos: {errores}")
    if errores > 0:
        print("Revisa 'errores_extraccion.log' para más detalles.")

if __name__ == "__main__":
    procesar_carpeta()