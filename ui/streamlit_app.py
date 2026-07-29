import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
from backend.domain.taxonomy import TAXONOMY
from backend.pipelines.importers import Importer
from backend.pipelines.detectors import ColumnMapper

st.set_page_config(
    page_title="AIPDP - AI Product Data Platform",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🧠 AI Product Data Platform (AIPDP)")
st.caption("Sistema central de conocimiento sobre productos - Fundación Cero")

# Sidebar
with st.sidebar:
    st.header("📊 Estado del Sistema")
    st.metric("Campos en Taxonomía", len(TAXONOMY.fields))
    st.metric("Sinónimos Registrados", len(TAXONOMY.get_all_aliases()))
    
    st.divider()
    st.subheader("📋 Taxonomía Activa")
    for field in TAXONOMY.fields:
        required_tag = "🔴 Obligatorio" if field.required else "⚪ Opcional"
        st.markdown(f"**{field.name}** (*{field.data_type}*) - {required_tag}")
        if field.aliases:
            st.caption(f"Alias: {', '.join(field.aliases[:3])}")

# Área principal
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("🚀 Importar Catálogo")
    uploaded_file = st.file_uploader(
        "Arrastra tu archivo (Excel, CSV) o selecciona",
        type=['xlsx', 'xls', 'csv'],
        accept_multiple_files=False
    )
    
    if uploaded_file is not None:
        try:
            # Leer el archivo usando nuestro importador
            df = Importer.read_from_bytes(uploaded_file.read(), uploaded_file.name)
            st.success(f"✅ Archivo leído: **{uploaded_file.name}** - {df.shape[0]} filas, {df.shape[1]} columnas")
            
            # Detectar columnas
            mapper = ColumnMapper(confidence_threshold=0.6)
            mapping = mapper.map_columns(df)
            report = mapper.get_confidence_report(mapping)
            
            st.subheader("🔍 Mapeo de Columnas Detectado")
            
            # Mostrar tabla de mapeo
            mapping_df = pd.DataFrame([
                {
                    "Columna Origen": col,
                    "Campo Taxonomía": field if field else "❓ No detectado",
                    "Confianza": f"{conf*100:.0f}%"
                }
                for col, (field, conf) in mapping.items()
            ])
            st.dataframe(mapping_df, use_container_width=True)
            
            # Métricas de confianza
            col_met1, col_met2, col_met3 = st.columns(3)
            col_met1.metric("Columnas Detectadas", report["mapped_columns"])
            col_met2.metric("Columnas No Detectadas", report["unmapped_columns"])
            col_met3.metric("Confianza Promedio", f"{report['average_confidence']*100:.0f}%")
            
            # Vista previa de datos
            with st.expander("👁️ Vista previa de los datos"):
                st.dataframe(df.head(10))
            
        except Exception as e:
            st.error(f"❌ Error al procesar el archivo: {str(e)}")

with col2:
    st.subheader("📈 Confianza del Sistema")
    st.metric("Confianza Global", "N/A", delta="Sube un archivo para evaluar")
    st.metric("Productos en Memoria", "0")
    
    st.divider()
    st.caption("⚡ Arquitectura: Modular Monolith + Event Bus (In-Memory)")

st.divider()
st.caption("AIPDP v0.1.0 - Fundación | Desarrollado bajo Clean Architecture + DDD")
