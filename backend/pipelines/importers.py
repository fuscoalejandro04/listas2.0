"""
Módulo de Importadores - Adaptadores para leer datos desde diferentes fuentes.
Detección automática de encabezados mejorada: prioriza palabras clave fuertes.
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
            header_row, score = Importer._detect_header_row(df_raw)
            # Si la detección falla (debería ser raro), usar fila 0
            if header_row is None:
                header_row = 0
                score = 0

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
        text = text.lower()
        nfkd = unicodedata.normalize('NFKD', text)
        return "".join(c for c in nfkd if not unicodedata.combining(c))

    @staticmethod
    def _detect_header_row(df: pd.DataFrame) -> tuple:
        """
        Detecta automáticamente la fila de encabezados.
        Retorna (fila, puntuación) o (None, 0) si no se detecta.
        """
        # Palabras clave principales (muy distintivas)
        strong_keywords = ['codigo', 'modelo', 'categoria', 'descripcion', 'precio', 'iva', 'ean', 'sku']
        # Palabras adicionales (menos distintivas)
        extra_keywords = ['foto', 'herramienta', 'sugerido', 'cuotas', 'costo', 'neto', 'marca']
        all_keywords = set(strong_keywords + extra_keywords)

        best_row = 0
        best_score = -1
        best_non_empty = 0

        # Revisar las primeras 30 filas (suficiente para la mayoría)
        for row_idx in range(min(30, len(df))):
            row_values = df.iloc[row_idx].astype(str).str.strip().tolist()
            valid_values = [v for v in row_values if v and v not in ['nan', 'None', '']]
            if not valid_values:
                continue

            non_empty = len(valid_values)
            # Contar cuántas celdas contienen al menos una palabra clave fuerte
            strong_count = 0
            keyword_count = 0
            for val in valid_values:
                norm_val = Importer._normalize_text(val)
                # Si contiene alguna strong_keyword, sumamos 2 puntos por celda
                if any(kw in norm_val for kw in strong_keywords):
                    strong_count += 1
                    keyword_count += 2
                elif any(kw in norm_val for kw in extra_keywords):
                    keyword_count += 1

            # Bonus si alguna celda contiene "ean"
            if any('ean' in Importer._normalize_text(v) for v in valid_values):
                keyword_count += 5

            # La puntuación prioriza filas con strong_keywords y muchas celdas no vacías
            score = keyword_count * 2 + non_empty

            # Si la puntuación es mayor o si es igual y tiene más celdas no vacías, elegir esta fila
            if score > best_score or (score == best_score and non_empty > best_non_empty):
                best_score = score
                best_row = row_idx
                best_non_empty = non_empty

        # Si no se encontró ninguna fila con strong_keywords, buscar la fila con más celdas no vacías
        if best_score == 0:
            max_non_empty = 0
            for row_idx in range(min(30, len(df))):
                non_empty = df.iloc[row_idx].count()
                if non_empty > max_non_empty:
                    max_non_empty = non_empty
                    best_row = row_idx
            best_score = -1  # indicar que no se encontraron keywords

        # Si la mejor fila tiene muy pocas celdas, usar la primera fila con al menos 3 celdas no vacías
        if best_non_empty < 3 and best_score < 1:
            for row_idx in range(min(30, len(df))):
                if df.iloc[row_idx].count() >= 3:
                    best_row = row_idx
                    break

        return best_row, best_score

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
