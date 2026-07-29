"""
Módulo de Importadores - Adaptadores para leer datos desde diferentes fuentes.
Detecta automáticamente la fila de encabezados usando heurística avanzada.
"""
import pandas as pd
import io
import re
from typing import Dict, List, Union, Optional
from pathlib import Path
from backend.domain.taxonomy import TAXONOMY

class Importer:
    """Importador con detección automática de encabezados."""

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

            # Detectar automáticamente la fila de encabezados
            header_row = Importer._detect_header_row(df_raw)

            # Extraer encabezados y datos
            headers = df_raw.iloc[header_row].astype(str).str.strip().tolist()
            data_rows = df_raw.iloc[header_row + 1:].copy()
            data_rows.columns = headers

            # Limpiar nombres de columnas
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
    def _detect_header_row(df: pd.DataFrame) -> int:
        """
        Detecta la fila de encabezados usando una heurística avanzada.
        Retorna el índice de la fila más probable.
        """
        best_score = -1
        best_row = 0

        # Palabras clave que suelen aparecer en encabezados
        keywords = set([
            'codigo', 'código', 'sku', 'modelo', 'descripcion', 'descripción',
            'precio', 'precio_lista', 'pvp', 'iva', 'ean', 'marca', 'categoria',
            'categoría', 'nombre', 'articulo', 'artículo', 'detalle', 'denominacion',
            'cantidad', 'unidad', 'peso', 'alto', 'ancho', 'profundidad', 'color',
            'talla', 'tamaño', 'stock', 'inventario', 'proveedor', 'fabricante'
        ])

        for row_idx in range(min(50, len(df))):
            row_values = df.iloc[row_idx].astype(str).str.strip()
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
                for kw in keywords:
                    if kw in val_lower:
                        keyword_count += 1
                        break
                # Números
                if re.match(r'^[\d.,]+$', val_lower.replace(',', '').replace('.', '').strip()):
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

        # Si la mejor puntuación es muy baja, usar fila 0
        if best_score < 1.0:
            return 0
        return best_row

    @staticmethod
    def _clean_column_names(headers: List[str]) -> List[str]:
        cleaned = []
        for h in headers:
            h = str(h).strip()
            h = re.sub(r'[^a-zA-Z0-9áéíóúñüÁÉÍÓÚÑÜ\s]', '', h)
            h = h.replace(' ', '_').lower()
            h = re.sub(r'_+', '_', h)
            if not h:
                h = f"columna_{len(cleaned)}"
            cleaned.append(h)
        return cleaned
