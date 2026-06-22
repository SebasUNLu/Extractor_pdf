import collections
import os
import re

def analizar_errores_documentos_carpeta(ruta_carpeta):
    # Recorremos uno a uno los archivos dentro de la carpeta
    for nombre_archivo in os.listdir(ruta_carpeta):
        if nombre_archivo.lower().endswith('.txt'):
            
            print(f"\nLeyendo archivo: {nombre_archivo}")
            print("-" * 50)
            
            # Inicializamos los contadores ADENTRO del bucle para que se reinicien por cada archivo
            contador_tipos_error = collections.Counter()
            conteo_por_pdf = {}
            contador_errores_solitarios = collections.Counter()
            
            ruta_archivo = os.path.join(ruta_carpeta, nombre_archivo)
            
            try:
                with open(ruta_archivo, 'r', encoding='utf-8') as archivo:
                    contenido = archivo.read()
            except FileNotFoundError:
                print(f"No se encontró el archivo. Ruta buscada: {os.path.abspath(ruta_archivo)}")
                continue # Salta al siguiente archivo si hay error
            except Exception as e:
                print(f"Ocurrió un error al intentar leer {nombre_archivo}: {e}")
                continue

            # =====================================================================
            # INICIO DEL CÓDIGO INTACTO (Lógica de lectura de datos)
            # =====================================================================
            fragmentos = contenido.split("Documento: ")[1:]

            for fragmento in fragmentos:
                fragmento_limpio = fragmento.replace('\n', ' ').replace('\r', ' ')
                
                if "|" in fragmento_limpio:
                    partes = fragmento_limpio.split("|")
                    nombre_pdf = partes[0].strip()
                    
                    if "Campos faltantes/erróneos:" in partes[1]:
                        errores_str = partes[1].split("Campos faltantes/erróneos:")[1]
                        lista_errores = [e.strip() for e in errores_str.split(",") if e.strip()]
                        
                        contador_tipos_error.update(lista_errores)
                        conteo_por_pdf[nombre_pdf] = len(lista_errores)
                        
                        if len(lista_errores) == 1:
                            contador_errores_solitarios.update(lista_errores)
            # =====================================================================
            # FIN DEL CÓDIGO INTACTO
            # =====================================================================

            # Ordenamos los PDFs de mayor a menor cantidad de errores de ESTE archivo en particular
            top_pdfs = sorted(conteo_por_pdf.items(), key=lambda x: x[1], reverse=True)

            # Imprimimos los reportes aislados para el archivo recién analizado
            print("=== TIPOS DE ERROR MÁS FRECUENTES (EN TOTAL) ===")
            for error, cantidad in contador_tipos_error.most_common():
                print(f"- {error}: {cantidad} repeticiones")

            print("\n=== ERRORES ÚNICOS (APARECEN SOLOS EN EL PDF) ===")
            total_documentos_un_error = sum(contador_errores_solitarios.values())
            print(f"Total de documentos que tienen un único error: {total_documentos_un_error}")
            for error, cantidad in contador_errores_solitarios.most_common():
                print(f"- {error}: {cantidad} veces apareció como único fallo")

            print("\n=== TOP 10 PDFs CON MÁS ERRORES ===")
            for pdf, cantidad in top_pdfs[:10]:
                print(f"- {pdf}: {cantidad} errores")


def contar_documentos_agrupados(ruta_carpeta):
    extensiones_validas = {'.yaml', '.json', '.md'}
    documentos_unicos = set()
    
    total_archivos_validos = 0

    for directorio_raiz, carpetas, archivos in os.walk(ruta_carpeta):
        for archivo in archivos:
            nombre_base, extension = os.path.splitext(archivo)
            
            if extension.lower() in extensiones_validas:
                total_archivos_validos += 1
                
                coincidencia = re.search(r'\d+', nombre_base)
                
                if coincidencia:
                    identificador = coincidencia.group()
                    documentos_unicos.add(identificador)
                else:
                    documentos_unicos.add(nombre_base)

    print(f"Total de archivos sueltos procesados (yaml, json, md): {total_archivos_validos}")
    print("-" * 50)
    print(f"Total de documentos ÚNICOS (agrupados por su ID numérico): {len(documentos_unicos)}")


# ==========================================
# EJECUCIÓN (MENÚ INTERACTIVO)
# ==========================================

if __name__ == "__main__":
    CARPETA_INTERNA = 'resultados_extractor'
    CARPETA_EXTERNA = r"C:\Users\franc\Downloads\errores 15-6-26"

    print("=== SELECTOR DE CARPETA A ANALIZAR ===")
    print("1. Carpeta interna ('resultados_extractor')")
    print(f"2. Carpeta externa ({CARPETA_EXTERNA})")
    print("O ingresa directamente la ruta completa de otra carpeta.")
    
    eleccion = input("\nElige una opción (1, 2 o ruta completa): ").strip()

    # Determinamos la ruta final según la elección
    if eleccion == '1':
        ruta_elegida = CARPETA_INTERNA
    elif eleccion == '2':
        ruta_elegida = CARPETA_EXTERNA
    else:
        # Si ingresas cualquier otra cosa, asume que es una ruta manual y le quita posibles comillas
        ruta_elegida = eleccion.replace('"', '').replace("'", "")

    # Validamos que la ruta ingresada exista antes de avanzar
    if os.path.exists(ruta_elegida):
        if os.path.isdir(ruta_elegida):
            print(f"\nIniciando análisis en: {ruta_elegida}")
            analizar_errores_documentos_carpeta(ruta_elegida)
        else:
            print("\nError: La ruta proporcionada corresponde a un archivo específico, no a una carpeta.")
    else:
        print(f"\nError: La ruta '{ruta_elegida}' no existe o está mal escrita. Verifica e intenta nuevamente.")