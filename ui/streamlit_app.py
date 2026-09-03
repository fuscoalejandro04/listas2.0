import streamlit as st
import pandas as pd
import io
import unicodedata

st.set_page_config(page_title="Procesador Multihoja", layout="wide", page_icon="⚙️")

# --- FUNCIONES CENTRALES ---
def normalizar_texto(texto):
    """Quita tildes y pasa a minúsculas para comparar columnas sin errores."""
    if pd.isna(texto): return ""
    texto = str(texto)
    return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8').lower()

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
    """ESTA ES LA FUNCIÓN QUE REEMPLAZA A LA IA PARA AGRUPAR CATEGORÍAS"""
    texto = str(row.get('Descripcion', '')) + " " + str(row.get('Modelo', ''))
    texto = normalizar_texto(texto)
    
    # 1. Agrupar Familia
    cat = "Herramienta General"
    if any(x in texto for x in ['taladro', 'atornillador', 'llave de impacto']): cat = "Taladro / Atornillador"
    elif any(x in texto for x in ['amoladora', 'pulidora', 'lijadora']): cat = "Amoladora / Lijadora"
    elif any(x in texto for x in ['sierra', 'caladora', 'ingleteadora', 'sensitiva']): cat = "Sierras"
    elif 'rotomartillo' in texto or 'martillo' in texto: cat = "Rotomartillo"
    elif 'compresor' in texto: cat = "Compresor"
    elif 'aspiradora' in texto or 'hidrolavadora' in texto: cat = "Limpieza"
    elif any(x in texto for x in ['motosierra', 'cortacesped', 'bordeadora', 'desmalezadora', 'soplador']): cat = "Jardín"
    elif any(x in texto for x in ['bateria', 'cargador', 'starter kit']): cat = "Baterías y Cargadores"
    elif any(x in texto for x in ['mecha', 'disco', 'punta', 'accesorio', 'hoja']): cat = "Accesorios"

    # 2. Agrupar Alimentación
    alim = ""
    if any(x in texto for x in ['inalambric', 'bateria', '18v', '36v', 'li-ion']): alim = "Inalámbrica"
    elif any(x in texto for x in ['electric', '220v']): alim = "Eléctrica"
    
    return f"{cat} {alim}".strip()

# --- INICIALIZAR MEMORIA ---
if 'datos_acumulados' not in st.session_state:
    st.session_state.datos_acumulados = pd.DataFrame()

st.title("⚙️ Procesador y Limpiador de Listas de Precios")

