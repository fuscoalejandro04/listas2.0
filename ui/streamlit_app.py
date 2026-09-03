import streamlit as st
import pandas as pd
import io
import re

st.set_page_config(page_title="Procesador Multihoja de Listas", layout="wide", page_icon="⚙️")

# 1. INICIALIZAR MEMORIA
if 'datos_acumulados' not in st.session_state:
    st.session_state.datos_acumulados = pd.DataFrame()

st.title("⚙️ Procesador y Limpiador de Listas de Precios")
st.markdown("Herramienta rápida y **100% determinista (Sin IA)** para adaptar listas de proveedores a la App de Gestión de Pedidos.")

# 2. CONFIGURACIÓN DE SALIDA (BARRA LATERAL)
st.sidebar.header("1. Configuración de Salida")
marca_destino = st.sidebar.selectbox("¿A qué marca pertenece este catálogo?", ["Einhell", "KWB", "Fijaciones", "Penosil", "Otra"])

# Determinar nombre exacto del archivo final esperado por app.py
nombres_archivo = {
    "Einhell": "Einhell_Limpia.xlsx",
    "KWB": "KWB_Limpia.xlsx",
    "Fijaciones": "Fijaciones_Limpia.xlsx",
    "Penosil": "Penosil_Limpia.xlsx",
    "Otra": "Productos_Limpia.xlsx"
}
archivo_salida = nombres_archivo[marca_destino]
st.sidebar.info(f"El archivo final se descargará como: **{archivo_salida}**")

if st.sidebar.button("🗑️ Vaciar Datos Acumulados", use_container_width=True):
    st.session_state.datos_acumulados = pd.DataFrame()
    st.rerun()

# 3. CARGA DE ARCHIVO Y SELECCIÓN DE HOJA
st.subheader("2. Cargar Excel del Proveedor y Seleccionar Hoja")
uploaded_file = st.file_uploader("Sube el archivo original", type=['xlsx', 'xls', 'csv'])

