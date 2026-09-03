import streamlit as st
import pandas as pd
import io
import unicodedata

st.set_page_config(page_title="Procesador Manual de Listas", layout="wide", page_icon="📝")

# --- FUNCIONES DE LIMPIEZA MÁGICA ---
def normalizar_texto(texto):
    if pd.isna(texto): return ""
    return unicodedata.normalize('NFKD', str(texto)).encode('ASCII', 'ignore').decode('utf-8').lower().strip()

def deducir_herramienta(row):
    """Categorizador Genérico: Agrupa por tipo y por alimentación"""
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

# --- MEMORIA DEL SISTEMA ---
if 'datos_acumulados' not in st.session_state:
    st.session_state.datos_acumulados = pd.DataFrame()
if 'hojas_procesadas' not in st.session_state:
    st.session_state.hojas_procesadas = []

# --- BARRA LATERAL ---
st.sidebar.header("1. Configuración de Salida")
marca_destino = st.sidebar.selectbox("Marca general del catálogo:", ["Einhell", "KWB", "Fijaciones", "Penosil", "Otra"])
archivo_salida = f"{marca_destino}_Limpia.xlsx" if marca_destino != "Otra" else "Productos_Limpia.xlsx"
st.sidebar.info(f"El archivo final será: **{archivo_salida}**")

if st.sidebar.button("🗑️ Reiniciar todo (Borrar memoria)", use_container_width=True):
    st.session_state.datos_acumulados = pd.DataFrame()
    st.session_state.hojas_procesadas = []
    st.rerun()

# --- ÁREA PRINCIPAL ---
st.title("📝 Procesador Guiado Hoja por Hoja")
st.markdown("Mapea tus columnas manualmente. Las hojas ya procesadas no se podrán volver a elegir.")

uploaded_file = st.file_uploader("📂 Sube el Excel original del proveedor", type=['xlsx', 'xls', 'csv'])

