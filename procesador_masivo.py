# Script para procesar todos los PDFs de una carpeta en lote con manejo de errores y logs.

import os
import subprocess
import logging
import sys
import random
import concurrent.futures

# Configuración del log de errores
logging.basicConfig(
    filename='errores_extraccion.log',
    level=logging.ERROR,
    format='%(asctime)s - Archivo: %(message)s'
)

def procesar_un_archivo(archivo, ruta_origen_abs, carpeta_resultados, script_extractor, script_post_procesador):
    """Procesa un único PDF con la misma lógica del flujo actual."""
    ruta_completa_pdf = os.path.join(ruta_origen_abs, archivo)

    try:
        subprocess.run(
            ["python", script_extractor, ruta_completa_pdf],
            cwd=carpeta_resultados,
            check=True,
            capture_output=True,
            text=True
        )

        nombre_base = os.path.splitext(archivo)[0]
        nombre_md = f"{nombre_base}.md"
        nombre_json = f"{nombre_base}.json"

        if os.path.exists(os.path.join(carpeta_resultados, nombre_md)) and os.path.exists(os.path.join(carpeta_resultados, nombre_json)):
            subprocess.run(
                ["python", script_post_procesador, nombre_json, nombre_md],
                cwd=carpeta_resultados,
                check=True,
                capture_output=True,
                text=True
            )
            return "EXITO", archivo, None
        else:
            return "ERROR", archivo, "El extractor no generó los archivos MD o JSON esperados."

    except subprocess.CalledProcessError as e:
        error_msg = f"{archivo} | Error del script: {e.stderr.strip()}"
        return "ERROR", archivo, error_msg
    except Exception as e:
        error_msg = f"{archivo} | Error inesperado: {str(e)}"
        return "ERROR", archivo, error_msg


def procesar_carpeta(ruta_destino, cantidad_aleatoria=None):
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

    # Lógica para la selección aleatoria de X archivos
    if cantidad_aleatoria is not None:
        if cantidad_aleatoria >= len(archivos):
            print(f"Aviso: Solicitaste {cantidad_aleatoria} archivos, pero la carpeta solo contiene {len(archivos)}. Se procesarán todos.")
        else:
            archivos = random.sample(archivos, cantidad_aleatoria)
            print(f"🎲 Selección aleatoria activa: Se eligieron {cantidad_aleatoria} PDFs al azar.")

    print(f"--- Se encontraron {len(archivos)} archivos. Iniciando proceso masivo ---")
    
    exitos = 0
    errores = 0

    if len(archivos) > 1:
        max_workers = max(1, min(len(archivos), (os.cpu_count() or 1) - 1))
        print(f"--- Iniciando procesamiento multinúcleo con {max_workers} workers ---")

        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
            tareas = {
                executor.submit(
                    procesar_un_archivo,
                    archivo,
                    ruta_origen_abs,
                    carpeta_resultados,
                    script_extractor,
                    script_post_procesador
                ): archivo for archivo in archivos
            }

            for indice, futuro in enumerate(concurrent.futures.as_completed(tareas), start=1):
                tipo_res, archivo_procesado, detalle = futuro.result()
                porcentaje = (indice / len(archivos)) * 100

                if tipo_res == "EXITO":
                    exitos += 1
                    print(f"[{indice}/{len(archivos)} - {porcentaje:.1f}%] OK: {archivo_procesado}")
                else:
                    errores += 1
                    logging.error(detalle)
                    print(f"\n[ERROR] Falló el procesamiento de: {archivo_procesado}. Revisa errores_extraccion.log")
    else:
        for archivo in archivos:
            print(f"Procesando: {archivo}...".ljust(60), end="\r")
            tipo_res, archivo_procesado, detalle = procesar_un_archivo(
                archivo,
                ruta_origen_abs,
                carpeta_resultados,
                script_extractor,
                script_post_procesador
            )

            if tipo_res == "EXITO":
                exitos += 1
            else:
                errores += 1
                logging.error(detalle)
                print(f"\n[ERROR] Falló el procesamiento de: {archivo_procesado}. Revisa errores_extraccion.log")

    print(f"\n\n--- Proceso finalizado ---".ljust(60))
    print(f"Exitosos: {exitos}")
    print(f"Fallidos: {errores}")
    print(f"Resultados guardados en: {carpeta_resultados}")
    if errores > 0:
        print("Revisa el archivo 'errores_extraccion.log' para más detalles.")

if __name__ == "__main__":
    # Ahora la validación contempla que el segundo parámetro es opcional
    if len(sys.argv) < 2:
        print("Uso: python procesador_masivo.py <ruta_de_la_carpeta_con_pdfs> [cantidad_aleatoria_X]")
    else:
        ruta_carpeta = sys.argv[1]
        x_cantidad = None
        
        # Comprobamos si se pasó el entero X secundario
        if len(sys.argv) > 2:
            try:
                x_cantidad = int(sys.argv[2])
                if x_cantidad <= 0:
                    print("Error: El segundo parámetro (X) debe ser un número entero mayor a 0.")
                    sys.exit(1)
            except ValueError:
                print("Error: El segundo parámetro (X) debe ser un número entero válido.")
                sys.exit(1)
                
        procesar_carpeta(ruta_carpeta, x_cantidad)