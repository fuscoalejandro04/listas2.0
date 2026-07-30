"""
Módulo de Importadores - Adaptadores para leer datos desde diferentes fuentes.
Soporte para Excel con encabezados en filas no estándar (detección automática).
"""
import pandas as pd
import io
import re
import numpy as np
from typing import Dict, List, Union, Optional
from pathlib import Path
from backend.domain.taxonomy import TAXONOMY


class Importer:
    """Importador que detecta automaticamente la fila de encabezados en cada hoja."""

    @staticmethod
    def read(file_path: Union[str, Path]) -> pd.DataFrame:
        path = Path(file_path)
        if path.suffix in ['.xlsx', '.xls']:
            return Importer._read_excel_all_sheets(path)
        elif path.suffix == '.csv':
            return pd.read_csv(path, encoding='utf-8', sep=None, engine='python')
        else:
            raise ValueError(f"Formato no soportado: {path.suffix}")

    @staticmethod
    def read_from_bytes(data: bytes, filename: str) -> pd.DataFrame:
        if filename.endswith('.xlsx') or filename.endswith('.xls'):
            return Importer._read_excel_all_sheets_from_bytes(data)
        elif filename.endswith('.csv'):
            return pd.read_csv(io.BytesIO(data), encoding='utf-8', sep=None, engine='python')
        else:
            raise ValueError(f"Formato no soportado: {filename}")

    @staticmethod
    def _read_excel_all_sheets(file_path: Path) -> pd.DataFrame:
        sheets_dict = pd.read_excel(file_path, sheet_name=None, header=None,
                                    engine='openpyxl' if file_path.suffix == '.xlsx' else 'xlrd')
        return Importer._combine_sheets_with_auto_header(sheets_dict)

    @staticmethod
    def _read_excel_all_sheets_from_bytes(data: bytes) -> pd.DataFrame:
        sheets_dict = pd.read_excel(io.BytesIO(data), sheet_name=None, header=None, engine='openpyxl')
        return Importer._combine_sheets_with_auto_header(sheets_dict)

    @staticmethod
    def _combine_sheets_with_auto_header(sheets_dict: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        Procesa cada hoja: detecta la fila de encabezados, limpia nombres,
        extrae los datos y los concatena en un único DataFrame.
        🔥 MODIFICADO: Rescata el último título de la columna 0 antes del header
        y lo inserta como primera fila para que el PipelineProcessor pueda heredarlo.
        """
        all_dfs = []
        for sheet_name, df_raw in sheets_dict.items():
            try:
                if df_raw.empty:
                    continue

                # 1. Detectar la fila de encabezados en esta hoja
                header_row = Importer._detect_header_row(df_raw)
                if header_row is None:
                    header_row = 0

                # 🔥 RESCATE DEL TÍTULO (último valor no vacío en columna 0 antes del header)
                last_title = None
                for idx in range(header_row):
                    val = df_raw.iloc[idx, 0]
                    if pd.notna(val) and str(val).strip():
                        last_title = str(val).strip()

                # 2. Extraer encabezados y datos
                headers = df_raw.iloc[header_row].astype(str).str.strip().tolist()
                data_rows = df_raw.iloc[header_row + 1:].copy()
                data_rows.columns = headers

                # 3. Limpiar nombres de columnas (con protección extra)
                clean_headers = Importer._clean_column_names(headers)
                data_rows.columns = clean_headers

                # 4. Eliminar filas completamente vacías
                data_rows = data_rows.dropna(how='all')
                if data_rows.empty:
                    continue

                # 🔥 INYECCIÓN DEL TÍTULO HUÉRFANO COMO PRIMERA FILA
                if last_title:
                    # Crear una fila con el título en la primera columna y NaN en el resto
                    new_row = {col: np.nan for col in data_rows.columns}
                    new_row[data_rows.columns[0]] = last_title
                    new_df = pd.DataFrame([new_row])
                    data_rows = pd.concat([new_df, data_rows], ignore_index=True)

                # 5. Añadir columna con el nombre de la hoja
                data_rows['hoja_origen'] = sheet_name
                all_dfs.append(data_rows)

            except Exception as e:
                # Registrar el error de esta hoja y continuar
                print(f"⚠️ Error al procesar la hoja '{sheet_name}': {e}")
                # Re-lanzar para que el importador lo capture y lo muestre en la UI
                raise ValueError(f"Hoja '{sheet_name}': {str(e)}")

        if not all_dfs:
            raise ValueError("No se encontraron hojas con datos válidos.")

        return pd.concat(all_dfs, ignore_index=True)

    @staticmethod
    def _detect_header_row(df: pd.DataFrame) -> Optional[int]:
        """
        Detecta la fila de encabezados usando una heurística avanzada.
        Retorna el índice de la fila más probable.
        🔥 Protegido contra valores float en las celdas.
        """
        best_score = -1
        best_row = 0

        # Palabras clave que suelen aparecer en encabezados
        keywords = set([
            'codigo', 'código', 'sku', 'modelo', 'descripción', 'descripcion',
            'precio', 'precio_lista', 'pvp', 'iva', 'ean', 'marca', 'categoría', 'categoria',
            'nombre', 'artículo', 'articulo', 'detalle', 'denominación', 'denominacion',
            'cantidad', 'unidad', 'peso', 'alto', 'ancho', 'profundidad', 'color',
            'talla', 'tamaño', 'stock', 'inventario', 'proveedor', 'fabricante'
        ])

        for row_idx in range(min(50, len(df))):
            try:
                # 🔥 Convertir TODA la fila a string ANTES de cualquier operación
                row_values = df.iloc[row_idx].astype(str).str.strip()
                # Filtrar valores vacíos
                non_empty = [v for v in row_values if v and v not in ['nan', 'none', '']]
                if len(non_empty) == 0:
                    continue

                # 1. Porcentaje de celdas no vacías
                non_empty_ratio = len(non_empty) / len(row_values)

                # 2. Contar palabras clave y números
                keyword_count = 0
                numeric_count = 0
                for val in non_empty:
                    val_lower = val.lower()
                    # Palabras clave
                    for k in keywords:
                        if k in val_lower:
                            keyword_count += 1
                            break
                    # Números (removiendo puntos y comas)
                    if re.match(r'^[0-9]+$', val_lower.replace('.', '').replace(',', '').strip()):
                        numeric_count += 1

                keyword_ratio = keyword_count / len(non_empty) if len(non_empty) > 0 else 0
                numeric_penalty = numeric_count / len(non_empty) if len(non_empty) > 0 else 0
                text_ratio = 1 - numeric_penalty

                # Bonus por palabras muy relevantes
                bonus = 0
                for val in non_empty:
                    val_lower = val.lower()
                    if 'ean' in val_lower or 'código' in val_lower or 'codigo' in val_lower:
                        bonus += 3
                    if 'precio' in val_lower or 'pvp' in val_lower:
                        bonus += 2

                # Penalizar si los valores son muy largos (probable descripción)
                avg_len = sum(len(v) for v in non_empty) / len(non_empty) if len(non_empty) > 0 else 0
                length_penalty = 1 if avg_len > 50 else 0

                # Puntuación final
                score = (non_empty_ratio * 2) + (keyword_ratio * 5) + (text_ratio * 2) + bonus - (length_penalty * 2)

                if score > best_score:
                    best_score = score
                    best_row = row_idx

            except Exception:
                # Si falla el procesamiento de esta fila, la ignoramos
                continue

        # Si la mejor puntuación es muy baja, usar fila 0
        if best_score < 1.0:
            return 0

        return best_row

    @staticmethod
    def _clean_column_names(headers: List[str]) -> List[str]:
        """
        Limpia nombres de columnas: sin tildes, espacios reemplazados por guiones bajos, minúsculas.
        🔥 Protegido: cada elemento se convierte a string antes de cualquier operación.
        """
        cleaned = []
        for h in headers:
            try:
                # 🔥 Convertir a string ANTES de cualquier operación
                h_str = str(h).strip() if h is not None else ""
                if not h_str:
                    h_str = f"columna_{len(cleaned)}"
                else:
                    # Eliminar caracteres especiales, pero mantener letras y números
                    h_str = re.sub(r'[^a-zA-Z0-9áéíóúñü\s]', '', h_str)
                    h_str = h_str.replace(' ', '_').lower()
                    # Eliminar tildes
                    h_str = Importer._normalize_text(h_str)
                    # Eliminar múltiples guiones bajos
                    h_str = re.sub(r'_+', '_', h_str)
                    # Limpiar guiones al inicio o final
                    h_str = h_str.strip('_')
                    if not h_str:
                        h_str = f"columna_{len(cleaned)}"
                cleaned.append(h_str)
            except Exception as e:
                # Si falla, asignar nombre genérico
                cleaned.append(f"columna_{len(cleaned)}")
        return cleaned

    @staticmethod
    def _normalize_text(text: str) -> str:
        """
        Elimina tildes y convierte a minúsculas para comparación.
        🔥 Protegido: si recibe float, lo convierte a string.
        """
        try:
            # Convertir a string por si acaso
            text_str = str(text) if text is not None else ""
            if not text_str:
                return ""
            import unicodedata
            text_str = text_str.lower()
            nfkd = unicodedata.normalize('NFKD', text_str)
            return "".join(c for c in nfkd if not unicodedata.combining(c))
        except Exception:
            return ""
