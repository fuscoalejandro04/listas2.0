"""
Módulo de Importadores - Adaptadores para leer datos desde diferentes fuentes.
Soporte para Excel con encabezados en filas no estándar (detección automática robusta).
"""
import pandas as pd
import io
import re
import numpy as np
import unicodedata
from typing import Dict, List, Union, Optional, Any, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
from backend.domain.taxonomy import TAXONOMY


# ============================================================
# MODELOS DE DOMINIO PARA EL IMPORTADOR
# ============================================================
class CellType(Enum):
    EMPTY = "empty"
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    BOOLEAN = "boolean"
    FORMULA = "formula"
    ERROR = "error"


@dataclass
class CellInfo:
    row: int
    col: int
    value: Optional[str] = None
    cell_type: CellType = CellType.EMPTY
    is_merged: bool = False
    bold: bool = False
    fill_color: Optional[str] = None
    border_bottom: bool = False


@dataclass
class RowInfo:
    index: int
    cells: List[CellInfo]
    non_empty_count: int = 0
    text_count: int = 0
    number_count: int = 0
    date_count: int = 0
    empty_count: int = 0
    max_col: int = 0


@dataclass
class HeaderDetectionResult:
    header_row: Optional[int]
    table_start: Optional[int]
    confidence: float
    strategy: str
    diagnostics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SheetImportResult:
    sheet_name: str
    success: bool
    header_result: Optional[HeaderDetectionResult] = None
    dataframe: Optional[pd.DataFrame] = None
    error: Optional[str] = None
    diagnostics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ImportResult:
    filename: str
    successful_sheets: List[SheetImportResult] = field(default_factory=list)
    failed_sheets: List[SheetImportResult] = field(default_factory=list)
    total_sheets: int = 0
    total_successful: int = 0
    total_failed: int = 0


# ============================================================
# CLASIFICADOR DE TIPOS
# ============================================================
class TypeClassifier:
    """Clasifica el tipo de dato de una celda."""
    
    NUMBER_PATTERNS = [
        re.compile(r'^[+-]?\d{1,3}(?:\.\d{3})*(?:,\d+)?$'),
        re.compile(r'^[+-]?\d{1,3}(?:,\d{3})*(?:\.\d+)?$'),
        re.compile(r'^[+-]?\d+(?:[.,]\d+)?$'),
        re.compile(r'^\$?\d+(?:[.,]\d+)?$'),
        re.compile(r'^\d+(?:[.,]\d+)?%$'),
    ]
    DATE_PATTERNS = [
        re.compile(r'^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$'),
        re.compile(r'^\d{1,2}[/-]\d{1,2}[/-]\d{2}$'),
    ]
    BOOLEAN_TRUE = re.compile(r'^(true|yes|sí|si|1)$', re.IGNORECASE)
    BOOLEAN_FALSE = re.compile(r'^(false|no|0)$', re.IGNORECASE)
    ERROR_PATTERNS = [re.compile(r'^#\w+!?$')]

    @classmethod
    def classify(cls, value) -> CellType:
        if value is None or (isinstance(value, str) and value.strip() == ''):
            return CellType.EMPTY
        if isinstance(value, bool):
            return CellType.BOOLEAN
        if isinstance(value, (int, float)):
            return CellType.NUMBER
        if isinstance(value, pd.Timestamp):
            return CellType.DATE
        if isinstance(value, str):
            stripped = value.strip()
            if stripped == '':
                return CellType.EMPTY
            for pat in cls.ERROR_PATTERNS:
                if pat.match(stripped):
                    return CellType.ERROR
            for pat in cls.DATE_PATTERNS:
                if pat.match(stripped):
                    return CellType.DATE
            for pat in cls.NUMBER_PATTERNS:
                if pat.match(stripped):
                    return CellType.NUMBER
            if cls.BOOLEAN_TRUE.match(stripped) or cls.BOOLEAN_FALSE.match(stripped):
                return CellType.BOOLEAN
            if stripped.startswith('='):
                return CellType.FORMULA
            return CellType.TEXT
        return CellType.TEXT


