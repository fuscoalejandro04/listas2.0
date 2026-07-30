"""
Módulo de Importadores - Adaptadores para leer datos desde diferentes fuentes.
Soporte para Excel con encabezados en filas no estándar (detección automática).
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
        if isinstance(value, pd.Timestamp) or isinstance(value, pd.Timestamp):
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
# IMPORTER PRINCIPAL
# ============================================================
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

                # 🔥 RESCATE DEL TÍTULO (Memoria a corto plazo de la columna 0)
                last_title = None
                if header_row > 0:
                    for idx in range(header_row):
                        val = df_raw.iloc[idx, 0]
                        if pd.notna(val) and str(val).strip() and str(val).lower() != 'nan':
                            last_title = str(val).strip()

                # 2. Extraer encabezados y datos
                headers = df_raw.iloc[header_row].astype(str).str.strip().tolist()
                data_rows = df_raw.iloc[header_row + 1:].copy()
                data_rows.columns = headers

                # 3. Limpiar nombres de columnas
                clean_headers = Importer._clean_column_names(headers)
                data_rows.columns = clean_headers

                # 4. Eliminar filas completamente vacías
                data_rows = data_rows.dropna(how='all')
                if data_rows.empty:
                    continue

                # 🔥 INYECCIÓN SEGURA DEL TÍTULO HUÉRFANO (Sin Diccionarios)
                if last_title:
                    new_row_df = pd.DataFrame(np.nan, index=[0], columns=data_rows.columns)
                    new_row_df.iloc[0, 0] = last_title
                    data_rows = pd.concat([new_row_df, data_rows], ignore_index=True)

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
        Detecta la fila de encabezados usando una heurística avanzada.
        Retorna el índice de la fila más probable.
        """
        best_score = -1
        best_row = 0

        keywords = set([
            'codigo', 'código', 'sku', 'modelo', 'descripción', 'descripcion',
            'precio', 'precio_lista', 'pvp', 'iva', 'ean', 'marca', 'categoría', 'categoria',
            'nombre', 'artículo', 'articulo', 'detalle', 'denominación', 'denominacion',
            'cantidad', 'unidad', 'peso', 'alto', 'ancho', 'profundidad', 'color',
            'talla', 'tamaño', 'stock', 'inventario', 'proveedor', 'fabricante'
        ])

        for row_idx in range(min(50, len(df))):
            try:
                row_values = df.iloc[row_idx].astype(str).str.strip()
                non_empty = [v for v in row_values if v and v not in ['nan', 'none', '']]
                if len(non_empty) == 0:
                    continue

                non_empty_ratio = len(non_empty) / len(row_values)
                keyword_count = 0
                numeric_count = 0
                for val in non_empty:
                    val_lower = val.lower()
                    for k in keywords:
                        if k in val_lower:
                            keyword_count += 1
                            break
                    if re.match(r'^[0-9]+$', val_lower.replace('.', '').replace(',', '').strip()):
                        numeric_count += 1

                keyword_ratio = keyword_count / len(non_empty) if len(non_empty) > 0 else 0
                numeric_penalty = numeric_count / len(non_empty) if len(non_empty) > 0 else 0
                text_ratio = 1 - numeric_penalty

                bonus = 0
                for val in non_empty:
                    val_lower = val.lower()
                    if 'ean' in val_lower or 'código' in val_lower or 'codigo' in val_lower:
                        bonus += 3
                    if 'precio' in val_lower or 'pvp' in val_lower:
                        bonus += 2

                avg_len = sum(len(v) for v in non_empty) / len(non_empty) if len(non_empty) > 0 else 0
                length_penalty = 1 if avg_len > 50 else 0

                score = (non_empty_ratio * 2) + (keyword_ratio * 5) + (text_ratio * 2) + bonus - (length_penalty * 2)

                if score > best_score:
                    best_score = score
                    best_row = row_idx

            except Exception:
                continue

        if best_score < 1.0:
            return 0

        return best_row

    @staticmethod
    def _clean_column_names(headers: List[str]) -> List[str]:
        """Limpia nombres de columnas garantizando que sean únicos y sin nulos fantasma."""
        cleaned = []
        for h in headers:
            try:
                h_str = str(h).strip() if h is not None else ""
                
                # Prevenir colapso por "nan" string de pandas
                if not h_str or h_str.lower() == 'nan':
                    h_str = f"columna_{len(cleaned)}"
                else:
                    h_str = re.sub(r'[^a-zA-Z0-9áéíóúñü\s]', '', h_str)
                    h_str = h_str.replace(' ', '_').lower()
                    h_str = Importer._normalize_text(h_str)
                    h_str = re.sub(r'_+', '_', h_str)
                    h_str = h_str.strip('_')
                    
                    if not h_str or h_str == 'nan':
                        h_str = f"columna_{len(cleaned)}"
                
                # Garantizar unicidad absoluta
                original_h_str = h_str
                counter = 1
                while h_str in cleaned:
                    h_str = f"{original_h_str}_{counter}"
                    counter += 1
                    
                cleaned.append(h_str)
            except Exception:
                cleaned.append(f"columna_{len(cleaned)}")
        return cleaned

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Elimina tildes y convierte a minúsculas para comparación."""
        try:
            text_str = str(text) if text is not None else ""
            if not text_str:
                return ""
            text_str = text_str.lower()
            nfkd = unicodedata.normalize('NFKD', text_str)
            return "".join(c for c in nfkd if not unicodedata.combining(c))
        except Exception:
            return ""


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
        """Importa un archivo Excel desde una ruta y retorna ImportResult."""
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

                # Detectar header
                header_row = Importer._detect_header_row(df_raw)
                if header_row is None:
                    header_row = 0

                # 🔥 RESCATE DEL TÍTULO (Memoria a corto plazo de la columna 0)
                last_title = None
                if header_row > 0:
                    for idx in range(header_row):
                        val = df_raw.iloc[idx, 0]
                        if pd.notna(val) and str(val).strip() and str(val).lower() != 'nan':
                            last_title = str(val).strip()

                # Extraer datos
                headers = df_raw.iloc[header_row].astype(str).str.strip().tolist()
                data_rows = df_raw.iloc[header_row + 1:].copy()
                data_rows.columns = headers

                # Limpiar nombres
                clean_headers = Importer._clean_column_names(headers)
                data_rows.columns = clean_headers

                # Eliminar filas vacías
                data_rows = data_rows.dropna(how='all')
                if data_rows.empty:
                    result.failed_sheets.append(SheetImportResult(
                        sheet_name=sheet_name,
                        success=False,
                        error="Sin datos después del header"
                    ))
                    continue

                # 🔥 INYECCIÓN SEGURA DEL TÍTULO HUÉRFANO (Sin Diccionarios)
                if last_title:
                    new_row_df = pd.DataFrame(np.nan, index=[0], columns=data_rows.columns)
                    new_row_df.iloc[0, 0] = last_title
                    data_rows = pd.concat([new_row_df, data_rows], ignore_index=True)

                # Añadir hoja de origen
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