# --- CONFIGURACIÓN ---
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
    # MODO 1: AUTOMÁTICO
    # ==========================================
    st.subheader("🚀 Modo Automático")
    if st.button(f"⚡ Procesar TODO el archivo automáticamente", type="primary", use_container_width=True):
        with st.spinner("Procesando..."):
            hojas_procesadas = 0
            
            for sheet in sheet_names:
                df_temp = pd.read_csv(xls, nrows=15, header=None) if es_csv else pd.read_excel(xls, sheet_name=sheet, nrows=15, header=None)
                
                # Buscar dónde están los títulos (ignorar tildes)
                fila_header = -1
                for idx, row in df_temp.iterrows():
                    row_str = normalizar_texto(" ".join([str(x) for x in row.values]))
                    if "codigo" in row_str or "precio" in row_str:
                        fila_header = idx
                        break
                
                if fila_header == -1: continue # Salta hojas vacías (como Lanzamientos)
                
                df_raw = pd.read_csv(xls, skiprows=fila_header) if es_csv else pd.read_excel(xls, sheet_name=sheet, skiprows=fila_header)
                
                df_limpio = pd.DataFrame()
                columnas_app = ['Codigo', 'Modelo', 'Descripcion', 'Precio_Lista', 'IVA', 'Herramienta', 'Color', 'Embalaje', 'CantidadPorCaja', 'UnidadPrecio']
                
                # Mapeo inteligente sin importar tildes o mayúsculas
                for col_esp in columnas_app:
                    col_encontrada = None
                    c_esp_norm = normalizar_texto(col_esp)
                    
                    for c_orig in df_raw.columns:
                        c_orig_norm = normalizar_texto(c_orig)
                        # Reglas específicas de coincidencia
                        if c_esp_norm == 'precio_lista' and 'precio' in c_orig_norm:
                            col_encontrada = c_orig; break
                        elif c_esp_norm == 'descripcion' and 'descrip' in c_orig_norm:
                            col_encontrada = c_orig; break
                        elif c_esp_norm in c_orig_norm:
                            col_encontrada = c_orig; break
                            
                    df_limpio[col_esp] = df_raw[col_encontrada] if col_encontrada else None

                # Enriquecimiento y Limpieza
                df_limpio['Marca'] = marca_destino
                df_limpio['Hoja_Origen'] = sheet
                
                if 'Descripcion' in df_limpio.columns:
                    df_limpio['Herramienta'] = df_limpio.apply(deducir_herramienta, axis=1)
                
                if 'Precio_Lista' in df_limpio.columns: df_limpio['Precio_Lista'] = df_limpio['Precio_Lista'].apply(limpiar_precio)
                if 'IVA' in df_limpio.columns: df_limpio['IVA'] = df_limpio['IVA'].apply(limpiar_iva)
                if 'Codigo' in df_limpio.columns: df_limpio['Codigo'] = df_limpio['Codigo'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                
                # Descartar filas que no tengan código ni descripción
                df_limpio = df_limpio.dropna(subset=['Codigo', 'Descripcion'], how='all')
                
                if not df_limpio.empty:
                    st.session_state.datos_acumulados = pd.concat([st.session_state.datos_acumulados, df_limpio], ignore_index=True)
                    hojas_procesadas += 1
                
            st.success(f"✅ ¡Proceso Terminado! Se combinaron {hojas_procesadas} hojas con éxito.")

    # ==========================================
    # MODO 2: MANUAL
    # ==========================================
    with st.expander("🛠️ Modo Manual (Ver y mapear columna por columna)"):
        col_hoja, col_fila = st.columns(2)
        hoja_seleccionada = col_hoja.selectbox("Selecciona hoja:", sheet_names)
        fila_titulos = col_fila.number_input("Fila Títulos (Donde dice 'Código'):", min_value=0, max_value=20, value=2)

        df_raw = pd.read_csv(xls, skiprows=fila_titulos) if es_csv else pd.read_excel(xls, sheet_name=hoja_seleccionada, skiprows=fila_titulos)
        
        st.markdown("**Vista previa de la hoja (Usa esto para saber qué elegir abajo):**")
        st.dataframe(df_raw.head(3), use_container_width=True)
        
        columnas_app = ['Codigo', 'Modelo', 'Descripcion', 'Precio_Lista', 'IVA', 'Herramienta', 'Color', 'Embalaje', 'CantidadPorCaja', 'UnidadPrecio']
        opciones_columnas = ["--- No usar ---"] + list(df_raw.columns)
        mapeo = {}
        
        cols = st.columns(3)
        for i, col_esperada in enumerate(columnas_app):
            with cols[i % 3]:
                index_default = 0
                for j, c_orig in enumerate(opciones_columnas):
                    c_orig_norm = normalizar_texto(c_orig)
                    c_esp_norm = normalizar_texto(col_esperada)
                    if c_esp_norm in c_orig_norm or (c_esp_norm == 'precio_lista' and 'precio' in c_orig_norm) or (c_esp_norm == 'descripcion' and 'descrip' in c_orig_norm):
                        index_default = j
                        break
                mapeo[col_esperada] = st.selectbox(f"'{col_esperada}':", options=opciones_columnas, index=index_default, key=col_esperada+"_manual")

        if st.button("➕ Limpiar y Añadir esta hoja"):
            df_limpio = pd.DataFrame()
            for col_esperada, col_origen in mapeo.items():
                df_limpio[col_esperada] = df_raw[col_origen] if col_origen != "--- No usar ---" else None 
                    
            df_limpio['Marca'] = marca_destino
            df_limpio['Hoja_Origen'] = hoja_seleccionada
            
            if 'Descripcion' in df_limpio.columns:
                df_limpio['Herramienta'] = df_limpio.apply(deducir_herramienta, axis=1)
            
            if 'Precio_Lista' in df_limpio.columns: df_limpio['Precio_Lista'] = df_limpio['Precio_Lista'].apply(limpiar_precio)
            if 'IVA' in df_limpio.columns: df_limpio['IVA'] = df_limpio['IVA'].apply(limpiar_iva)
            if 'Codigo' in df_limpio.columns: df_limpio['Codigo'] = df_limpio['Codigo'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
            
            df_limpio = df_limpio.dropna(subset=['Codigo', 'Descripcion'], how='all')
            if not df_limpio.empty:
                st.session_state.datos_acumulados = pd.concat([st.session_state.datos_acumulados, df_limpio], ignore_index=True)
                st.success(f"✅ Hoja añadida manualmente ({len(df_limpio)} productos).")
            else:
                st.error("⚠️ La hoja resultó vacía. Revisa el mapeo de Código y Descripción.")

# ==========================================
# DESCARGA FINAL
# ==========================================
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
