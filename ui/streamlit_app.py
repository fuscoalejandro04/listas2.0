import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Procesador de Listas de Precios", layout="wide")

st.title("⚙️ Procesador y Limpiador de Listas de Precios")
st.markdown("Herramienta rápida sin IA para adaptar listas de proveedores a la **App de Gestión de Pedidos**.")

# 1. Parámetros de Exportación
st.sidebar.header("1. Configuración de Salida")
marca_destino = st.sidebar.selectbox(
    "¿De qué marca es esta lista?", 
    ["Einhell", "KWB", "Fijaciones", "Penosil", "Otra"]
)

# Nombres exactos que espera app.py
nombres_archivo_salida = {
    "Einhell": "Einhell_Limpia.xlsx",
    "KWB": "KWB_Limpia.xlsx",
    "Fijaciones": "Fijaciones_Limpia.xlsx",
    "Penosil": "Penosil_Limpia.xlsx",
    "Otra": "Productos_Limpia.xlsx"
}
archivo_salida = nombres_archivo_salida[marca_destino]

st.sidebar.info(f"El archivo se exportará como: **{archivo_salida}** listos para app.py")

# 2. Carga de Archivo
st.subheader("2. Cargar Lista del Proveedor")
uploaded_file = st.file_uploader("Sube el Excel original del proveedor", type=['xlsx', 'xls', 'csv'])

if uploaded_file:
    # Leer archivo
    if uploaded_file.name.endswith('.csv'):
        df_raw = pd.read_csv(uploaded_file)
    else:
        df_raw = pd.read_excel(uploaded_file)
    
    st.success(f"Archivo cargado. {df_raw.shape[0]} filas x {df_raw.shape[1]} columnas.")
    
    with st.expander("Ver datos originales"):
        st.dataframe(df_raw.head(10))

    st.markdown("---")
    st.subheader("3. Mapeo de Columnas (Alinear con app.py)")
    st.write("Indica qué columna del Excel original corresponde a los campos obligatorios de la app de pedidos.")
    
    # Columnas que espera app.py
    columnas_app = ['Codigo', 'Modelo', 'Descripcion', 'Precio_Lista', 'Herramienta', 'Color', 'Embalaje', 'CantidadPorCaja', 'UnidadPrecio']
    
    cols = st.columns(3)
    mapeo = {}
    
    opciones_columnas = ["--- No usar ---"] + list(df_raw.columns)
    
    for i, col_esperada in enumerate(columnas_app):
        with cols[i % 3]:
            # Intentar auto-detectar
            index_default = 0
            for j, c_orig in enumerate(opciones_columnas):
                if col_esperada.lower() in c_orig.lower():
                    index_default = j
                    break
                    
            mapeo[col_esperada] = st.selectbox(f"Columna para '{col_esperada}':", options=opciones_columnas, index=index_default)
    
    # Configuraciones extra
    st.markdown("---")
    st.subheader("4. Limpieza de Precios e IVA")
    col_iva, col_hoja = st.columns(2)
    iva_default = col_iva.selectbox("IVA por defecto (generalmente 21%)", [0.21, 0.105])
    hoja_origen = col_hoja.text_input("Hoja de Origen (opcional)", value=marca_destino)

    if st.button("🚀 Procesar Lista y Generar Archivo Limpio", type="primary"):
        with st.spinner("Procesando datos..."):
            df_limpio = pd.DataFrame()
            
            # Aplicar el mapeo
            for col_esperada, col_origen in mapeo.items():
                if col_origen != "--- No usar ---":
                    df_limpio[col_esperada] = df_raw[col_origen]
                else:
                    df_limpio[col_esperada] = None # Llenar con None para que app.py no falle
            
            # Forzar campos obligatorios de app.py
            df_limpio['Marca'] = marca_destino
            df_limpio['IVA'] = iva_default
            df_limpio['Hoja_Origen'] = hoja_origen
            
            # Limpiar precios (quitar signos de dolar, comas, espacios y convertir a float)
            if 'Precio_Lista' in df_limpio.columns:
                def limpiar_precio(val):
                    if pd.isna(val): return 0.0
                    if isinstance(val, (int, float)): return float(val)
                    val = str(val).replace('$', '').replace('.', '').replace(',', '.').strip()
                    try: return float(val)
                    except: return 0.0
                
                df_limpio['Precio_Lista'] = df_limpio['Precio_Lista'].apply(limpiar_precio)

            # Limpiar Códigos (asegurar que sean string sin el .0 al final)
            if 'Codigo' in df_limpio.columns:
                df_limpio['Codigo'] = df_limpio['Codigo'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
            
            st.success("✅ Procesamiento completado.")
            
            st.subheader("Vista Previa de la Lista Optimizada")
            st.dataframe(df_limpio.head(15), use_container_width=True)
            
            # Exportar a Excel
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_limpio.to_excel(writer, index=False, sheet_name='Productos')
            
            st.download_button(
                label=f"📥 Descargar {archivo_salida}",
                data=output.getvalue(),
                file_name=archivo_salida,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )
            st.info("Paso final: Descarga este archivo, colócalo en la misma carpeta que tu app.py, y la app de pedidos lo leerá a la perfección.")
