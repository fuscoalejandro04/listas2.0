"""
Módulo de Importadores - Adaptadores para leer datos desde diferentes fuentes.
Soporte para Excel con encabezados en filas no estándar (detección automática).
"""
import pandas as pd
import io
import re
from typing import Dict, List, Union, Optional
from pathlib import Path
from backend.domain.taxonomy import TAXONOMY  # para usar sinónimos en la detección

class Importer:
    """Importador que detecta automáticamente la fila de encabezados en cada hoja."""

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
        sheets_dict = pd.read_excel(file_path, sheet_name=None, header=None, engine='openpyxl' if file_path.suffix == '.xlsx' else 'xlrd')
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
        """
        all_dfs = []
        for sheet_name, df_raw in sheets_dict.items():
            if df_raw.empty:
                continue

            # 1. Detectar la fila de encabezados en esta hoja
            header_row = Importer._detect_header_row(df_raw)
            if header_row is None:
                # Si no se detecta, usamos la primera fila (comportamiento por defecto)
                header_row = 0

            # 2. Extraer encabezados y datos
            headers = df_raw.iloc[header_row].astype(str).str.strip().tolist()
            data_rows = df_raw.iloc[header_row + 1:].copy()
            data_rows.columns = headers

            # 3. Limpiar nombres de columnas (espacios, símbolos, etc.)
            clean_headers = Importer._clean_column_names(headers)
            data_rows.columns = clean_headers

            # 4. Eliminar filas completamente vacías
            data_rows = data_rows.dropna(how='all')
            if data_rows.empty:
                continue

            # 5. Añadir columna con el nombre de la hoja
            data_rows['hoja_origen'] = sheet_name
            all_dfs.append(data_rows)

        if not all_dfs:
            raise ValueError("No se encontraron hojas con datos válidos.")

        return pd.concat(all_dfs, ignore_index=True)

    @staticmethod
    def _detect_header_row(df: pd.DataFrame) -> Optional[int]:
        """
        Detecta la fila que contiene los encabezados de columna.
        Usa una heurística basada en:
        - Porcentaje de celdas no vacías.
        - Presencia de palabras clave de la taxonomía (sinónimos).
        - Tipo de datos (prefiere texto sobre números).
        """
        # Obtener todas las palabras clave (sinónimos) de la taxonomía
        all_aliases = [alias.lower() for alias in TAXONOMY.get_all_aliases()]
        # También agregamos algunos términos comunes que no están en la taxonomía
        extra_keywords = ['código', 'descripción', 'precio', 'modelo', 'categoria', 'iva', 'ean']
        keywords = set(all_aliases + extra_keywords)

        best_score = -1
        best_row = 0
        # Revisar las primeras 30 filas (suficiente para la mayoría de los casos)
        for row_idx in range(min(30, len(df))):
            row_values = df.iloc[row_idx].astype(str).str.lower().str.strip()
            # 1. Porcentaje de celdas no vacías
            non_empty = sum(1 for v in row_values if v and v != 'nan' and v != 'none')
            non_empty_ratio = non_empty / len(row_values) if len(row_values) > 0 else 0

            # 2. Presencia de palabras clave
            keyword_matches = 0
            for val in row_values:
                if val and val != 'nan':
                    # Dividir por espacios o guiones
                    tokens = re.split(r'[\s\-_/]+', val)
                    for token in tokens:
                        if token in keywords:
                            keyword_matches += 1
                            break  # una coincidencia por celda

            # 3. Penalizar si hay muchos números en la fila (probablemente datos, no encabezados)
            numeric_count = sum(1 for v in row_values if re.match(r'^[\d.,]+$', v))
            numeric_penalty = numeric_count / len(row_values) if len(row_values) > 0 else 0

            # Puntuación combinada
            score = (non_empty_ratio * 3) + (keyword_matches * 2) - (numeric_penalty * 2)

            # Bonus si la fila contiene exactamente 'ean' o 'código' (muy común)
            if any('ean' in v or 'código' in v or 'codigo' in v for v in row_values):
                score += 5

            if score > best_score:
                best_score = score
                best_row = row_idx

        # Si la mejor puntuación es muy baja, es posible que no haya encabezados; usamos fila 0
        if best_score < 1.0:
            return 0
        return best_row

    @staticmethod
    def _clean_column_names(headers: List[str]) -> List[str]:
        """Limpia los nombres de columnas: elimina espacios, convierte a minúsculas, reemplaza caracteres especiales."""
        cleaned = []
        for h in headers:
            h = str(h).strip()
            # Eliminar caracteres extraños, pero mantener letras, números y algunos símbolos
            h = re.sub(r'[^a-zA-Z0-9áéíóúñüÁÉÍÓÚÑÜ\s]', '', h)
            # Reemplazar espacios por guiones bajos
            h = h.replace(' ', '_').lower()
            # Eliminar múltiples guiones bajos
            h = re.sub(r'_+', '_', h)
            # Si queda vacío, poner "columna"
            if not h:
                h = f"columna_{len(cleaned)}"
            cleaned.append(h)
        return cleaned
