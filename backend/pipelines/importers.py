"""
Módulo de Importadores - Adaptadores para leer datos desde diferentes fuentes.
Detección automática de encabezados mejorada.
"""
import pandas as pd
import io
import re
import unicodedata
from typing import Dict, List, Union, Optional
from pathlib import Path
from backend.domain.taxonomy import TAXONOMY

class Importer:
    """Importador con detección inteligente y automática de encabezados."""

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
        all_dfs = []
        for sheet_name, df_raw in sheets_dict.items():
            if df_raw.empty:
                continue

            # Detectar la fila de encabezados automáticamente
            header_row = Importer._detect_header_row(df_raw)
            # Si la detección falla (debería ser raro), usar fila 0
            if header_row is None:
                header_row = 0

            # Extraer encabezados y datos
            headers = df_raw.iloc[header_row].astype(str).str.strip().tolist()
            data_rows = df_raw.iloc[header_row + 1:].copy()
            data_rows.columns = headers

            # Limpiar nombres de columnas (sin tildes, espacios, etc.)
            clean_headers = Importer._clean_column_names(headers)
            data_rows.columns = clean_headers

            # Eliminar filas vacías
            data_rows = data_rows.dropna(how='all')
            if data_rows.empty:
                continue

            data_rows['hoja_origen'] = sheet_name
            all_dfs.append(data_rows)

        if not all_dfs:
            raise ValueError("No se encontraron hojas con datos válidos.")

        return pd.concat(all_dfs, ignore_index=True)

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Elimina tildes y convierte a minúsculas para comparación."""
        if not isinstance(text, str):
            return ""
        # Convertir a minúsculas
        text = text.lower()
        # Eliminar tildes
        nfkd = unicodedata.normalize('NFKD', text)
        return "".join(c for c in nfkd if not unicodedata.combining(c))

    @staticmethod
    def _detect_header_row(df: pd.DataFrame) -> int:
        """
        Detecta automáticamente la fila que contiene los encabezados de columna.
        Usa heurística robusta basada en palabras clave y tipo de datos.
        """
        # Construir conjunto de palabras clave: nombres de campos + alias + extras
        keywords = set()
        for field in TAXONOMY.fields:
            # Nombre del campo (sin tilde)
            keywords.add(field.name.lower())
            # Alias
            for alias in field.aliases:
                keywords.add(Importer._normalize_text(alias))
        # Palabras extra específicas de este tipo de archivos
        extras = ['foto', 'herramienta', 'sugerido', 'cuotas', 'precio sugerido', 'costo', 'neto']
        for extra in extras:
            keywords.add(Importer._normalize_text(extra))

        best_score = -1
        best_row = 0

        # Revisar las primeras 50 filas (suficiente para la mayoría de los casos)
        for row_idx in range(min(50, len(df))):
            row_values = df.iloc[row_idx].astype(str).str.strip().tolist()
            # Filtrar valores vacíos
            valid_values = [v for v in row_values if v and v not in ['nan', 'None', '']]
            if not valid_values:
                continue

            non_empty = len(valid_values)
            keyword_cells = 0
            numeric_cells = 0

            for val in valid_values:
                # Normalizar para comparación
                norm_val = Importer._normalize_text(val)
                # Verificar si es numérica
                if re.match(r'^[\d.,]+$', norm_val):
                    numeric_cells += 1
                # Verificar si contiene alguna palabra clave
                if any(kw in norm_val for kw in keywords):
                    keyword_cells += 1

            # Puntuación: priorizar celdas con keywords, penalizar numéricas
            score = (keyword_cells * 3) - numeric_cells
            # Bonus si alguna celda contiene "ean" (muy distintivo)
            if any('ean' in Importer._normalize_text(v) for v in valid_values):
                score += 10

            if score > best_score:
                best_score = score
                best_row = row_idx

        # Si no se encontró ninguna fila con puntuación positiva, usar la fila con más contenido
        if best_score <= 0:
            # Buscar la fila con mayor cantidad de celdas no vacías
            max_non_empty = 0
            for row_idx in range(min(50, len(df))):
                non_empty = df.iloc[row_idx].count()
                if non_empty > max_non_empty:
                    max_non_empty = non_empty
                    best_row = row_idx

        return best_row

    @staticmethod
    def _clean_column_names(headers: List[str]) -> List[str]:
        """Limpia nombres de columnas: sin tildes, espacios reemplazados por guiones bajos, minúsculas."""
        cleaned = []
        for h in headers:
            h = str(h).strip()
            # Eliminar caracteres especiales, pero mantener letras y números
            h = re.sub(r'[^a-zA-Z0-9áéíóúñüÁÉÍÓÚÑÜ\s]', '', h)
            # Reemplazar espacios por guiones bajos y convertir a minúsculas
            h = h.replace(' ', '_').lower()
            # Eliminar tildes para uniformidad
            h = Importer._normalize_text(h)
            # Eliminar múltiples guiones bajos
            h = re.sub(r'_+', '_', h)
            if not h:
                h = f"columna_{len(cleaned)}"
            cleaned.append(h)
        return cleaned
