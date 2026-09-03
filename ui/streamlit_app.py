import streamlit as st
import pandas as pd
import io
import re

st.set_page_config(page_title="Procesador Automático Multihoja", layout="wide", page_icon="⚙️")

# --- FUNCIONES DE LIMPIEZA CENTRALIZADAS ---
def limpiar_precio(val):
    if pd.isna(val): return 0.0
    if isinstance(val, (int, float)): return float(val)
    val_str = str(val).replace('$', '').replace('.', '').replace(',', '.').strip()
    try: return float(val_str)
    except: return 0.0

def limpiar_iva(val):
    if pd.isna(val) or str(val).strip() == '': return 0.21
    val_str = str(val).replace('%', '').replace(',', '.').strip()
    try:
        num = float(val_str)
        return num / 100.0 if num > 1 else num
    except: return 0.21

def deducir_herramienta(row):
    texto = str(row.get('Descripcion', '')) + " " + str(row.get('Modelo', ''))
    texto = texto.upper()
    cat = ""
    if any(x in texto for x in ['TALADRO', 'ATORNILLADOR', 'LLAVE DE IMPACTO']): cat = "Taladro / Atornillador"
    elif any(x in texto for x in ['AMOLADORA', 'PULIDORA', 'LIJADORA']): cat = "Amoladora / Lijadora"
    elif any(x in texto for x in ['SIERRA', 'CALADORA', 'INGLETEADORA', 'SENSITIVA']): cat = "Sierras"
    elif 'ROTOMARTILLO' in texto or 'MARTILLO' in texto: cat = "Rotomartillo"
    elif 'COMPRESOR' in texto: cat = "Compresor"
    elif 'ASPIRADORA' in texto or 'HIDROLAVADORA' in texto: cat = "Limpieza"
    elif any(x in texto for x in ['MOTOSIERRA', 'CORTACESPED', 'BORDEADORA', 'DESMALEZADORA', 'SOPLADOR']): cat = "Jardín"
    elif any(x in texto for x in ['BATERÍA', 'BATERIA', 'CARGADOR', 'STARTER KIT']): cat = "Baterías y Cargadores"
    elif any(x in texto for x in ['MECHA', 'DISCO', 'PUNTA', 'ACCESORIO', 'HOJA']): cat = "Accesorios"
    else: cat = "Herramienta General"

    alim = ""
    if any(x in texto for x in ['INALÁMBRIC', 'INALAMBRIC', 'BATERÍA', 'BATERIA', '18V', '36V', 'LI-ION']): alim = "Inalámbrica"
    elif any(x in texto for x in ['ELÉCTRIC', 'ELECTRIC', '220V', ' 220 V']): alim = "Eléctrica"
    return f"{cat} {alim}".strip()

# --- INICIALIZAR MEMORIA ---
if 'datos_acumulados' not in st.session_state:
    st.session_state.datos_acumulados = pd.DataFrame()

st.title("⚙️ Procesador y Limpiador de Listas de Precios")

# --- CONFIGURACIÓN DE SALIDA ---
st.sidebar.header("1. Configuración de Salida")
marca_destino = st.sidebar.selectbox("Marca del catálogo:", ["Einhell", "KWB", "Fijaciones", "Penosil", "Otra"])
archivo_salida = f"{marca_destino}_Limpia.xlsx" if marca_destino != "Otra" else "Productos_Limpia.xlsx"

if st.sidebar.button("🗑️ Vaciar Datos", use_container_width=True):
    st.session_state.datos_acumulados = pd.DataFrame()
    st.rerun()

# --- CARGA DE ARCHIVO ---
st.subheader("2. Cargar Excel del Proveedor")
uploaded_file = st.file_uploader("Sube el archivo original", type=['xlsx', 'xls', 'csv'])

