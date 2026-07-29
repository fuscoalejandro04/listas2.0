"""
Módulo de Importadores - Estrategia híbrida: Bottom-Up (tipos de datos) + Taxonomía Inversa.
Detección robusta de encabezados sin heurísticas de palabras clave.
"""
import pandas as pd
import io
import re
from typing import Dict, List, Union, Optional
from pathlib import Path
from backend.domain.taxonomy import TAXONOMY
from backend.pipelines.detectors import ColumnMapper  # Para validar mapeo

class Importer:
    """Importador con detección inteligente de encabezados basada en tipos de datos y taxonomía."""

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
                                    engine='openpyxl' if Path(file_path).suffix == '.xlsx' else 'xlrd')
        return Importer._combine_sheets_with_auto_header(sheets_dict)

    @staticmethod
    def _read_excel_all_sheets_from_bytes(data: bytes) -> pd.DataFrame:
        sheets_dict = pd.read_excel(io.BytesIO(data), sheet_name=None, header=None, engine='openpyxl')
        return Importer._combine_sheets_with_auto_header(sheets_dict)

    @staticmethod
    def _combine_sheets_with_auto_header(sheets_dict: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        all_dfs = []
        for sheet_name, df_raw in sheets_dict.items():
            # Limpiar filas/columnas completamente vacías
            df_clean = df_raw.dropna(how='all', axis=0).dropna(how='all', axis=1)
            if df_clean.empty:
                continue

            # 1. Intentar detección por tipos de datos (Bottom-Up)
            header_row = Importer._find_header_by_data_types(df_clean)

            # 2. Validar con taxonomía
            if header_row is not None:
                header_candidates = [header_row]
                # Si la validación falla, probar filas cercanas
                for offset in [-1, 1, -2, 2]:
                    candidate = header_row + offset
                    if 0 <= candidate < len(df_clean):
                        header_candidates.append(candidate)
                # Elegir la que mejor mapee a la taxonomía
                best_row = Importer._select_best_by_taxonomy(df_clean, header_candidates)
                if best_row is not None:
                    header_row = best_row

            # 3. Si aún no se encontró, usar taxonomía inversa pura
            if header_row is None:
                header_row = Importer._find_header_by_taxonomy_only(df_clean)

            if header_row is None:
                # Fallback extremo: usar fila con más celdas no vacías
                header_row = Importer._fallback_max_non_empty(df_clean)

            # Extraer encabezados y datos
            headers = df_clean.loc[header_row].astype(str).str.strip().tolist()
            data_rows = df_clean.loc[header_row + 1:].copy()

            clean_headers = Importer._clean_column_names(headers)
            data_rows.columns = clean_headers
            data_rows = data_rows.dropna(how='all')
            if data_rows.empty:
                continue

            data_rows['hoja_origen'] = sheet_name
            all_dfs.append(data_rows)

        if not all_dfs:
            raise ValueError("No se encontraron hojas con datos válidos.")
        return pd.concat(all_dfs, ignore_index=True)

    @staticmethod
    def _find_header_by_data_types(df: pd.DataFrame) -> Optional[int]:
        """
        Detecta la fila donde los tipos de datos por columna se vuelven consistentes.
        Retorna el índice de la fila de encabezados (la anterior al inicio de datos).
        """
        # Tomar primeras 50 filas para análisis
        sample = df.head(50)
        if len(sample) < 2:
            return None

        # Calcular el tipo de dato inferido para cada celda (usando pandas)
        # Creamos una matriz de tipos
        type_matrix = sample.applymap(lambda x: pd.api.types.infer_dtype([x], skipna=True))

        # Función para medir la "consistencia" de una fila: cuántas columnas tienen el mismo tipo
        # que la fila siguiente (transición suave)
        scores = []
        for i in range(len(type_matrix) - 1):
            row_types = type_matrix.iloc[i]
            next_row_types = type_matrix.iloc[i + 1]
            # Comparar tipo por columna (ignorando NaN)
            matches = 0
            total = 0
            for col in row_types.index:
                if pd.notna(row_types[col]) and pd.notna(next_row_types[col]):
                    total += 1
                    if row_types[col] == next_row_types[col]:
                        matches += 1
            if total > 0:
                similarity = matches / total
                scores.append((i, similarity))
            else:
                scores.append((i, 0.0))

        # Buscar la fila donde la similitud es máxima (el cambio de tipos se estabiliza)
        # La fila de encabezados suele estar justo antes de que los tipos se vuelvan homogéneos
        if not scores:
            return None

        # Ordenar por similitud descendente
        scores.sort(key=lambda x: x[1], reverse=True)
        best_row_idx = scores[0][0]

        # La fila de encabezados es la anterior a la primera fila con alta consistencia
        # Pero si la mejor fila es la 0, entonces encabezado es 0 también
        if best_row_idx == 0:
            return 0

        # Buscar la primera fila donde la consistencia supera un umbral alto (ej. 0.7)
        threshold = 0.7
        for i, sim in sorted(scores, key=lambda x: x[0]):
            if sim >= threshold:
                # La fila de encabezados es la anterior (i)
                return i

        # Si no se encuentra umbral, usar la fila con mayor similitud - 1
        return best_row_idx

    @staticmethod
    def _select_best_by_taxonomy(df: pd.DataFrame, candidate_rows: List[int]) -> Optional[int]:
        """Evalúa los candidatos y elige el que mejor mapea a la taxonomía."""
        mapper = ColumnMapper(confidence_threshold=0.0)  # Sin umbral mínimo
        best_score = -1
        best_row = None

        for row_idx in candidate_rows:
            if row_idx < 0 or row_idx >= len(df):
                continue
            headers = df.loc[row_idx].astype(str).str.strip().tolist()
            # Crear un DataFrame ficticio con esos encabezados para mapear
            dummy_df = pd.DataFrame([headers], columns=headers)
            mapping = mapper.map_columns(dummy_df)
            # Calcular puntuación: porcentaje de columnas mapeadas
            mapped = sum(1 for v in mapping.values() if v[0] is not None)
            total = len(mapping)
            if total == 0:
                continue
            score = mapped / total
            # Bonus si hay columnas con confianza alta
            avg_conf = sum(v[1] for v in mapping.values() if v[0] is not None) / max(1, mapped)
            final_score = score * 0.7 + avg_conf * 0.3
            if final_score > best_score:
                best_score = final_score
                best_row = row_idx

        return best_row

    @staticmethod
    def _find_header_by_taxonomy_only(df: pd.DataFrame) -> Optional[int]:
        """Fallback: busca la fila que maximiza mapeo a taxonomía entre las primeras 20."""
        candidates = list(range(min(20, len(df))))
        return Importer._select_best_by_taxonomy(df, candidates)

    @staticmethod
    def _fallback_max_non_empty(df: pd.DataFrame) -> int:
        """Último recurso: fila con más celdas no vacías."""
        max_count = -1
        best_row = 0
        for idx in range(min(30, len(df))):
            count = df.iloc[idx].count()
            if count > max_count:
                max_count = count
                best_row = idx
        return best_row

    @staticmethod
    def _clean_column_names(headers: List[str]) -> List[str]:
        cleaned = []
        for i, h in enumerate(headers):
            h = str(h).strip()
            # Eliminar caracteres especiales, mantener letras, números, espacios
            h = re.sub(r'[^a-zA-Z0-9áéíóúñüÁÉÍÓÚÑÜ\s]', '', h)
            # Normalizar: minúsculas, reemplazar espacios por guiones bajos
            h = h.lower().replace(' ', '_')
            # Eliminar acentos
            import unicodedata
            nfkd = unicodedata.normalize('NFKD', h)
            h = "".join(c for c in nfkd if not unicodedata.combining(c))
            h = re.sub(r'_+', '_', h).strip('_')
            if not h or h == 'nan':
                h = f"columna_{i}"
            cleaned.append(h)
        return cleaned
