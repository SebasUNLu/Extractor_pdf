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
El proyecto ofrece dos modalidades de uso dependiendo de si necesitas procesar un solo documento o una carpeta completa:

### 1. Procesamiento Individual (Paso a paso)
Ideal para probar o extraer la información de un solo archivo. Consta de dos pasos manuales:

#### Paso A: Extracción
Ejecuta el script extractor pasando la ruta del PDF como argumento:

```bash
python script_extractor.py mi_documento.pdf
```
Esto generará dos archivos en la misma carpeta: `mi_documento.md` (con el texto limpio y jerarquizado) y `mi_documento.json` (con los metadatos auxiliares extraídos).

#### Paso B: Post-Procesamiento
Para consolidar la información en el formato final, ejecuta el post-procesador pasándole los dos archivos generados en el paso anterior:
```bash
python post_procesador.py mi_documento.json mi_documento.md
```
Esto creará el archivo final mi_documento_canonico.yaml, el cual contendrá toda la metadata estructurada y el cuerpo del documento listo para ser consumido por otras aplicaciones.

#### 2. Procesador masivo
Ideal para procesar decenas o cientos de PDFs automáticamente. Este script se encarga de gestionar el pipeline completo (extracción + post-procesamiento) de forma segura.

Ubícate en la raíz del proyecto y ejecuta el procesador masivo indicando la ruta absoluta o relativa de la carpeta que contiene los PDFs:
```bash
python procesador_masivo.py /ruta/a/la/carpeta_con_pdfs
```
El sistema procesará cada archivo y automáticamente guardará los resultados finales (`.md`, `.json` y `_canonico.yaml`) de forma ordenada en una carpeta llamada resultados_extractor creada en tu directorio actual.

Se generará un archivo `errores_extraccion.log` para registrar de manera transparente cualquier PDF que haya fallado o presentado problemas durante el proceso.


## 📁 Estructura del Proyecto
- `script_unificado.py`: El core del proyecto que contiene ambas fases de procesamiento.

- `procesador_masivo.py`: Script para procesar todos los PDFs de una carpeta en lote con manejo de errores y logs. La forma de ejecutarlo es la siguiente:
```bash
# Debes tener ambos scripts y los pdf a procesar en la misma carpeta
python procesador_masivo.py
```
- `procesador_masivo.py`: Orquestador diseñado para procesar todos los PDFs de un directorio en lote, gestionando la ejecución secuencial de los scripts anteriores y manejando los logs.

- `/Pruebas`: Carpeta donde se guardan las pruebas realizadas con el script para poder comparar resultados con los documentos originales.