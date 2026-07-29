"""
Módulo de Importadores - Refactorizado con detección robusta de encabezados
Basado en análisis de Gemini (sistema de votación por tokens y densidad de texto).
"""
import pandas as pd
import io
import re
import unicodedata
from typing import Dict, List, Union, Optional
from pathlib import Path

class Importer:
    """Importador con detección inteligente de encabezados por sistema de votación."""

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
        engine = 'openpyxl' if file_path.suffix == '.xlsx' else 'xlrd'
        sheets_dict = pd.read_excel(file_path, sheet_name=None, header=None, engine=engine)
        return Importer._combine_sheets_with_auto_header(sheets_dict)

    @staticmethod
    def _read_excel_all_sheets_from_bytes(data: bytes) -> pd.DataFrame:
        sheets_dict = pd.read_excel(io.BytesIO(data), sheet_name=None, header=None, engine='openpyxl')
        return Importer._combine_sheets_with_auto_header(sheets_dict)

    @staticmethod
    def _combine_sheets_with_auto_header(sheets_dict: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        all_dfs = []
        for sheet_name, df_raw in sheets_dict.items():
            # 1. Limpieza inicial: eliminar filas/columnas completamente vacías
            df_cleaned = df_raw.dropna(how='all', axis=0).dropna(how='all', axis=1)
            if df_cleaned.empty:
                continue

            # 2. Detectar índice real de la fila de encabezados
            header_row_idx = Importer._detect_header_row_sheet(df_cleaned)
            if header_row_idx is None:
                # Si no se detecta, se omite la hoja (se puede registrar en logs)
                continue

            # 3. Extraer encabezados y aislar los datos puros
            headers = df_cleaned.loc[header_row_idx].astype(str).str.strip().tolist()
            data_rows = df_cleaned.loc[header_row_idx + 1:].copy()

            # 4. Limpieza de nombres de columnas
            clean_headers = Importer._clean_column_names(headers)
            data_rows.columns = clean_headers

            # 5. Descartar filas vacías dentro de los datos
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
        if pd.isna(text):
            return ""
        text = str(text).lower().strip()
        nfkd = unicodedata.normalize('NFKD', text)
        return "".join(c for c in nfkd if not unicodedata.combining(c))

    @staticmethod
    def _detect_header_row_sheet(df: pd.DataFrame) -> Optional[int]:
        """
        Detecta la fila de encabezados utilizando un sistema de votación basado en:
        - Match exacto de palabras clave (evita subcadenas falsas).
        - Exclusión de filas de metadatos (requiere mínimo de celdas no vacías).
        - Densidad de strings vs números.
        """
        # Palabras clave del dominio comercial/ferretero
        taxonomy_keywords = {
            'codigo', 'cod', 'modelo', 'categoria', 'descripcion', 'desc',
            'precio', 'pr', 'lista', 'iva', 'ean', 'sku', 'costo', 'neto',
            'marca', 'rubro', 'familia', 'descuento', 'stock', 'código',
            'descripción', 'denominación'
        }

        best_score = -1
        best_row_idx = None

        # Limitar la búsqueda a las primeras 35 filas para rendimiento
        head_df = df.head(35)

        for idx, row in head_df.iterrows():
            row_values = row.dropna().astype(str).tolist()
            total_cells = len(row_values)

            # REGLA 1: Ignorar filas con menos de 3 celdas llenas (suelen ser títulos o metadatos)
            if total_cells < 3:
                continue

            keyword_hits = 0
            string_cells = 0

            for val in row_values:
                norm_val = Importer._normalize_text(val)
                # Tokenizar por palabras para match exacto usando regex boundary (\b)
                words = set(re.findall(r'\b\w+\b', norm_val))

                # Intersección de tokens con nuestra taxonomía
                if words.intersection(taxonomy_keywords):
                    keyword_hits += 1

                # Chequeo de densidad de texto (los encabezados rara vez son números puros)
                is_numeric = bool(re.match(r'^-?\d+$', re.sub(r'[.,]', '', norm_val)))
                if not is_numeric and len(norm_val) > 1:
                    string_cells += 1

            string_ratio = string_cells / total_cells if total_cells > 0 else 0

            # REGLA 2: Sistema de votación (Score)
            # - Multiplicador alto para matches de taxonomía (10 puntos)
            # - Multiplicador medio para densidad de texto (5 puntos)
            # - Multiplicador bajo para cantidad de columnas (0.1 puntos, desempate)
            score = (keyword_hits * 10) + (string_ratio * 5) + (total_cells * 0.1)

            # REGLA 3: Super-Bonus: si la fila tiene EAN/SKU Y un campo financiero, es indiscutible
            row_text_joined = " ".join([Importer._normalize_text(v) for v in row_values])
            has_id = 'ean' in row_text_joined or 'sku' in row_text_joined
            has_money = 'precio' in row_text_joined or 'costo' in row_text_joined or 'neto' in row_text_joined
            if has_id and has_money:
                score += 25

            # Guardamos el mejor candidato (exigimos al menos 1 keyword hit para considerarlo)
            if score > best_score and keyword_hits > 0:
                best_score = score
                best_row_idx = idx

        return best_row_idx

    @staticmethod
    def _clean_column_names(headers: List[str]) -> List[str]:
        cleaned = []
        seen = set()
        for i, h in enumerate(headers):
            h = str(h).strip()
            # Mantener solo letras, números y espacios (eliminar símbolos como $, %, etc.)
            h = re.sub(r'[^a-zA-Z0-9áéíóúñüÁÉÍÓÚÑÜ\s]', '', h)
            h = Importer._normalize_text(h)
            h = h.replace(' ', '_')
            h = re.sub(r'_+', '_', h)   # Eliminar guiones bajos múltiples
            h = h.strip('_')            # Eliminar guiones al inicio o final

            # Si queda vacío o es 'nan', asignar nombre genérico
            if not h or h == 'nan':
                h = f"columna_{i}"

            # Evitar duplicados
            if h in seen:
                h = f"{h}_{i}"
            seen.add(h)
            cleaned.append(h)
        return cleaned
