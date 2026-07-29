import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import io
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
    for field in TAXONOMY.fields[:5]:
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
                # 1. Leer el archivo (TODAS las hojas si es Excel)
                df_raw = Importer.read_from_bytes(uploaded_file.read(), uploaded_file.name)
                
                # Mostrar información de las hojas (si existe columna hoja_origen)
                if 'hoja_origen' in df_raw.columns:
                    hoja_counts = df_raw['hoja_origen'].value_counts().to_dict()
                    st.info(f"📂 Archivo procesado con {len(hoja_counts)} hojas: {', '.join([f'{k}: {v} filas' for k, v in hoja_counts.items()])}")
                else:
                    st.info(f"📄 Archivo procesado con {df_raw.shape[0]} filas y {df_raw.shape[1]} columnas.")
                
                # 2. Ejecutar pipeline completo
                processor = PipelineProcessor(confidence_threshold=0.6)
                result = processor.process(df_raw)
                
                # 3. Mostrar resumen ejecutivo
                summary = result['summary']
                st.success(f"✅ Procesamiento completado: {summary['total_rows']} productos")
                
                # Métricas principales
                col_met1, col_met2, col_met3, col_met4 = st.columns(4)
                col_met1.metric("Productos", summary['total_rows'])
                col_met2.metric("Errores", summary['error_rows'], delta="⚠️")
                col_met3.metric("Advertencias", summary['warning_rows'], delta="⚡")
                col_met4.metric("Calidad", f"{summary['quality_score']*100:.0f}%", delta="📈")
                
                # 4. Mapeo de columnas
                with st.expander("🔍 Mapeo de Columnas (Confianza)"):
                    mapping_df = pd.DataFrame([
                        {"Columna Origen": col, "Campo Taxonomía": field if field else "❓ No detectado", "Confianza": f"{conf*100:.0f}%"}
                        for col, (field, conf) in result['mapping'].items()
                    ])
                    st.dataframe(mapping_df, use_container_width=True)
                
                # 5. Vista previa de productos normalizados
                with st.expander("📊 Productos Normalizados (Vista previa)", expanded=True):
                    if result['products']:
                        df_normalized = pd.DataFrame(result['products'])
                        # Si existe hoja_origen, mostrarla
                        if 'hoja_origen' in df_normalized.columns:
                            st.dataframe(df_normalized[['codigo', 'nombre_articulo', 'precio_lista', 'hoja_origen']].head(20), use_container_width=True)
                        else:
                            st.dataframe(df_normalized.head(20), use_container_width=True)
                        st.caption(f"Mostrando 20 de {len(result['products'])} productos")
                
                # 6. Reporte de calidad
                with st.expander("⚠️ Reporte de Calidad y Validación"):
                    issues = result['validation_report']['issues']
                    if issues:
                        issues_df = pd.DataFrame(issues)
                        st.dataframe(issues_df, use_container_width=True)
                    else:
                        st.success("✅ No se encontraron errores ni advertencias.")
                    
                    if result['duplicates']:
                        st.warning(f"⚠️ Se detectaron {len(result['duplicates'])} productos con código duplicado.")
                        dup_df = pd.DataFrame(result['duplicates'])
                        st.dataframe(dup_df)
                
                # 7. Descarga con formato Excel mejorado
                st.subheader("📥 Descargar Catálogo Normalizado")
                # Crear un Excel con dos hojas: datos y validaciones
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    # Hoja de datos normalizados
                    df_export = pd.DataFrame(result['products'])
                    df_export.to_excel(writer, sheet_name='Productos Normalizados', index=False)
                    
                    # Hoja de validaciones (errores y advertencias)
                    if issues:
                        issues_df = pd.DataFrame(issues)
                        issues_df.to_excel(writer, sheet_name='Validaciones', index=False)
                    else:
                        # Hoja vacía con mensaje
                        pd.DataFrame({"Mensaje": ["No se encontraron errores o advertencias."]}).to_excel(writer, sheet_name='Validaciones', index=False)
                    
                    # Hoja de mapeo usado
                    mapping_export = pd.DataFrame([
                        {"Columna Origen": col, "Campo Taxonomía": field if field else "No detectado", "Confianza": f"{conf*100:.0f}%"}
                        for col, (field, conf) in result['mapping'].items()
                    ])
                    mapping_export.to_excel(writer, sheet_name='Mapeo de Columnas', index=False)
                
                output.seek(0)
                st.download_button(
                    label="📥 Descargar Excel Completo",
                    data=output,
                    file_name=f"{uploaded_file.name.split('.')[0]}_procesado.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
                # También ofrecer CSV simple
                csv_data = pd.DataFrame(result['products']).to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Descargar CSV (solo datos)",
                    data=csv_data,
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
st.caption("AIPDP v0.3.0 - Soporte multi-hoja | Desarrollado bajo Clean Architecture + DDD")
