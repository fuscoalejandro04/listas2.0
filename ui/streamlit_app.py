import streamlit as st
import pandas as pd
from backend.domain.taxonomy import TAXONOMY
from backend.domain.product import Product

# Configuración de la página (moderna y profesional)
st.set_page_config(
    page_title="AIPDP - AI Product Data Platform",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Título Principal
st.title("🧠 AI Product Data Platform (AIPDP)")
st.caption("Sistema central de conocimiento sobre productos - Fundación Cero")

# Sidebar con información del sistema
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

# Área principal de trabajo
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("🚀 Importar Catálogo")
    uploaded_file = st.file_uploader(
        "Arrastra tu archivo (Excel, CSV) o selecciona",
        type=['xlsx', 'xls', 'csv'],
        accept_multiple_files=False
    )
    
    if uploaded_file is not None:
        # Por ahora, solo mostramos la recepción. En Fase 2, llamaremos al pipeline.
        st.success(f"Archivo recibido: **{uploaded_file.name}**")
        st.info("⏳ El motor de procesamiento ETL se conectará aquí en la siguiente etapa.")
        
        # Previsualización básica (para ir calentando)
        try:
            df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
            st.dataframe(df.head(5))
        except Exception as e:
            st.warning(f"No se pudo previsualizar: {e}")

with col2:
    st.subheader("📈 Confianza del Sistema")
    st.metric("Confianza Global", "N/A", delta="Esperando datos")
    st.metric("Productos en Memoria", "0")
    
    st.divider()
    st.caption("⚡ Arquitectura: Modular Monolith + Event Bus (In-Memory)")

# Footer
st.divider()
st.caption("AIPDP v0.1.0 - Fundación | Desarrollado bajo Clean Architecture + DDD")
