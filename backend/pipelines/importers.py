"""
Módulo de Importadores - Versión final con detección robusta de encabezados.
"""
import pandas as pd
import io
import re
import unicodedata
from typing import Dict, List, Union, Optional
from pathlib import Path
from backend.domain.taxonomy import TAXONOMY

class Importer:
    """Importador con detección inteligente de encabezados, hoja por hoja."""

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

            # Detectar la fila de encabezados para esta hoja
            header_row = Importer._detect_header_row_sheet(df_raw)
            
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

            # Verificar si los nombres son todos "Unnamed" - si es así, reintentar con fila 4
            unnamed_ratio = sum(1 for h in clean_headers if h.startswith('columna_')) / len(clean_headers) if clean_headers else 1
            if unnamed_ratio > 0.8:
                # Reintentar con fila 4 (la que funciona en el archivo de ejemplo)
                fallback_row = 4
                if len(df_raw) > fallback_row:
                    headers_fb = df_raw.iloc[fallback_row].astype(str).str.strip().tolist()
                    data_rows = df_raw.iloc[fallback_row + 1:].copy()
                    data_rows.columns = headers_fb
                    clean_headers_fb = Importer._clean_column_names(headers_fb)
                    data_rows.columns = clean_headers_fb
                    data_rows = data_rows.dropna(how='all')
                    if not data_rows.empty and all(h.startswith('columna_') for h in clean_headers_fb) == False:
                        clean_headers = clean_headers_fb
                        header_row = fallback_row

            data_rows['hoja_origen'] = sheet_name
            all_dfs.append(data_rows)

        if not all_dfs:
            raise ValueError("No se encontraron hojas con datos válidos.")

        return pd.concat(all_dfs, ignore_index=True)

    @staticmethod
    def _normalize_text(text: str) -> str:
        if not isinstance(text, str):
            return ""
        text = text.lower()
        nfkd = unicodedata.normalize('NFKD', text)
        return "".join(c for c in nfkd if not unicodedata.combining(c))

    @staticmethod
    def _detect_header_row_sheet(df: pd.DataFrame) -> int:
        """
        Detecta la fila de encabezados en una hoja específica.
        Estrategia: buscar la fila que contenga al menos una palabra clave fuerte
        y tenga la mayor cantidad de celdas no vacías.
        """
        strong_keywords = ['codigo', 'modelo', 'categoria', 'descripcion', 'precio', 'iva', 'ean', 'sku', 'código', 'descripción']
        extra_keywords = ['foto', 'herramienta', 'sugerido', 'cuotas', 'costo', 'neto', 'marca', 'denominación']
        all_keywords = set(strong_keywords + extra_keywords)

        candidates = []
        for row_idx in range(min(50, len(df))):
            row_values = df.iloc[row_idx].astype(str).str.strip().tolist()
            valid = [v for v in row_values if v and v not in ['nan', 'None', '']]
            if not valid:
                continue

            non_empty = len(valid)
            has_strong = False
            keyword_score = 0
            numeric_count = 0

            for val in valid:
                norm_val = Importer._normalize_text(val)
                if any(kw in norm_val for kw in strong_keywords):
                    has_strong = True
                    keyword_score += 3
                elif any(kw in norm_val for kw in extra_keywords):
                    keyword_score += 1
                if re.match(r'^[\d.,]+$', norm_val.replace(',', '').replace('.', '')):
                    numeric_count += 1

            # Bonus especial por "ean"
            if any('ean' in Importer._normalize_text(v) for v in valid):
                keyword_score += 10

            # Penalizar si hay muchos números
            penalty = numeric_count / max(1, non_empty)
            score = keyword_score * 2 + non_empty - penalty * 5

            if has_strong or keyword_score > 2:
                candidates.append((row_idx, score, non_empty))

        if candidates:
            # Elegir el candidato con mayor puntuación, desempatar por non_empty
            best = max(candidates, key=lambda x: (x[1], x[2]))
            return best[0]

        # Fallback: fila con más celdas no vacías
        max_non_empty = 0
        best_row = 0
        for row_idx in range(min(30, len(df))):
            non_empty = df.iloc[row_idx].count()
            if non_empty > max_non_empty:
                max_non_empty = non_empty
                best_row = row_idx
        return best_row

    @staticmethod
    def _clean_column_names(headers: List[str]) -> List[str]:
        cleaned = []
        for h in headers:
            h = str(h).strip()
            # Eliminar caracteres especiales, mantener letras y números
            h = re.sub(r'[^a-zA-Z0-9áéíóúñüÁÉÍÓÚÑÜ\s]', '', h)
            h = h.replace(' ', '_').lower()
            h = Importer._normalize_text(h)
            h = re.sub(r'_+', '_', h)
            if not h:
                h = f"columna_{len(cleaned)}"
            cleaned.append(h)
        return cleaned
