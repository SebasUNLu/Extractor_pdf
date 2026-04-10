import fitz
import pandas as pd
import sys
import os
import time
import re
import io

def aplanar_y_limpiar_avanzado(ruta_entrada):
    """
    Limpia el PDF de estructuras fantasmas y normaliza el texto.
    Retorna un objeto BytesIO con el PDF procesado.
    """
    if not os.path.exists(ruta_entrada):
        print(f"Error: El archivo '{ruta_entrada}' no existe.")
        return None

    doc_original = fitz.open(ruta_entrada)
    doc_limpio = fitz.open()

    for i, pagina in enumerate(doc_original):
        rect = pagina.rect
        nueva_pag = doc_limpio.new_page(width=rect.width, height=rect.height)
        
        # 1. Transferencia de Texto (Normalización)
        diccionario_texto = pagina.get_text("dict")
        for bloque in diccionario_texto["blocks"]:
            if bloque["type"] == 0:
                for linea in bloque["lines"]:
                    for span in linea["spans"]:
                        nueva_pag.insert_text(
                            span["origin"], 
                            span["text"], 
                            fontsize=span["size"],
                            fontname="helv",
                            color=(0,0,0)
                        )
        
        # 2. Filtrado de Gráficos
        tabs = pagina.find_tables()
        areas_a_ignorar = []
        
        for t in tabs.tables:
            res = t.extract()
            if not res: continue
            
            celdas_totales = len(res) * len(res[0])
            celdas_con_datos = sum(1 for fila in res for celda in fila if str(celda).strip())
            
            if (celdas_con_datos / celdas_totales) < 0.30:
                areas_a_ignorar.append(t.bbox)

        # 3. Dibujado Selectivo
        dibujos = pagina.get_drawings()
        for d in dibujos:
            for item in d["items"]:
                rect_item = d["rect"]
                if any(rect_item.intersects(area) for area in areas_a_ignorar):
                    continue
                
                if item[0] == "l":
                    p1, p2 = item[1], item[2]
                    if abs(p1.x - p2.x) > 10 or abs(p1.y - p2.y) > 10:
                        nueva_pag.draw_line(p1, p2, color=(0,0,0), width=0.5)
                elif item[0] == "re":
                    r = item[1]
                    if r.width > 15 and r.height > 15:
                        nueva_pag.draw_rect(r, color=(0,0,0), width=0.5)

    # Guardar en buffer en lugar de disco
    buffer_pdf = io.BytesIO()
    doc_limpio.save(buffer_pdf, garbage=4, deflate=True, clean=True)
    
    doc_original.close()
    doc_limpio.close()
    
    buffer_pdf.seek(0)
    print(f"--- Fase 1: PDF Aplanado y Limpio en Memoria ---")
    return buffer_pdf

def extraer_a_markdown_directo(buffer_pdf, nombre_original):
    """
    Recibe el buffer del PDF limpio y realiza la extracción a Markdown.
    """
    print(f"--- Fase 2: Iniciando Extracción a Markdown: {nombre_original} ---")
    doc = fitz.open("pdf", buffer_pdf)
    contenido_final = []

    patron_alfabetico = re.compile(r'^[a-zA-Z]\.\s')

    for i, pagina in enumerate(doc):
        cp = pagina.cropbox
        alto = cp.height
        margen_superior = cp.y0 + (alto * 0.20)
        margen_inferior = cp.y0 + (alto * 0.92)

        tabs = pagina.find_tables(strategy="lines", snap_tolerance=4, intersection_tolerance=3)
        areas_tablas = [t.bbox for t in tabs.tables]

        bloques = pagina.get_text("dict")["blocks"]
        bloques.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))

        tablas_procesadas = []
        
        for b in bloques:
            if b["type"] == 0: 
                x0, y0, x1, y1 = b["bbox"]
                centro_y = (y0 + y1) / 2
                
                if centro_y < margen_superior or centro_y > margen_inferior:
                    continue

                esta_en_tabla = False
                for idx_tab, area in enumerate(areas_tablas):
                    if x0 >= area[0]-3 and y0 >= area[1]-3 and x1 <= area[2]+3 and y1 <= area[3]+3:
                        if idx_tab not in tablas_procesadas:
                            df = tabs.tables[idx_tab].to_pandas().fillna("")
                            if not (df.to_string().strip() == "" or len(df.columns) < 2):
                                try:
                                    markdown_table = "\n" + df.to_markdown(index=False) + "\n"
                                except:
                                    markdown_table = "\n" + df.to_csv(sep="|", index=False) + "\n"
                                contenido_final.append(markdown_table)
                            tablas_procesadas.append(idx_tab)
                        esta_en_tabla = True
                        break
                
                if not esta_en_tabla:
                    texto_acumulado = ""
                    lineas = b["lines"]
                    
                    for idx, linea in enumerate(lineas):
                        contenido_linea = " ".join([s["text"].strip() for s in linea["spans"] if s["text"].strip()])
                        
                        if not contenido_linea:
                            continue

                        linea_limpia = contenido_linea.lstrip()
                        
                        starts_with_bullet = any(linea_limpia.startswith(char) for char in ['·', '●', '•'])
                        starts_with_alpha = bool(patron_alfabetico.match(linea_limpia))
                        
                        if starts_with_bullet or starts_with_alpha:
                            if starts_with_bullet:
                                for char in ['·', '●', '•']:
                                    linea_limpia = linea_limpia.replace(char, '', 1).strip()
                            
                            prefijo = "\n- " if texto_acumulado else "- "
                            texto_acumulado += prefijo + linea_limpia
                        
                        else:
                            if texto_acumulado:
                                ultimo_char = texto_acumulado.strip()[-1] if texto_acumulado.strip() else ""
                                
                                if ultimo_char in ['.', '!', '?'] and linea_limpia[0].isupper():
                                    texto_acumulado += "\n\n" + linea_limpia
                                else:
                                    if texto_acumulado.endswith("- ") or texto_acumulado.split('\n')[-1].startswith("- "):
                                        texto_acumulado += " " + linea_limpia
                                    else:
                                        texto_acumulado += " " + linea_limpia
                            else:
                                texto_acumulado = linea_limpia
                    
                    if texto_acumulado:
                        limpio = re.sub(r' +', ' ', texto_acumulado)
                        contenido_final.append(limpio.strip())

        contenido_final.append("\n\n---\n\n")

    doc.close()
    nombre_salida = f"{os.path.splitext(nombre_original)[0]}_procesado.md"
    with open(nombre_salida, "w", encoding="utf-8") as f:
        f.write("\n\n".join(contenido_final))
    
    return nombre_salida

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python script_unificado.py archivo.pdf")
    else:
        ruta_archivo = sys.argv[1]
        inicio = time.time()
        
        # Paso 1: Aplanar en memoria
        pdf_limpio_buffer = aplanar_y_limpiar_avanzado(ruta_archivo)
        
        if pdf_limpio_buffer:
            # Paso 2: Extraer del buffer
            archivo_resultado = extraer_a_markdown_directo(pdf_limpio_buffer, os.path.basename(ruta_archivo))
            fin = time.time()
            
            print(f"\nProceso total terminado en {fin - inicio:.2f} segundos.")
            print(f"Archivo Markdown generado: {archivo_resultado}")