# ============================================================
# IMPORTER PRINCIPAL (MÉTODOS BLINDADOS)
# ============================================================
class Importer:
    """Importador con detección robusta de encabezados."""

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
        Usa el método robusto _detect_header_row.
        """
        all_dfs = []
        for sheet_name, df_raw in sheets_dict.items():
            try:
                if df_raw.empty:
                    continue

                # 1. Detectar la fila de encabezados usando el método blindado
                header_row = Importer._detect_header_row(df_raw)
                if header_row is None:
                    header_row = 0

                # 2. Extraer encabezados y datos
                headers = df_raw.iloc[header_row].astype(str).str.strip().tolist()
                data_rows = df_raw.iloc[header_row + 1:].copy()
                data_rows.columns = headers

                # 3. Limpiar nombres de columnas (con protección de unicidad)
                clean_headers = Importer._clean_column_names(headers)
                data_rows.columns = clean_headers

                # 4. Eliminar filas completamente vacías
                data_rows = data_rows.dropna(how='all')
                if data_rows.empty:
                    continue

                # 5. Añadir columna con el nombre de la hoja
                data_rows['hoja_origen'] = sheet_name
                all_dfs.append(data_rows)

            except Exception as e:
                print(f"⚠️ Error al procesar la hoja '{sheet_name}': {e}")
                raise ValueError(f"Hoja '{sheet_name}': {str(e)}")

        if not all_dfs:
            raise ValueError("No se encontraron hojas con datos válidos.")

        return pd.concat(all_dfs, ignore_index=True)

    @staticmethod
    def _detect_header_row(df: pd.DataFrame) -> Optional[int]:
        """
        🔥 VERSIÓN BLINDADA: Detecta la fila de encabezados usando Python puro.
        No usa .astype(str).str.strip() encadenado.
        Itera sobre los valores de la fila como lista y limpia manualmente.
        """
        if df.empty:
            return None

        # Palabras clave que suelen aparecer en encabezados
        keywords = {
            'codigo', 'código', 'sku', 'modelo', 'descripción', 'descripcion',
            'precio', 'precio_lista', 'pvp', 'iva', 'ean', 'marca', 'categoría', 'categoria',
            'nombre', 'artículo', 'articulo', 'detalle', 'denominación', 'denominacion',
            'cantidad', 'unidad', 'peso', 'alto', 'ancho', 'profundidad', 'color',
            'talla', 'tamaño', 'stock', 'inventario', 'proveedor', 'fabricante'
        }

        best_score = -1
        best_row = 0

        # Limitar a las primeras 50 filas
        max_rows = min(50, len(df))

        for row_idx in range(max_rows):
            # Obtener los valores de la fila como lista (Pandas nativo, pero sin encadenar métodos)
            row_values = df.iloc[row_idx].values

            # Limpiar cada valor: convertir a string, quitar espacios, descartar vacíos y 'nan'
            clean_values = []
            for v in row_values:
                if pd.isna(v):
                    continue
                v_str = str(v).strip()
                if v_str and v_str.lower() != 'nan':
                    clean_values.append(v_str)

            if not clean_values:
                continue

            # 1. Porcentaje de celdas no vacías (sobre el total de la fila)
            non_empty_ratio = len(clean_values) / len(row_values)

            # 2. Contar palabras clave y números
            keyword_count = 0
            numeric_count = 0
            for val in clean_values:
                val_lower = val.lower()
                # Palabras clave
                matched = False
                for kw in keywords:
                    if kw in val_lower:
                        keyword_count += 1
                        matched = True
                        break
                # Números (removiendo puntos y comas)
                if not matched:
                    cleaned_num = re.sub(r'[.,]', '', val_lower)
                    if cleaned_num.isdigit():
                        numeric_count += 1

            keyword_ratio = keyword_count / len(clean_values) if clean_values else 0
            numeric_penalty = numeric_count / len(clean_values) if clean_values else 0
            text_ratio = 1 - numeric_penalty

            # Bonus por palabras muy relevantes (ean, codigo, precio)
            bonus = 0
            for val in clean_values:
                val_lower = val.lower()
                if 'ean' in val_lower or 'código' in val_lower or 'codigo' in val_lower:
                    bonus += 3
                if 'precio' in val_lower or 'pvp' in val_lower:
                    bonus += 2

            # Penalizar si los valores son muy largos (probable descripción)
            avg_len = sum(len(v) for v in clean_values) / len(clean_values) if clean_values else 0
            length_penalty = 1 if avg_len > 50 else 0

            # Puntuación final
            score = (non_empty_ratio * 2) + (keyword_ratio * 5) + (text_ratio * 2) + bonus - (length_penalty * 2)

            if score > best_score:
                best_score = score
                best_row = row_idx

        # Si la mejor puntuación es muy baja (menos de 1), devolvemos 0 (primera fila) como fallback
        if best_score < 1.0:
            return 0

        return best_row

    @staticmethod
    def _clean_column_names(headers: List[str]) -> List[str]:
        """
        🔥 VERSIÓN BLINDADA: Limpia nombres de columnas y garantiza unicidad.
        - Convierte a string.
        - Si está vacío o es 'nan', asigna nombre genérico.
        - Normaliza con NFKD (sin tildes, minúsculas).
        - Asegura unicidad con while loop (añade sufijo _1, _2, etc.).
        """
        cleaned = []

        for h in headers:
            # 1. Convertir a string y limpiar espacios
            h_str = str(h).strip() if h is not None else ""

            # 2. Si quedó vacío o es 'nan', asignar nombre genérico
            if not h_str or h_str.lower() == 'nan':
                base_name = f"columna_{len(cleaned)}"
            else:
                # 3. Eliminar caracteres especiales (solo letras, números, espacios)
                h_str = re.sub(r'[^a-zA-Z0-9áéíóúñü\s]', '', h_str)
                # 4. Reemplazar espacios por guiones bajos
                h_str = h_str.replace(' ', '_')
                # 5. Convertir a minúsculas
                h_str = h_str.lower()
                # 6. Normalizar NFKD (eliminar tildes)
                try:
                    nfkd = unicodedata.normalize('NFKD', h_str)
                    h_str = "".join(c for c in nfkd if not unicodedata.combining(c))
                except Exception:
                    pass  # Si falla, mantener el string original
                # 7. Eliminar guiones bajos múltiples y limpiar extremos
                h_str = re.sub(r'_+', '_', h_str)
                h_str = h_str.strip('_')
                # 8. Si quedó vacío, asignar genérico
                if not h_str:
                    base_name = f"columna_{len(cleaned)}"
                else:
                    base_name = h_str

            # 9. 🔥 GARANTIZAR UNICIDAD (evitar colisiones)
            final_name = base_name
            counter = 1
            while final_name in cleaned:
                final_name = f"{base_name}_{counter}"
                counter += 1

            cleaned.append(final_name)

        return cleaned


# ============================================================
# ORQUESTADOR DE IMPORTACIÓN (ExcelImporter)
# ============================================================
class ExcelImporter:
    """Orquestador principal para importar archivos Excel con detección de headers."""

    def __init__(self, max_scan_rows: int = 100, max_scan_cols: int = 30):
        self.max_scan_rows = max_scan_rows
        self.max_scan_cols = max_scan_cols

    def import_from_bytes(self, data: bytes, filename: str) -> ImportResult:
        """Importa un archivo Excel desde bytes y retorna ImportResult."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        try:
            return self.import_from_path(tmp_path, filename)
        finally:
            tmp_path.unlink(missing_ok=True)

    def import_from_path(self, filepath: Path, filename: Optional[str] = None) -> ImportResult:
        """
        Importa un archivo Excel desde una ruta y retorna ImportResult.
        🔥 Incluye la inyección del título huérfano (last_title) para que el
        PipelineProcessor pueda heredar la categoría.
        """
        if filename is None:
            filename = filepath.name

        result = ImportResult(filename=filename)
        sheets_dict = pd.read_excel(filepath, sheet_name=None, header=None,
                                    engine='openpyxl' if filepath.suffix == '.xlsx' else 'xlrd')

        for sheet_name, df_raw in sheets_dict.items():
            try:
                if df_raw.empty:
                    result.failed_sheets.append(SheetImportResult(
                        sheet_name=sheet_name,
                        success=False,
                        error="Hoja vacía"
                    ))
                    continue

                # 1. Detectar header usando el método blindado
                header_row = Importer._detect_header_row(df_raw)
                if header_row is None:
                    header_row = 0

                # 2. 🔥 RESCATE DEL TÍTULO (último valor no vacío en columna 0 antes del header)
                last_title = None
                for idx in range(header_row):
                    val = df_raw.iloc[idx, 0]
                    if pd.notna(val) and str(val).strip():
                        last_title = str(val).strip()

                # 3. Extraer encabezados y datos
                headers = df_raw.iloc[header_row].astype(str).str.strip().tolist()
                data_rows = df_raw.iloc[header_row + 1:].copy()
                data_rows.columns = headers

                # 4. Limpiar nombres de columnas (con protección de unicidad)
                clean_headers = Importer._clean_column_names(headers)
                data_rows.columns = clean_headers

                # 5. Eliminar filas completamente vacías
                data_rows = data_rows.dropna(how='all')
                if data_rows.empty:
                    result.failed_sheets.append(SheetImportResult(
                        sheet_name=sheet_name,
                        success=False,
                        error="Sin datos después del header"
                    ))
                    continue

                # 6. 🔥 INYECCIÓN DEL TÍTULO HUÉRFANO COMO PRIMERA FILA
                if last_title:
                    # Crear una fila con el título en la primera columna y NaN en el resto
                    new_row = {col: np.nan for col in data_rows.columns}
                    # Asegurar que al menos exista la primera columna
                    if data_rows.columns[0] in new_row:
                        new_row[data_rows.columns[0]] = last_title
                    else:
                        # Si no hay columnas, crear una
                        new_row = {data_rows.columns[0]: last_title}
                    new_df = pd.DataFrame([new_row])
                    data_rows = pd.concat([new_df, data_rows], ignore_index=True)

                # 7. Añadir columna con el nombre de la hoja
                data_rows['hoja_origen'] = sheet_name

                result.successful_sheets.append(SheetImportResult(
                    sheet_name=sheet_name,
                    success=True,
                    dataframe=data_rows,
                    header_result=HeaderDetectionResult(
                        header_row=header_row,
                        table_start=header_row + 1,
                        confidence=1.0,
                        strategy="heuristic"
                    )
                ))

            except Exception as e:
                result.failed_sheets.append(SheetImportResult(
                    sheet_name=sheet_name,
                    success=False,
                    error=str(e)
                ))

        result.total_sheets = len(result.successful_sheets) + len(result.failed_sheets)
        result.total_successful = len(result.successful_sheets)
        result.total_failed = len(result.failed_sheets)
        return result


# ============================================================
# FUNCIÓN DE ENTRADA (LA QUE USA STREAMLIT)
# ============================================================
def import_excel(data: bytes, filename: str) -> ImportResult:
    """
    Función principal para importar archivos Excel.
    Retorna un objeto ImportResult con las hojas procesadas.
    """
    importer = ExcelImporter()
    return importer.import_from_bytes(data, filename)