if uploaded_file:
    es_csv = uploaded_file.name.endswith('.csv')
    xls = uploaded_file if es_csv else pd.ExcelFile(uploaded_file)
    sheet_names = ["Hoja CSV"] if es_csv else xls.sheet_names

    st.markdown("---")
    
    # ==========================================
    # MODO 1: PROCESAMIENTO AUTOMÁTICO MASIVO
    # ==========================================
    st.subheader("🚀 Modo Automático (Recomendado)")
    st.write("El sistema escaneará todas las hojas, buscará los títulos, mapeará las columnas y procesará todo en un solo clic.")
    
    if st.button(f"⚡ Procesar TODO el archivo automáticamente para {marca_destino}", type="primary", use_container_width=True):
        with st.spinner("Procesando hojas y analizando datos..."):
            columnas_app = ['Codigo', 'Modelo', 'Descripcion', 'Precio_Lista', 'IVA', 'Herramienta', 'Color', 'Embalaje', 'CantidadPorCaja', 'UnidadPrecio']
            hojas_procesadas = 0
            
            for sheet in sheet_names:
                # 1. Encontrar la fila de títulos escaneando las primeras 15 filas
                df_temp = pd.read_csv(xls, nrows=15, header=None) if es_csv else pd.read_excel(xls, sheet_name=sheet, nrows=15, header=None)
                
                fila_header = -1
                for idx, row in df_temp.iterrows():
                    row_str = " ".join([str(x).upper() for x in row.values])
                    if "CODIGO" in row_str or "CÓDIGO" in row_str or "PRECIO" in row_str:
                        fila_header = idx
                        break
                
                # Si no encuentra un encabezado válido (hojas vacías o de presentación), la salta
                if fila_header == -1:
                    continue
                
                # 2. Cargar la hoja real con los títulos correctos
                df_raw = pd.read_csv(xls, skiprows=fila_header) if es_csv else pd.read_excel(xls, sheet_name=sheet, skiprows=fila_header)
                
                # 3. Mapeo Automático
                df_limpio = pd.DataFrame()
                for col_esp in columnas_app:
                    col_encontrada = None
                    for c_orig in df_raw.columns:
                        if col_esp.lower() in str(c_orig).lower() or (col_esp == 'Precio_Lista' and 'precio' in str(c_orig).lower()):
                            col_encontrada = c_orig
                            break
                    if col_encontrada:
                        df_limpio[col_esp] = df_raw[col_encontrada]
                    else:
                        df_limpio[col_esp] = None

                # 4. Limpieza y Enriquecimiento
                df_limpio['Marca'] = marca_destino
                df_limpio['Hoja_Origen'] = sheet
                
                if df_limpio['Herramienta'].isnull().all() and 'Descripcion' in df_limpio.columns:
                    df_limpio['Herramienta'] = df_limpio.apply(deducir_herramienta, axis=1)
                
                if 'Precio_Lista' in df_limpio.columns:
                    df_limpio['Precio_Lista'] = df_limpio['Precio_Lista'].apply(limpiar_precio)
                    
                if 'IVA' in df_limpio.columns:
                    df_limpio['IVA'] = df_limpio['IVA'].apply(limpiar_iva)
                else:
                    df_limpio['IVA'] = 0.21
                    
                if 'Codigo' in df_limpio.columns:
                    df_limpio['Codigo'] = df_limpio['Codigo'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                
                df_limpio = df_limpio.dropna(subset=['Codigo', 'Descripcion'], how='all')
                
                st.session_state.datos_acumulados = pd.concat([st.session_state.datos_acumulados, df_limpio], ignore_index=True)
                hojas_procesadas += 1
                
            st.success(f"✅ ¡Proceso Automático Terminado! Se leyeron y combinaron {hojas_procesadas} hojas con éxito.")

    # ==========================================
    # MODO 2: PROCESAMIENTO MANUAL POR HOJA
    # ==========================================
    with st.expander("🛠️ Modo Manual (Por si falla el automático)"):
        col_hoja, col_fila = st.columns(2)
        hoja_seleccionada = col_hoja.selectbox("Selecciona hoja:", sheet_names)
        fila_titulos = col_fila.number_input("Fila Títulos:", min_value=0, max_value=20, value=2)

        df_raw = pd.read_csv(xls, skiprows=fila_titulos) if es_csv else pd.read_excel(xls, sheet_name=hoja_seleccionada, skiprows=fila_titulos)
        
        columnas_app = ['Codigo', 'Modelo', 'Descripcion', 'Precio_Lista', 'IVA', 'Herramienta', 'Color', 'Embalaje', 'CantidadPorCaja', 'UnidadPrecio']
        opciones_columnas = ["--- No usar ---"] + list(df_raw.columns)
        mapeo = {}
        
        cols = st.columns(3)
        for i, col_esperada in enumerate(columnas_app):
            with cols[i % 3]:
                index_default = 0
                for j, c_orig in enumerate(opciones_columnas):
                    if col_esperada.lower() in str(c_orig).lower() or (col_esperada == 'Precio_Lista' and 'precio' in str(c_orig).lower()):
                        index_default = j
                        break
                mapeo[col_esperada] = st.selectbox(f"'{col_esperada}':", options=opciones_columnas, index=index_default, key=col_esperada+"_manual")

        if st.button("➕ Limpiar y Añadir esta hoja"):
            df_limpio = pd.DataFrame()
            for col_esperada, col_origen in mapeo.items():
                df_limpio[col_esperada] = df_raw[col_origen] if col_origen != "--- No usar ---" else None 
                    
            df_limpio['Marca'] = marca_destino
            df_limpio['Hoja_Origen'] = hoja_seleccionada
            
            if df_limpio['Herramienta'].isnull().all() and 'Descripcion' in df_limpio.columns:
                df_limpio['Herramienta'] = df_limpio.apply(deducir_herramienta, axis=1)
            
            if 'Precio_Lista' in df_limpio.columns: df_limpio['Precio_Lista'] = df_limpio['Precio_Lista'].apply(limpiar_precio)
            if 'IVA' in df_limpio.columns: df_limpio['IVA'] = df_limpio['IVA'].apply(limpiar_iva)
            if 'Codigo' in df_limpio.columns: df_limpio['Codigo'] = df_limpio['Codigo'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
            
            df_limpio = df_limpio.dropna(subset=['Codigo', 'Descripcion'], how='all')
            st.session_state.datos_acumulados = pd.concat([st.session_state.datos_acumulados, df_limpio], ignore_index=True)
            st.success("✅ Hoja añadida manualmente.")

# --- EXPORTACIÓN FINAL ---
if not st.session_state.datos_acumulados.empty:
    st.markdown("---")
    st.subheader("📦 Catálogo Final Acumulado (Listo para app.py)")
    st.dataframe(st.session_state.datos_acumulados.head(10), use_container_width=True)
    st.info(f"Total de productos unificados: **{len(st.session_state.datos_acumulados)}**")
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        st.session_state.datos_acumulados.to_excel(writer, index=False, sheet_name='Productos')
    
    st.download_button(
        label=f"⬇️ Descargar Archivo Final ({archivo_salida})",
        data=output.getvalue(),
        file_name=archivo_salida,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True
    )
