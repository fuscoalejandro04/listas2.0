import sys
import os
from pathlib import Path

# 1. Calcular la ruta absoluta de la raíz del repositorio (listas2.0)
root_path = str(Path(__file__).resolve().parent.parent)

# 2. Inyectar la ruta en sys.path ANTES de importar cualquier módulo interno
if root_path not in sys.path:
    sys.path.insert(0, root_path)

# 3. Importar librerías de terceros
import streamlit as st
import pandas as pd
import io
import importlib.util

# 4. Importar módulos de backend (ya no se redefine PipelineProcessor aquí)
from backend.domain.taxonomy import TAXONOMY
from backend.pipelines.detectors import ColumnMapper
from backend.pipelines.processor import PipelineProcessor

# Cargar manualmente el importador (si tienes problemas de caché)
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

# ============================================================
# INTERFAZ CON PESTAÑAS (Tabs)
# ============================================================
tab1, tab2 = st.tabs(["⚡ Pipeline ETL", "⚙️ Configuración de Reglas"])

# ============================================================
# PESTAÑA 1: PIPELINE ETL (Todo el código actual)
# ============================================================
with tab1:
    # --- Todo el código existente de importación y procesamiento va aquí ---
    # (Coloca todo el contenido que estaba debajo de los imports,
    #  desde el título y la sidebar hasta los botones de descarga)
    # --- INICIO DEL BLOQUE EXISTENTE ---
    
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
                    # ... (el resto del código de procesamiento) ...
                    # Asegúrate de que todo el código desde "import_result = import_excel(...)"
                    # hasta los botones de descarga esté aquí dentro.
                    pass  # Reemplazar con el código real
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
    
    # --- FIN DEL BLOQUE EXISTENTE ---

# ============================================================
# PESTAÑA 2: CONFIGURACIÓN DE REGLAS (CRUD de Líneas de Producto)
# ============================================================
with tab2:
    st.header("⚙️ Configuración de Reglas")
    st.caption("Gestiona las líneas de producto que el sistema reconoce para categorización.")
    
    # Inicializar el categorizador (solo para acceder a las líneas)
    from backend.pipelines.rule_categorizer import RuleCategorizer
    categorizer = RuleCategorizer()
    
    # Mostrar lista actual
    st.subheader("📋 Líneas de Producto Actuales")
    lineas = categorizer.obtener_lineas()
    
    if lineas:
        # Mostrar como tabla
        df_lineas = pd.DataFrame({"Línea": lineas})
        st.dataframe(df_lineas, use_container_width=True, hide_index=True)
    else:
        st.info("No hay líneas configuradas.")
    
    st.divider()
    
    # CRUD: Agregar nueva línea
    st.subheader("➕ Agregar Nueva Línea")
    col_add1, col_add2 = st.columns([3, 1])
    with col_add1:
        nueva_linea = st.text_input("Nombre de la línea (ej. PREMIUM PLUS)", key="nueva_linea_input")
    with col_add2:
        st.write("")  # Espaciado
        st.write("")  # Espaciado
        btn_agregar = st.button("Agregar Línea", type="primary", use_container_width=True)
    
    if btn_agregar:
        if nueva_linea and nueva_linea.strip():
            if categorizer.agregar_linea(nueva_linea.strip()):
                st.success(f"✅ Línea '{nueva_linea.strip()}' agregada correctamente.")
                st.rerun()  # Refrescar la página para mostrar la lista actualizada
            else:
                st.warning(f"⚠️ La línea '{nueva_linea.strip()}' ya existe o es inválida.")
        else:
            st.error("❌ Ingresa un nombre válido para la línea.")
    
    st.divider()
    
    # CRUD: Eliminar línea existente
    st.subheader("🗑️ Eliminar Línea")
    if lineas:
        col_del1, col_del2 = st.columns([3, 1])
        with col_del1:
            linea_a_eliminar = st.selectbox(
                "Selecciona una línea para eliminar",
                options=lineas,
                key="eliminar_linea_select"
            )
        with col_del2:
            st.write("")  # Espaciado
            st.write("")  # Espaciado
            btn_eliminar = st.button("Eliminar Línea", type="secondary", use_container_width=True)
        
        if btn_eliminar:
            if linea_a_eliminar:
                if categorizer.eliminar_linea(linea_a_eliminar):
                    st.success(f"✅ Línea '{linea_a_eliminar}' eliminada correctamente.")
                    st.rerun()
                else:
                    st.error(f"❌ Error al eliminar la línea '{linea_a_eliminar}'.")
    else:
        st.info("No hay líneas para eliminar.")
    
    st.divider()
    st.caption("💡 Los cambios se guardan automáticamente en el archivo `backend/infrastructure/knowledge/lineas_producto.json`.")

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
                    # 🔥 USAR process_result['products'] DIRECTAMENTE
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