if uploaded_file:
    # Determinar si es CSV o Excel
    if uploaded_file.name.endswith('.csv'):
        sheet_names = ["Hoja CSV"]
        xls = uploaded_file
    else:
        xls = pd.ExcelFile(uploaded_file)
        sheet_names = xls.sheet_names

    st.markdown("---")
    col_hoja, col_fila = st.columns(2)
    
    # Selector de hoja
    hoja_seleccionada = col_hoja.selectbox("Selecciona la hoja a procesar (ej: TOOLS, JARDIN, ACCESORIOS):", sheet_names)
    
    # Ajuste de fila de títulos (Para saltar las filas vacías de la portada y evitar los 'Unnamed')
    fila_titulos = col_fila.number_input("Fila donde están los Títulos (Sube esto para quitar los 'Unnamed'):", min_value=0, max_value=20, value=2)

    # Leer la hoja específica saltando las filas indicadas
    if uploaded_file.name.endswith('.csv'):
        df_raw = pd.read_csv(xls, skiprows=fila_titulos)
    else:
        df_raw = pd.read_excel(xls, sheet_name=hoja_seleccionada, skiprows=fila_titulos)

    st.caption("Vista previa (Verifica que los nombres de las columnas se lean correctamente):")
    st.dataframe(df_raw.head(4), use_container_width=True)

    st.markdown("---")
    
    # 4. MAPEO DE COLUMNAS
    st.subheader("3. Mapeo de Columnas (Alinear con app.py)")
    st.write("Indica qué columna del Excel original corresponde a los campos que necesita la app.")
    
    columnas_app = ['Codigo', 'Modelo', 'Descripcion', 'Precio_Lista', 'IVA', 'Herramienta', 'Color', 'Embalaje', 'CantidadPorCaja', 'UnidadPrecio']
    opciones_columnas = ["--- No usar ---"] + list(df_raw.columns)
    mapeo = {}
    
    # Mostrar selectores en 3 columnas
    cols = st.columns(3)
    for i, col_esperada in enumerate(columnas_app):
        with cols[i % 3]:
            # Auto-seleccionar si el nombre coincide parcialmente
            index_default = 0
            for j, c_orig in enumerate(opciones_columnas):
                if col_esperada.lower() in str(c_orig).lower() or (col_esperada == 'Precio_Lista' and 'precio' in str(c_orig).lower()):
                    index_default = j
                    break
            mapeo[col_esperada] = st.selectbox(f"Columna para '{col_esperada}':", options=opciones_columnas, index=index_default, key=col_esperada)

    # 5. PROCESAMIENTO Y LIMPIEZA DE DATOS
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("➕ Limpiar y Añadir esta hoja al catálogo final", type="primary", use_container_width=True):
        df_limpio = pd.DataFrame()
        
        # A) Asignar las columnas mapeadas
        for col_esperada, col_origen in mapeo.items():
            if col_origen != "--- No usar ---":
                df_limpio[col_esperada] = df_raw[col_origen]
            else:
                df_limpio[col_esperada] = None 
                
        df_limpio['Marca'] = marca_destino
        df_limpio['Hoja_Origen'] = hoja_seleccionada
        
        # B) AUTODETECCIÓN DE HERRAMIENTA Y CATEGORÍA (Reemplaza la IA)
        if df_limpio['Herramienta'].isnull().all() and 'Descripcion' in df_limpio.columns:
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
                if any(x in texto for x in ['INALÁMBRIC', 'INALAMBRIC', 'BATERÍA', 'BATERIA', '18V', '36V', 'LI-ION']):
                    alim = "Inalámbrica"
                elif any(x in texto for x in ['ELÉCTRIC', 'ELECTRIC', '220V', ' 220 V']):
                    alim = "Eléctrica"
                
                return f"{cat} {alim}".strip()

            df_limpio['Herramienta'] = df_limpio.apply(deducir_herramienta, axis=1)

        # C) Limpieza estricta de Precios
        if 'Precio_Lista' in df_limpio.columns:
            def limpiar_precio(val):
                if pd.isna(val): return 0.0
                if isinstance(val, (int, float)): return float(val)
                # Quitar $, puntos de miles (asumiendo formato argentino), reemplazar coma por punto decimal
                val_str = str(val).replace('$', '').replace('.', '').replace(',', '.').strip()
                try: 
                    return float(val_str)
                except: 
                    return 0.0
            df_limpio['Precio_Lista'] = df_limpio['Precio_Lista'].apply(limpiar_precio)

        # D) Detección y Limpieza de IVA
        if 'IVA' in df_limpio.columns:
            def limpiar_iva(val):
                if pd.isna(val) or str(val).strip() == '': return 0.21
                val_str = str(val).replace('%', '').replace(',', '.').strip()
                try:
                    num = float(val_str)
                    return num / 100.0 if num > 1 else num # Convierte 21 o 10.5 a 0.21 o 0.105
                except:
                    return 0.21
            df_limpio['IVA'] = df_limpio['IVA'].apply(limpiar_iva)
        else:
            df_limpio['IVA'] = 0.21

        # E) Limpieza de Códigos
        if 'Codigo' in df_limpio.columns:
            df_limpio['Codigo'] = df_limpio['Codigo'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

        # F) Eliminar filas completamente vacías (donde Código y Descripción estén nulos)
        df_limpio = df_limpio.dropna(subset=['Codigo', 'Descripcion'], how='all')

        # Acumular datos en memoria
        st.session_state.datos_acumulados = pd.concat([st.session_state.datos_acumulados, df_limpio], ignore_index=True)
        st.success(f"✅ Se limpiaron y añadieron {len(df_limpio)} productos de la hoja '{hoja_seleccionada}'.")

# 6. EXPORTACIÓN FINAL
if not st.session_state.datos_acumulados.empty:
    st.markdown("---")
    st.subheader("📦 Catálogo Final Acumulado (Listo para app.py)")
    st.dataframe(st.session_state.datos_acumulados.head(10), use_container_width=True)
    st.info(f"Total de productos unificados: **{len(st.session_state.datos_acumulados)}**")
    
    # Generar el Excel en memoria
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        st.session_state.datos_acumulados.to_excel(writer, index=False, sheet_name='Productos')
    
    col_dl, col_space = st.columns([1, 2])
    with col_dl:
        st.download_button(
            label=f"⬇️ Descargar Archivo Final ({archivo_salida})",
            data=output.getvalue(),
            file_name=archivo_salida,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True
        )
    st.caption("Una vez descargado, colócalo en la misma carpeta que app.py y reemplaza el archivo viejo.")
