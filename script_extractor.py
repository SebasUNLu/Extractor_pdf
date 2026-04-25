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

    buffer_pdf = io.BytesIO()
    doc_limpio.save(buffer_pdf, garbage=4, deflate=True, clean=True)
    doc_original.close()
    doc_limpio.close()
    buffer_pdf.seek(0)
    print(f"--- Fase 1: PDF Aplanado y Limpio en Memoria ---")
    return buffer_pdf

def extraer_a_markdown_directo(buffer_pdf, nombre_original):
    """
    Realiza la extracción jerarquizada a Markdown procesando bloques individuales.
    """
    print(f"--- Fase 2: Iniciando Extracción (Bloques Originales): {nombre_original} ---")
    doc = fitz.open("pdf", buffer_pdf)
    contenido_final = []

    # Patrones para jerarquización
    patron_alfabetico = re.compile(r'^[a-zA-Z]\.\s')
    patron_visto = re.compile(r'^(VISTO|Visto)[:\s]*')
    patron_considerando = re.compile(r'^(CONSIDERANDO|Considerando)[:\s]*')
    patron_resuelve = re.compile(r'^(R\s*E\s*S\s*U\s*E\s*L\s*V\s*E|D\s*I\s*S\s*P\s*O\s*N\s*E|D\s*E\s*C\s*R\s*E\s*T\s*A)[:\s]*', re.IGNORECASE)
    patron_articulo = re.compile(r'^(ART[IÍ]CULO|Art[ií]culo)\s*(\d+)([:\s\.]*)')
    patron_anexo = re.compile(r'^(ANEXO|Anexo)\s*(\d+|[IVXLCDM]+)?')
    patron_firma_keywords = re.compile(r'(Dr\.|Dra\.|Prof\.|Lic\.|Mg\.|Secretario|Directivo|Secretaria|Presidente|Director|Directora|Decano|Vicedecano)', re.IGNORECASE)
    patron_folio = re.compile(r'^\s*-\s*\d+\s*-\s*$')
    patron_titulo_norma = re.compile(r'(DISPOSICIÓN|RESOLUCIÓN)\s+([A-Z\-]+):\s*(\d+)-(\d+)', re.IGNORECASE)
    titulo_encontrado = None
    indice_titulo = -1
    
    for i, pagina in enumerate(doc):
        firmas_detectadas = False
        
        cp = pagina.cropbox
        alto = cp.height

        rect_pag = pagina.rect
        ancho_pag = rect_pag.width
        alto_pag = rect_pag.height

        margen_superior = cp.y0 + (alto * 0.20)
        margen_inferior = cp.y0 + (alto * 0.96)

        tabs = pagina.find_tables(strategy="lines", snap_tolerance=4)
        areas_tablas = [t.bbox for t in tabs.tables]

        bloques = pagina.get_text("dict")["blocks"]
        # Ordenamos solo para asegurar lectura natural de arriba hacia abajo
        bloques.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))

        tablas_procesadas = []

        indices_ignorados = set()
        
        for idx, b in enumerate(bloques):
            if b["type"] != 0: continue
            if idx in indices_ignorados:
                continue
            
            x0, y0, x1, y1 = b["bbox"]
            centro_y = (y0 + y1) / 2
            ancho_bloque = x1 - x0

            # Filtro de márgenes (Header/Footer)
            if not (margen_superior <= centro_y <= margen_inferior):
                continue

            # Verificación de Tablas
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
                lineas_bloque = []
                es_bloque_firma = False
                es_negrita = False
                
                # --- DETECCIÓN DE NEGRITA (Bold) ---
                if b["lines"] and b["lines"][0]["spans"]:
                    # Verificamos si el primer span tiene el bit 4 activo (negrita)
                    if b["lines"][0]["spans"][0]["flags"] & 16:
                        es_negrita = True

                # --- LÓGICA DE DETECCIÓN DE FIRMA ---
                # 1. ¿Ocupa poco ancho? (< 25%)
                es_bloque_angosto = (ancho_bloque < ancho_pag * 0.25)
                # 2. ¿Tiene más de una línea?
                tiene_varias_lineas = len(b["lines"]) > 1
                # Si cumple alguna, verificamos si hay un bloque "pegado" abajo
                es_posible_firma = es_bloque_angosto and tiene_varias_lineas
                
                for linea in b["lines"]:
                    txt = " ".join([s["text"].strip() for s in linea["spans"] if s["text"].strip()])
                    if txt and "///" not in txt and not patron_folio.match(txt):
                        lineas_bloque.append(txt)
                    
                if es_posible_firma and lineas_bloque:
                    # 3. ¿Tiene un bloque justo abajo? (Posible Departamento/Cargo)
                    cursor_idx = idx + 1
                    while cursor_idx < len(bloques):
                        sig = bloques[cursor_idx]
                        dist_v = sig["bbox"][1] - y1 # Distancia entre fondo actual y techo siguiente
                        
                        # Si el siguiente bloque está a menos de 15 pts y no es muy ancho
                        if 0 <= dist_v < 15 and (sig["bbox"][2] - sig["bbox"][0]) < ancho_pag * 0.40:
                            for l_sig in sig["lines"]:
                                txt_sig = " ".join([s["text"].strip() for s in l_sig["spans"] if s["text"].strip()])
                                if txt_sig: lineas_a_procesar.append(txt_sig)
                            
                            indices_ignorados.add(cursor_idx)
                            y1 = sig["bbox"][3] # Actualizamos el límite inferior para el siguiente paso del while
                            cursor_idx += 1
                        else:
                            break

                    # Validación de keywords para confirmar que es una firma
                    texto_completo_firma = " ".join(lineas_bloque)
                    if patron_firma_keywords.search(texto_completo_firma):
                        if not firmas_detectadas:
                            contenido_final.append("## Firmas")
                            firmas_detectadas = True
                        
                        firma_unida = " — ".join(lineas_bloque)
                        contenido_final.append("- " + firma_unida)
                        continue

                if not lineas_bloque: continue

                # NUEVA LÓGICA DE FIRMAS (Preguntas de validación)
                # 1. ¿Coincide con la posición de un bloque firma? (Parte inferior y derecha)
                es_posicion_firma = (x0 > ancho_pag * 0.40)
                if es_posicion_firma:
                    print("bloque firma")
                
                # 2. ¿Su ancho no ocupa más del 40% del ancho de página?
                es_ancho_firma = (ancho_bloque < ancho_pag * 0.40)
                
                # 3. ¿Contiene palabras clave? (Validación extra de seguridad)
                texto_total_bloque = " ".join(lineas_bloque)
                contiene_keywords = bool(patron_firma_keywords.search(texto_total_bloque))

                if es_posicion_firma and es_ancho_firma and contiene_keywords:
                    if not firmas_detectadas:
                        contenido_final.append("## Firmas")
                        firmas_detectadas = True
                    firma_formateada = " — ".join(lineas_bloque)
                    contenido_final.append("- " + firma_formateada)
                    continue

                # Procesamiento de Jerarquización
                texto_unido = " ".join(lineas_bloque).replace(" \n- ", "\n- ").strip()
                texto_unido = re.sub(r'\s{2,}', ' ', texto_unido).strip()

                match = patron_titulo_norma.search(texto_unido)
                if match:
                    tipo = match.group(1).capitalize() # Disposicion o Resolucion
                    sigla = match.group(2)            # DISPCD-TLUJ
                    numero = str(int(match.group(3))) # 0000352 -> 352
                    anio = match.group(4)             # 23
                    
                    # Formateamos el año (asumiendo 20xx si tiene 2 dígitos)
                    anio_completo = f"20{anio}" if len(anio) == 2 else anio
                    
                    titulo_encontrado = f"# {tipo} {sigla} - {numero}/{anio_completo}"
                    indice_titulo = i
                    continue
                
                if patron_visto.match(texto_unido):
                    texto_unido = "## Visto\n" + patron_visto.sub("", texto_unido).strip()
                elif patron_considerando.match(texto_unido):
                    texto_unido = "## Considerando\n" + patron_considerando.sub("", texto_unido).strip()
                elif m_res := patron_resuelve.match(texto_unido):
                    termino = m_res.group(1).replace(" ", "").upper()
                    encabezado = "## Parte dispositiva" if "DISPONE" in termino else "## Parte resolutiva"
                    texto_unido = f"{encabezado}\n" + patron_resuelve.sub("", texto_unido).strip()
                elif m := patron_articulo.match(texto_unido):
                    texto_unido = f"### Artículo {m.group(2)}\n" + patron_articulo.sub("", texto_unido).strip()
                elif patron_anexo.match(texto_unido):
                    texto_unido = "# " + texto_unido
                elif es_negrita:
                    texto_unido = f"## {texto_unido}\n"
                
                # Limpieza de conectores y formato de listas
                texto_unido = re.sub(r';\s*(y|que)\s*$', '.', texto_unido, flags=re.IGNORECASE)
                linea_limpia = texto_unido.lstrip()
                
                if any(linea_limpia.startswith(c) for c in ['·', '●', '•']) or patron_alfabetico.match(linea_limpia):
                    for c in ['·', '●', '•']: 
                        linea_limpia = linea_limpia.replace(c, '', 1).strip()
                    contenido_final.append("- " + linea_limpia)
                else:
                    contenido_final.append(texto_unido)
                # print(f"--x--\n{linea_limpia}")

        contenido_final.append("\n")

    doc.close()

    if titulo_encontrado:
        # Opcional: si quieres quitar la línea original del cuerpo del texto, descomenta la siguiente línea
        # contenido_final.pop(indice_titulo) 
        contenido_final.insert(0, titulo_encontrado)

    nombre_salida = f"{os.path.splitext(nombre_original)[0]}_jerarquizado.md"
    with open(nombre_salida, "w", encoding="utf-8") as f:
        f.write("\n\n".join(contenido_final))
    return nombre_salida

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python script_unificado.py archivo.pdf")
    else:
        ruta_archivo = sys.argv[1]
        inicio = time.time()
        pdf_limpio_buffer = aplanar_y_limpiar_avanzado(ruta_archivo)
        if pdf_limpio_buffer:
            archivo_resultado = extraer_a_markdown_directo(pdf_limpio_buffer, os.path.basename(ruta_archivo))
            print(f"\nProceso total terminado en {time.time() - inicio:.2f} segundos.")
            print(f"Archivo Markdown Jerarquizado: {archivo_resultado}")