if uploaded_file:
    es_csv = uploaded_file.name.endswith('.csv')
    xls = uploaded_file if es_csv else pd.ExcelFile(uploaded_file)
    sheet_names = ["Hoja CSV"] if es_csv else xls.sheet_names

    # Filtrar hojas procesadas
    hojas_disponibles = [hoja for hoja in sheet_names if hoja not in st.session_state.hojas_procesadas]

    st.markdown("---")

    if not hojas_disponibles:
        st.success("🎉 ¡Todas las hojas han sido procesadas! Puedes descargar el catálogo final abajo.")
    else:
        st.subheader("2. Seleccionar y Mapear Hoja")
        
        col_hoja, col_fila = st.columns(2)
        hoja_seleccionada = col_hoja.selectbox("Selecciona la hoja a procesar:", hojas_disponibles)
        
        # Detección de fila de títulos sugerida
        df_temp = pd.read_csv(xls, nrows=15, header=None) if es_csv else pd.read_excel(xls, sheet_name=hoja_seleccionada, nrows=15, header=None)
        fila_header_sugerida = 0
        for idx, row in df_temp.iterrows():
            celdas_limpias = [normalizar_texto(x) for x in row.values]
            if any(c in ['codigo', 'código', 'articulo', 'artículo'] for c in celdas_limpias):
                fila_header_sugerida = idx
                break
                
        fila_titulos = col_fila.number_input("Fila donde están los Títulos:", min_value=0, max_value=20, value=fila_header_sugerida)

        df_raw = pd.read_csv(xls, skiprows=fila_titulos) if es_csv else pd.read_excel(xls, sheet_name=hoja_seleccionada, skiprows=fila_titulos)

        st.caption("Vista previa:")
        st.dataframe(df_raw.head(3), use_container_width=True)
        st.markdown("---")
        
        # --- MAPEO ---
        st.subheader("3. Mapeo de Columnas")
        columnas_app = ['Codigo', 'Marca', 'Modelo', 'Descripcion', 'Precio_Lista', 'IVA', 'Herramienta', 'Color', 'Embalaje', 'CantidadPorCaja', 'UnidadPrecio']
        opciones_columnas = ["--- No usar ---"] + list(df_raw.columns)
        mapeo = {}
        
        cols = st.columns(4)
        for i, col_esperada in enumerate(columnas_app):
            with cols[i % 4]:
                index_default = 0
                c_esp_norm = normalizar_texto(col_esperada)
                for j, c_orig in enumerate(opciones_columnas):
                    c_orig_norm = normalizar_texto(c_orig)
                    if c_esp_norm in c_orig_norm or (c_esp_norm == 'precio_lista' and 'precio' in c_orig_norm) or (c_esp_norm == 'descripcion' and 'descrip' in c_orig_norm):
                        index_default = j
                        break
                mapeo[col_esperada] = st.selectbox(f"'{col_esperada}':", options=opciones_columnas, index=index_default, key=col_esperada)

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button(f"➕ Limpiar y Añadir '{hoja_seleccionada}' al Catálogo", type="primary", use_container_width=True):
            df_limpio = pd.DataFrame()
            
            # 1. Aplicar mapeo
            for col_esperada, col_origen in mapeo.items():
                if col_origen != "--- No usar ---":
                    df_limpio[col_esperada] = df_raw[col_origen]
                else:
                    df_limpio[col_esperada] = None 
            
            # 2. Respetar la MARCA mapeada o poner la general
            if mapeo['Marca'] == "--- No usar ---":
                df_limpio['Marca'] = marca_destino
            else:
                df_limpio['Marca'] = df_limpio['Marca'].fillna(marca_destino)

            df_limpio['Hoja_Origen'] = hoja_seleccionada
            
            # 3. Categorización Genérica
            df_limpio['Herramienta'] = df_limpio.apply(deducir_herramienta, axis=1)

            # 4. Limpieza Numérica
            if mapeo['Precio_Lista'] != "--- No usar ---": 
                df_limpio['Precio_Lista'] = df_limpio['Precio_Lista'].apply(limpiar_precio)
            if mapeo['IVA'] != "--- No usar ---": 
                df_limpio['IVA'] = df_limpio['IVA'].apply(limpiar_iva)
            else:
                df_limpio['IVA'] = 0.21
            
            # 5. Limpieza de Códigos
            if mapeo['Codigo'] != "--- No usar ---":
                df_limpio = df_limpio.dropna(subset=['Codigo'], how='all')
                df_limpio['Codigo'] = df_limpio['Codigo'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

            if not df_limpio.empty:
                st.session_state.datos_acumulados = pd.concat([st.session_state.datos_acumulados, df_limpio], ignore_index=True)
                st.session_state.hojas_procesadas.append(hoja_seleccionada)
                st.rerun()
            else:
                st.error("⚠️ La hoja resultó vacía. Asegúrate de mapear bien la columna Código.")

# --- SECCIÓN FINAL: BARRIDA Y DESCARGA ---
if not st.session_state.datos_acumulados.empty:
    st.markdown("---")
    st.subheader("🧹 Catálogo Final Acumulado y Optimizado")
    
    df_final = st.session_state.datos_acumulados.copy()

    # 1. Eliminar Códigos Fantasma (Subtítulos o basura): El código NO debe contener letras
    df_final = df_final[~df_final['Codigo'].str.contains(r'[a-zA-Z]', na=False)]
    
    # 2. Normalizar Marcas (Para que los filtros de app.py funcionen perfecto)
    df_final['Marca'] = df_final['Marca'].astype(str).str.upper()
    df_final['Marca'] = df_final['Marca'].replace({'EINHELL': 'Einhell', 'KWB': 'KWB'})
    
    # 3. Rellenar Vacíos Cruzados (Para que el buscador de app.py nunca falle)
    df_final['Descripcion'] = df_final['Descripcion'].fillna(df_final['Modelo'])
    df_final['Modelo'] = df_final['Modelo'].fillna(df_final['Descripcion'])
    
    # 4. Ordenar columnas como en Einhell_Limpia
    columnas_ordenadas = ['Codigo', 'Herramienta', 'Modelo', 'Descripcion', 'Precio_Lista', 'IVA', 'Hoja_Origen', 'Marca', 'Color', 'Embalaje', 'CantidadPorCaja', 'UnidadPrecio']
    for col in columnas_ordenadas:
        if col not in df_final.columns:
            df_final[col] = None
    df_final = df_final[columnas_ordenadas]
    
    st.dataframe(df_final.head(10), use_container_width=True)
    st.info(f"Total de productos 100% puros: **{len(df_final)}** | Hojas procesadas: **{len(st.session_state.hojas_procesadas)}**")
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_final.to_excel(writer, index=False, sheet_name='Productos')
    
    col1, col2 = st.columns([1, 2])
    with col1:
        st.download_button(
            label=f"⬇️ Descargar Archivo Optimizado ({archivo_salida})",
            data=output.getvalue(),
            file_name=archivo_salida,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True
        )
