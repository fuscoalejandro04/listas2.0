import streamlit as st
import pandas as pd
import io
import re
import unicodedata

st.set_page_config(page_title="Procesador Automático Multihoja", layout="wide", page_icon="🪄")

# --- FUNCIONES DE LIMPIEZA MÁGICA ---
def normalizar_texto(texto):
    if pd.isna(texto): return ""
    return unicodedata.normalize('NFKD', str(texto)).encode('ASCII', 'ignore').decode('utf-8').lower().strip()

def deducir_herramienta(row):
    texto = str(row.get('Descripcion', '')) + " " + str(row.get('Modelo', ''))
    texto = normalizar_texto(texto)
    
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

if 'datos_acumulados' not in st.session_state:
    st.session_state.datos_acumulados = pd.DataFrame()

st.sidebar.header("1. Configuración de Salida")
marca_destino = st.sidebar.selectbox("Marca unificada del catálogo:", ["Einhell", "Fijaciones", "Penosil", "Otra"])
archivo_salida = f"{marca_destino}_Limpia.xlsx" if marca_destino != "Otra" else "Productos_Limpia.xlsx"

if st.sidebar.button("🗑️ Reiniciar / Borrar Memoria", use_container_width=True):
    st.session_state.datos_acumulados = pd.DataFrame()
    st.rerun()

st.title("🪄 Procesador Mágico Multihoja")
st.markdown("Sube tu lista y haz clic en el botón automático. Todos los productos (incluyendo KWB) se unificarán bajo la marca seleccionada.")

uploaded_file = st.file_uploader("📂 Sube el Excel original del proveedor", type=['xlsx', 'xls', 'csv'])

if uploaded_file:
    es_csv = uploaded_file.name.endswith('.csv')
    xls = uploaded_file if es_csv else pd.ExcelFile(uploaded_file)
    sheet_names = ["Hoja CSV"] if es_csv else xls.sheet_names

    st.markdown("---")
    
    if st.button(f"⚡ Procesar TODO el archivo automáticamente", type="primary", use_container_width=True):
        with st.spinner("Procesando las hojas y unificando marcas..."):
            datos_finales = []
            hojas_procesadas = 0
            
            for sheet in sheet_names:
                df_temp = pd.read_csv(xls, nrows=15, header=None) if es_csv else pd.read_excel(xls, sheet_name=sheet, nrows=15, header=None)
                
                fila_header = -1
                for idx, row in df_temp.iterrows():
                    celdas_limpias = [normalizar_texto(x) for x in row.values]
                    if any(c in ['codigo', 'código', 'articulo', 'artículo'] for c in celdas_limpias):
                        fila_header = idx
                        break
                
                if fila_header == -1: continue 
                
                df_raw = pd.read_csv(xls, skiprows=fila_header) if es_csv else pd.read_excel(xls, sheet_name=sheet, skiprows=fila_header)
                df_limpio = pd.DataFrame()
                
                cols_raw_norm = {normalizar_texto(c): c for c in df_raw.columns}
                
                col_cod = next((c for n, c in cols_raw_norm.items() if n in ['codigo', 'articulo']), None)
                df_limpio['Codigo'] = df_raw[col_cod] if col_cod else None
                
                col_mod = next((c for n, c in cols_raw_norm.items() if 'modelo' in n or 'nombre' in n), None)
                df_limpio['Modelo'] = df_raw[col_mod] if col_mod else None
                
                col_desc = next((c for n, c in cols_raw_norm.items() if 'descrip' in n), None)
                df_limpio['Descripcion'] = df_raw[col_desc] if col_desc else None
                
                col_precio = next((c for n, c in cols_raw_norm.items() if 'precio' in n and 'sugerido' not in n), None)
                df_limpio['Precio_Lista'] = df_raw[col_precio] if col_precio else 0.0
                
                col_iva = next((c for n, c in cols_raw_norm.items() if 'iva' in n), None)
                df_limpio['IVA'] = df_raw[col_iva] if col_iva else 0.21

                # FORZAR MARCA UNIFICADA
                df_limpio['Marca'] = marca_destino
                
                df_limpio['Hoja_Origen'] = sheet
                df_limpio['Herramienta'] = df_limpio.apply(deducir_herramienta, axis=1)
                df_limpio['Precio_Lista'] = df_limpio['Precio_Lista'].apply(limpiar_precio)
                df_limpio['IVA'] = df_limpio['IVA'].apply(limpiar_iva)
                
                df_limpio = df_limpio.dropna(subset=['Codigo'], how='all')
                df_limpio['Codigo'] = df_limpio['Codigo'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                
                if not df_limpio.empty:
                    datos_finales.append(df_limpio)
                    hojas_procesadas += 1

            if datos_finales:
                st.session_state.datos_acumulados = pd.concat(datos_finales, ignore_index=True)
                st.success(f"✅ ¡Proceso Automático Terminado! Se leyeron {hojas_procesadas} hojas con éxito.")

if not st.session_state.datos_acumulados.empty:
    st.markdown("---")
    st.subheader("🧹 Catálogo Final Unificado")
    
    df_final = st.session_state.datos_acumulados.copy()

    df_final = df_final[~df_final['Codigo'].astype(str).str.contains(r'[a-zA-Z]', na=False)]
    df_final['Marca'] = marca_destino
    
    df_final['Descripcion'] = df_final['Descripcion'].fillna(df_final['Modelo'])
    df_final['Modelo'] = df_final['Modelo'].fillna(df_final['Descripcion'])
    
    columnas_ordenadas = ['Codigo', 'Herramienta', 'Modelo', 'Descripcion', 'Precio_Lista', 'IVA', 'Hoja_Origen', 'Marca', 'Color', 'Embalaje', 'CantidadPorCaja', 'UnidadPrecio']
    for col in columnas_ordenadas:
        if col not in df_final.columns:
            df_final[col] = None
    df_final = df_final[columnas_ordenadas]
    
    st.dataframe(df_final.head(10), use_container_width=True)
    st.info(f"Total de productos 100% puros unificados bajo la marca '{marca_destino}': **{len(df_final)}**")
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_final.to_excel(writer, index=False, sheet_name='Productos')
    
    st.download_button(
        label=f"⬇️ Descargar Catálogo Completo ({archivo_salida})",
        data=output.getvalue(),
        file_name=archivo_salida,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary"
    )
