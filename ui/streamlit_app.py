import sys
import os
from pathlib import Path

# 1. Calcular la ruta absoluta de la raíz del repositorio
root_path = str(Path(__file__).resolve().parent.parent)

# 2. Inyectar la ruta en sys.path ANTES de importar cualquier módulo interno
if root_path not in sys.path:
    sys.path.insert(0, root_path)

# 3. Importar librerías de terceros
import streamlit as st
import pandas as pd
import io
import importlib.util

# 4. Importar módulos de backend
from backend.domain.taxonomy import TAXONOMY
from backend.pipelines.detectors import ColumnMapper
from backend.pipelines.processor import PipelineProcessor
from backend.pipelines.rule_categorizer import RuleCategorizer

# Cargar manualmente el importador
def load_import_excel():
    """Carga la función import_excel desde backend/pipelines/importers.py"""
    filepath = Path(__file__).resolve().parent.parent / "backend" / "pipelines" / "importers.py"
    if not filepath.exists():
        st.error(f"❌ No se encuentra el archivo: {filepath}")
        return None
    
    spec = importlib.util.spec_from_file_location("importers_module", filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    if hasattr(module, "import_excel"):
        return module.import_excel
    else:
        st.error("❌ La función 'import_excel' no se encontró en el módulo.")
        return None

import_excel = load_import_excel()
if import_excel is None:
    st.stop()

# Configuración de la página
st.set_page_config(
    page_title="AIPDP - AI Product Data Platform",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Pestañas
tab1, tab2 = st.tabs(["⚡ Pipeline ETL", "⚙️ Configuración de Reglas"])

with tab1:
    st.title("🧠 AI Product Data Platform (AIPDP)")
    st.caption("Sistema central de conocimiento sobre productos - Pipeline ETL Activo")
    
    uploaded_file = st.file_uploader("Cargar lista de precios (Excel)", type=["xlsx", "xls"])
    
    if uploaded_file is not None:
        file_bytes = uploaded_file.read()
        import_result = import_excel(file_bytes, uploaded_file.name)
        
        if import_result and import_result.successful_sheets:
            processor = PipelineProcessor()
            
            for sheet in import_result.successful_sheets:
                st.subheader(f"Hoja: {sheet.sheet_name}")
                df_raw = sheet.dataframe
                
                if df_raw is not None and not df_raw.empty:
                    # Desempaquetado correcto de la tupla (DataFrame, Reporte)
                    processed_df, summary = processor.process(df_raw)
                    
                    st.success("✅ Procesamiento con IA completado con éxito!")
                    st.dataframe(processed_df, use_container_width=True)
                    
                    if summary:
                        st.subheader("📊 Reporte de Calidad")
                        st.json(summary)
        else:
            st.error("❌ No se pudieron procesar las hojas del archivo.")

with tab2:
    st.header("⚙️ Configuración de Reglas")
    st.caption("Gestiona las líneas de producto que el sistema reconoce para categorización.")
    
    categorizer = RuleCategorizer()
    lineas = categorizer.obtener_lineas() if hasattr(categorizer, 'obtener_lineas') else []
    
    st.subheader("📋 Líneas de Producto Actuales")
    if lineas:
        st.write(", ".join([f"`{l}`" for l in lineas]))
    else:
        st.info("No hay líneas registradas.")
