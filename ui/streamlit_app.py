# --- SECCIÓN FINAL: BARRIDA Y DESCARGA ---
if not st.session_state.datos_acumulados.empty:
    st.markdown("---")
    st.subheader("🧹 Catálogo Final Acumulado y Optimizado")
    
    df_final = st.session_state.datos_acumulados.copy()

    # 1. Eliminar Códigos Fantasma (Subtítulos o basura): El código NO debe contener letras
    df_final = df_final[~df_final['Codigo'].astype(str).str.contains(r'[a-zA-Z]', na=False)]
    
    # 2. Normalizar Marcas (Para que los filtros de app.py funcionen perfecto)
    df_final['Marca'] = df_final['Marca'].astype(str).str.upper().strip()
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
    
    # --- AUTO-SEPARACIÓN Y DESCARGA POR MARCA ---
    st.markdown("### 📥 Descargar Archivos Separados")
    st.write("El sistema detectó las siguientes marcas y separó los archivos para tu sistema de pedidos:")
    
    marcas_detectadas = df_final['Marca'].dropna().unique()
    
    # Crear columnas dinámicas según la cantidad de marcas encontradas
    cols_descarga = st.columns(len(marcas_detectadas))
    
    for idx, marca_actual in enumerate(marcas_detectadas):
        # Filtrar solo los productos de esta marca
        df_marca = df_final[df_final['Marca'] == marca_actual]
        
        # Nombrar el archivo exactamente como lo pide app.py
        nombre_archivo = f"{marca_actual}_Limpia.xlsx"
        
        # Generar el Excel en memoria
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_marca.to_excel(writer, index=False, sheet_name='Productos')
        
        # Crear su botón de descarga
        with cols_descarga[idx]:
            st.download_button(
                label=f"⬇️ Descargar {nombre_archivo} \n({len(df_marca)} productos)",
                data=output.getvalue(),
                file_name=nombre_archivo,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True
            )
