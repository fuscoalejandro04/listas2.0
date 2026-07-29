import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import io
import importlib.util

# ============================================================
# CARGA MANUAL DEL IMPORTADOR (para evitar problemas de cache)
# ============================================================
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

# Cargar la función
import_excel = load_import_excel()
if import_excel is None:
    st.stop()

# Resto de imports normales
from backend.domain.taxonomy import TAXONOMY
from backend.pipelines.detectors import ColumnMapper
from backend.pipelines.processor import PipelineProcessor

st.set_page_config(
    page_title="AIPDP - AI Product Data Platform",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🧠 AI Product Data Platform (AIPDP)")
st.caption("Sistema central de conocimiento sobre productos - Pipeline ETL Activo con importación profesional")

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
                # =================================================
                # 1. IMPORTACIÓN PROFESIONAL (HOJA POR HOJA)
                # =================================================
                import_result = import_excel(uploaded_file.read(), uploaded_file.name)
                
                # Mostrar resumen de la importación
                if import_result.failed_sheets:
                    st.warning(f"⚠️ {len(import_result.failed_sheets)} hoja(s) fallaron al importar.")
                    for failed in import_result.failed_sheets:
                        st.caption(f"- {failed.sheet_name}: {failed.error}")
                
                if not import_result.successful_sheets:
                    st.error("❌ No se pudo procesar ninguna hoja del archivo.")
                    st.stop()
                
                # Combinar todas las hojas exitosas en un solo DataFrame
                dfs = []
                for sheet_result in import_result.successful_sheets:
                    if sheet_result.dataframe is not None and not sheet_result.dataframe.empty:
                        df = sheet_result.dataframe.copy()
                        df['hoja_origen'] = sheet_result.sheet_name
                        dfs.append(df)
                
                if not dfs:
                    st.error("❌ Las hojas procesadas no contienen datos válidos.")
                    st.stop()
                
                df_raw = pd.concat(dfs, ignore_index=True)
                
                # Información del archivo procesado
                sheet_names = [sr.sheet_name for sr in import_result.successful_sheets]
                st.info(f"📂 Archivo procesado con {len(sheet_names)} hojas: {', '.join(sheet_names[:5])}{'...' if len(sheet_names) > 5 else ''}. Total de filas: {df_raw.shape[0]}, columnas: {df_raw.shape[1]}")
                
                # =================================================
                # 2. PIPELINE ETL (DETECCIÓN, NORMALIZACIÓN, VALIDACIÓN)
                # =================================================
                processor = PipelineProcessor(confidence_threshold=0.6)
                process_result = processor.process(df_raw)
                
                # Resumen ejecutivo
                summary = process_result['summary']
                st.success(f"✅ Procesamiento completado: {summary['total_rows']} productos")
                
                # Métricas principales
                col_met1, col_met2, col_met3, col_met4 = st.columns(4)
                col_met1.metric("Productos", summary['total_rows'])
                col_met2.metric("Errores", summary['error_rows'], delta="⚠️")
                col_met3.metric("Advertencias", summary['warning_rows'], delta="⚡")
                col_met4.metric("Calidad", f"{summary['quality_score']*100:.0f}%", delta="📈")
                
                # 3. Mapeo de columnas
                with st.expander("🔍 Mapeo de Columnas (Confianza)"):
                    mapping_df = pd.DataFrame([
                        {"Columna Origen": col, "Campo Taxonomía": field if field else "❓ No detectado", "Confianza": f"{conf*100:.0f}%"}
                        for col, (field, conf) in process_result['mapping'].items()
                    ])
                    st.dataframe(mapping_df, use_container_width=True)
                
                # 4. Vista previa de productos normalizados
                with st.expander("📊 Productos Normalizados (Vista previa)", expanded=True):
                    if process_result['products']:
                        df_normalized = pd.DataFrame(process_result['products'])
                        cols_to_show = ['codigo', 'nombre_articulo', 'precio_lista', 'hoja_origen'] if 'hoja_origen' in df_normalized.columns else ['codigo', 'nombre_articulo', 'precio_lista']
                        available_cols = [col for col in cols_to_show if col in df_normalized.columns]
                        st.dataframe(df_normalized[available_cols].head(20), use_container_width=True)
                        st.caption(f"Mostrando 20 de {len(process_result['products'])} productos")
                
                # 5. Reporte de validación
                with st.expander("⚠️ Reporte de Calidad y Validación"):
                    issues = process_result['validation_report']['issues']
                    if issues:
                        issues_df = pd.DataFrame(issues)
                        st.dataframe(issues_df, use_container_width=True)
                    else:
                        st.success("✅ No se encontraron errores ni advertencias.")
                    
                    if process_result['duplicates']:
                        st.warning(f"⚠️ Se detectaron {len(process_result['duplicates'])} productos con código duplicado.")
                        dup_df = pd.DataFrame(process_result['duplicates'])
                        st.dataframe(dup_df)
                
                # 6. Descarga en Excel y CSV
                st.subheader("📥 Descargar Catálogo Normalizado")
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_export = pd.DataFrame(process_result['products'])
                    df_export.to_excel(writer, sheet_name='Productos Normalizados', index=False)
                    
                    if issues:
                        issues_df = pd.DataFrame(issues)
                        issues_df.to_excel(writer, sheet_name='Validaciones', index=False)
                    
                    mapping_export = pd.DataFrame([
                        {"Columna Origen": col, "Campo Taxonomía": field if field else "No detectado", "Confianza": f"{conf*100:.0f}%"}
                        for col, (field, conf) in process_result['mapping'].items()
                    ])
                    mapping_export.to_excel(writer, sheet_name='Mapeo de Columnas', index=False)
                
                output.seek(0)
                st.download_button(
                    label="📥 Descargar Excel Completo",
                    data=output,
                    file_name=f"{uploaded_file.name.split('.')[0]}_procesado.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
                csv_data = pd.DataFrame(process_result['products']).to_csv(index=False).encode('utf-8')
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
    st.caption("⚡ Pipeline: Importación Profesional → Detectar → Normalizar → Validar")

st.divider()
st.caption("AIPDP v0.5.0 - Importación profesional hoja por hoja")
