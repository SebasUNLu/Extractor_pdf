# PDF to Markdown Extractor

Este proyecto es una herramienta robusta en Python diseñada para convertir archivos PDF complejos (con tablas, listas y formatos académicos) en archivos Markdown limpios y estructurados.

## 🚀 Funcionamiento

El script utiliza un pipeline de dos etapas para garantizar la fidelidad del texto y evitar el desorden común en las extracciones de PDF tradicionales:

### 1. Fase de Aplanado y Limpieza (Normalización)
Utiliza la geometría de los objetos para reconstruir el PDF en memoria. 
- **Filtrado de Gráficos:** Detecta y elimina "tablas fantasma" o elementos decorativos que ensucian la extracción.
- **Normalización de Texto:** Asegura que el texto mantenga su origen y tamaño, facilitando el análisis posterior.

### 2. Fase de Extracción Inteligente
Procesa el PDF normalizado mediante un análisis de coordenadas:
- **Detección de Tablas:** Identifica áreas de tablas y las convierte a formato Markdown usando `pandas`.
- **Lógica de Párrafos y Listas:** Une oraciones cortadas por el margen del PDF y reconoce viñetas (·, ●, •) o listas alfabéticas automáticamente.
- **Exclusión de Márgenes:** Ignora encabezados y pies de página configurando márgenes de seguridad (20% superior, 10% inferior).

## 🛠️ Requisitos e Instalación

1. **Clonar el repositorio:**
  ```bash
  git clone https://github.com/SebasUNLu/Extractor_pdf
  cd Extractor_pdf
  ```
  
2. **Instalar dependencias:**
- Asegúrate de tener Python 3.x instalado. Luego ejecuta:
```bash
pip install pymupdf pandas tabulate
```

## 📖 Uso
Para procesar un archivo individual, ejecuta el script pasando la ruta del PDF como argumento:
```bash
python script_extractor.py mi_documento.pdf
```
El script generará un archivo llamado `mi_documento_procesado.md` en la misma carpeta.

## 📁 Estructura del Proyecto
- `script_unificado.py`: El core del proyecto que contiene ambas fases de procesamiento.

- `procesador_masivo.py`: Script para procesar todos los PDFs de una carpeta en lote con manejo de errores y logs. La forma de ejecutarlo es la siguiente:
```bash
# Debes tener ambos scripts y los pdf a procesar en la misma carpeta
python procesador_masivo.py
```

- `/Pruebas`: Carpeta donde se guardan las pruebas realizadas con el script para poder comparar resultados con los documentos originales.