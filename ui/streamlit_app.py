import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
from backend.domain.taxonomy import TAXONOMY
from backend.pipelines.importers import Importer
from backend.pipelines.detectors import ColumnMapper
from backend.pipelines.processor import PipelineProcessor

st.set_page_config(
    page_title="AIPDP - AI Product Data Platform",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🧠 AI Product Data Platform (AIPDP)")
st.caption("Sistema central de conocimiento sobre productos - Pipeline ETL Activo")

# Sidebar
with st.sidebar:
    st.header("📊 Estado del Sistema")
    st.metric("Campos en Taxonomía", len(TAXONOMY.fields))
    st.metric("Sinónimos Registrados", len(TAXONOMY.get_all_aliases()))
    
    st.divider()
    st.subheader("📋 Taxonomía Activa")
    for field in TAXONOMY.fields[:5]:  # Mostramos solo 5 para no saturar
        required_tag = "🔴 Obligatorio" if field.required else "⚪ Opcional"
        st.markdown(f"**{field.name}** (*{field.data_type}*) - {required_tag}")
        if field.aliases:
            st.caption(f"Alias: {', '.join(field.aliases[:3])}")

# Área principal
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("🚀 Importar y Procesar Catálogo")
    uploaded_file = st.file_uploader(
        "Arrastra tu archivo (Excel, CSV) o selecciona",
        type=['xlsx', 'xls', 'csv'],
        accept_multiple_files=False
    )
    
    if uploaded_file is not None:
        with st.spinner("⏳ Procesando archivo... Esto puede tomar unos segundos."):
            try:
                # Leer archivo
                df = Importer.read_from_bytes(uploaded_file.read(), uploaded_file.name)
                
                # Ejecutar pipeline
                processor = PipelineProcessor(confidence_threshold=0.6)
                result = processor.process(df)
                
                # Mostrar resumen ejecutivo
                st.success(f"✅ Procesamiento completado: {result['summary']['total_rows']} productos")
                
                # Métricas principales
                col_met1, col_met2, col_met3, col_met4 = st.columns(4)
                col_met1.metric("Productos", result['summary']['total_rows'])
                col_met2.metric("Errores", result['summary']['error_rows'], delta="⚠️")
                col_met3.metric("Advertencias", result['summary']['warning_rows'], delta="⚡")
                col_met4.metric("Calidad", f"{result['summary']['quality_score']*100:.0f}%", delta="📈")
                
                # Mapeo de columnas
                with st.expander("🔍 Mapeo de Columnas (Confianza)"):
                    mapping_df = pd.DataFrame([
                        {"Columna Origen": col, "Campo Taxonomía": field if field else "❓ No detectado", "Confianza": f"{conf*100:.0f}%"}
                        for col, (field, conf) in result['mapping'].items()
                    ])
                    st.dataframe(mapping_df, use_container_width=True)
                
                # Productos normalizados (tabla)
                with st.expander("📊 Productos Normalizados (Vista previa)", expanded=True):
                    if result['products']:
                        df_normalized = pd.DataFrame(result['products'])
                        st.dataframe(df_normalized.head(20), use_container_width=True)
                        st.caption(f"Mostrando 20 de {len(result['products'])} productos")
                
                # Reporte de validación
                with st.expander("⚠️ Reporte de Calidad y Validación"):
                    if result['validation_report']['issues']:
                        issues_df = pd.DataFrame(result['validation_report']['issues'])
                        st.dataframe(issues_df, use_container_width=True)
                    else:
                        st.success("✅ No se encontraron errores ni advertencias.")
                    
                    if result['duplicates']:
                        st.warning(f"⚠️ Se detectaron {len(result['duplicates'])} productos con código duplicado.")
                        dup_df = pd.DataFrame(result['duplicates'])
                        st.dataframe(dup_df)
                
                # Botón de descarga (simulado por ahora)
                st.download_button(
                    label="📥 Descargar Catálogo Normalizado (CSV)",
                    data=pd.DataFrame(result['products']).to_csv(index=False).encode('utf-8'),
                    file_name=f"{uploaded_file.name.split('.')[0]}_normalizado.csv",
                    mime="text/csv"
                )
                
            except Exception as e:
                st.error(f"❌ Error durante el procesamiento: {str(e)}")
                st.exception(e)

with col2:
    st.subheader("📈 Confianza del Sistema")
    st.metric("Confianza Global", "N/A", delta="Sube un archivo para evaluar")
    st.metric("Productos en Memoria", "0")
    
    st.divider()
    st.caption("⚡ Pipeline: Importar → Detectar → Normalizar → Validar")

st.divider()
st.caption("AIPDP v0.2.0 - Pipeline ETL Activo | Desarrollado bajo Clean Architecture + DDD")
