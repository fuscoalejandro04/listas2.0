import streamlit as st
import pandas as pd
import io
import re
import unicodedata

st.set_page_config(page_title="Procesador Mágico de Listas", layout="wide", page_icon="🪄")

# --- FUNCIONES DE LIMPIEZA MÁGICA ---
def normalizar_texto(texto):
    if pd.isna(texto): return ""
    return unicodedata.normalize('NFKD', str(texto)).encode('ASCII', 'ignore').decode('utf-8').lower().strip()

def extraer_herramienta(descripcion):
    texto = str(descripcion).upper()
    match = re.split(r'(\d+|\||-|\bW\b|\bV\b|\bBARES\b|\bRPM\b|\bA BATERÍA\b|\bMM\b|\bCM\b)', texto)
    if match:
        herramienta = match[0].strip()
        herramienta = herramienta.replace('ELÉCTRICO', 'ELÉCTRICA')
        return herramienta
    return texto.strip()

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

# --- INTERFAZ ---
st.title("🪄 Procesador Mágico Multihoja")
st.markdown("Extrae, limpia y unifica listas de proveedores automáticamente para obtener un catálogo perfecto.")

marca_destino = st.selectbox("¿A qué marca pertenece este catálogo?", ["Einhell", "KWB", "Fijaciones", "Penosil", "Otra"])
archivo_salida = f"{marca_destino}_Limpia.xlsx" if marca_destino != "Otra" else "Productos_Limpia.xlsx"

uploaded_file = st.file_uploader("📂 Sube el Excel original del proveedor (ej. Lista EINHELL Y KWB...)", type=['xlsx', 'xls', 'csv'])

if uploaded_file:
    es_csv = uploaded_file.name.endswith('.csv')
    xls = uploaded_file if es_csv else pd.ExcelFile(uploaded_file)
    sheet_names = ["Hoja CSV"] if es_csv else xls.sheet_names

    st.markdown("---")
    
    if st.button(f"⚡ Procesar TODO el Excel Automáticamente", type="primary", use_container_width=True):
        with st.spinner("Escaneando hojas, extrayendo herramientas y limpiando precios..."):
            datos_finales = []
            hojas_procesadas = 0
            
            for sheet in sheet_names:
                # 1. Encontrar la fila de encabezados correcta (Búsqueda estricta)
                df_temp = pd.read_csv(xls, nrows=15, header=None) if es_csv else pd.read_excel(xls, sheet_name=sheet, nrows=15, header=None)
                fila_header = -1
                
                for idx, row in df_temp.iterrows():
                    # Analizamos celda por celda para no confundirnos con títulos largos
                    celdas_limpias = [normalizar_texto(x) for x in row.values]
                    if any(c in ['codigo', 'código', 'articulo', 'artículo'] for c in celdas_limpias):
                        fila_header = idx
                        break
                
                if fila_header == -1: continue # Salta portadas vacías (Lanzamientos, Combos, etc)
                
                # 2. Leer la hoja limpia a partir de la fila detectada
                df_raw = pd.read_csv(xls, skiprows=fila_header) if es_csv else pd.read_excel(xls, sheet_name=sheet, skiprows=fila_header)
                df_limpio = pd.DataFrame()
                
                # 3. Mapeo Inteligente
                cols_raw_norm = {normalizar_texto(c): c for c in df_raw.columns}
                
                # Codigo
                col_cod = next((c for n, c in cols_raw_norm.items() if n in ['codigo', 'articulo']), None)
                df_limpio['Codigo'] = df_raw[col_cod] if col_cod else None
                
                # Modelo
                col_mod = next((c for n, c in cols_raw_norm.items() if 'modelo' in n or 'nombre' in n), None)
                df_limpio['Modelo'] = df_raw[col_mod] if col_mod else None
                
                # Descripción
                col_desc = next((c for n, c in cols_raw_norm.items() if 'descrip' in n), None)
                df_limpio['Descripcion'] = df_raw[col_desc] if col_desc else None
                
                # Precio
                col_precio = next((c for n, c in cols_raw_norm.items() if 'precio' in n and 'sugerido' not in n), None)
                df_limpio['Precio_Lista'] = df_raw[col_precio] if col_precio else 0.0
                
                # IVA
                col_iva = next((c for n, c in cols_raw_norm.items() if 'iva' in n), None)
                df_limpio['IVA'] = df_raw[col_iva] if col_iva else 0.21

                # 4. Magia de Limpieza
                df_limpio['Hoja_Origen'] = sheet
                df_limpio['Marca'] = marca_destino
                
                # Extraer Herramienta
                df_limpio['Herramienta'] = df_limpio['Descripcion'].apply(extraer_herramienta)
                
                # Formatear números
                df_limpio['Precio_Lista'] = df_limpio['Precio_Lista'].apply(limpiar_precio)
                df_limpio['IVA'] = df_limpio['IVA'].apply(limpiar_iva)
                
                # Limpiar Códigos
                df_limpio = df_limpio.dropna(subset=['Codigo'], how='all')
                df_limpio['Codigo'] = df_limpio['Codigo'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                
                if not df_limpio.empty:
                    datos_finales.append(df_limpio)
                    hojas_procesadas += 1

            # 5. Unificar todo
            if datos_finales:
                df_final = pd.concat(datos_finales, ignore_index=True)
                
                # ORDENAR COLUMNAS EXACTAMENTE COMO EN 'Einhell_Limpia.xlsx'
                columnas_ordenadas = ['Codigo', 'Herramienta', 'Modelo', 'Descripcion', 'Precio_Lista', 'IVA', 'Hoja_Origen', 'Marca']
                for col in columnas_ordenadas:
                    if col not in df_final.columns:
                        df_final[col] = None
                df_final = df_final[columnas_ordenadas]

                st.success(f"✅ ¡Magia Terminada! Se combinaron {hojas_procesadas} hojas con más de {len(df_final)} productos.")
                
                st.subheader("📦 Resultado Final")
                st.dataframe(df_final.head(15), use_container_width=True)
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_final.to_excel(writer, index=False, sheet_name='Productos')
                
                col1, col2 = st.columns([1, 2])
                with col1:
                    st.download_button(
                        label=f"⬇️ Descargar {archivo_salida}",
                        data=output.getvalue(),
                        file_name=archivo_salida,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary",
                        use_container_width=True
                    )
            else:
                st.error("No se encontraron datos procesables en el archivo.")
