"""
Módulo de Importadores - Versión definitiva para openpyxl read_only=True.
Arquitectura en capas: Infraestructura (escáner), Dominio (modelos), Casos de uso (detectores y scorers).
"""
import re
import pandas as pd
from openpyxl import load_workbook
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum
from pathlib import Path
import tempfile
from datetime import datetime

# ============================================================
# CAPA DE DOMINIO (Modelos de datos)
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
    col_idx: int          # Siempre int (0-based)
    value: Any
    cell_type: CellType
    is_bold: bool = False
    has_fill: bool = False
    has_bottom_border: bool = False

@dataclass
class RowInfo:
    index: int            # Siempre int (0-based)
    cells: List[CellInfo] = field(default_factory=list)
    non_empty_count: int = 0
    text_count: int = 0
    number_count: int = 0
    bold_count: int = 0
    fill_count: int = 0
    border_count: int = 0

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
# CAPA DE INFRAESTRUCTURA (Adaptadores para openpyxl)
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
        if isinstance(value, datetime):
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

class SafeStyleExtractor:
    """Extrae estilos de forma segura en modo read_only."""
    @staticmethod
    def is_bold(cell) -> bool:
        try:
            return bool(cell.font and cell.font.bold)
        except Exception:
            return False

    @staticmethod
    def has_fill(cell) -> bool:
        try:
            return bool(cell.fill and cell.fill.fill_type is not None and str(cell.fill.fill_type).lower() != 'none')
        except Exception:
            return False

    @staticmethod
    def has_bottom_border(cell) -> bool:
        try:
            return bool(cell.border and cell.border.bottom and cell.border.bottom.style is not None)
        except Exception:
            return False

class WorksheetScanner:
    """
    Escáner de hoja que usa enumerate() para índices seguros.
    Lee solo un bounding box (max_rows x max_cols) para rendimiento.
    """
    @staticmethod
    def scan_head(ws, max_rows: int = 60, max_cols: int = 50) -> List[RowInfo]:
        rows_info = []
        for r_idx, row_cells in enumerate(ws.iter_rows(max_row=max_rows, max_col=max_cols, values_only=False)):
            if r_idx >= max_rows:
                break
            cells_info = []
            non_empty = 0
            text_cnt = 0
            num_cnt = 0
            bold_cnt = 0
            fill_cnt = 0
            border_cnt = 0

            for c_idx, cell in enumerate(row_cells):
                if c_idx >= max_cols:
                    break
                val = cell.value
                c_type = TypeClassifier.classify(val)
                is_bold = SafeStyleExtractor.is_bold(cell)
                has_fill = SafeStyleExtractor.has_fill(cell)
                has_border = SafeStyleExtractor.has_bottom_border(cell)

                if c_type != CellType.EMPTY:
                    non_empty += 1
                    if c_type == CellType.TEXT:
                        text_cnt += 1
                    elif c_type == CellType.NUMBER:
                        num_cnt += 1
                if is_bold:
                    bold_cnt += 1
                if has_fill:
                    fill_cnt += 1
                if has_border:
                    border_cnt += 1

                cells_info.append(CellInfo(
                    col_idx=c_idx,
                    value=val,
                    cell_type=c_type,
                    is_bold=is_bold,
                    has_fill=has_fill,
                    has_bottom_border=has_border
                ))

            # Solo conservamos filas con al menos una celda no vacía o estilos relevantes
            if non_empty > 0 or bold_cnt > 0 or fill_cnt > 0:
                rows_info.append(RowInfo(
                    index=r_idx,
                    cells=cells_info,
                    non_empty_count=non_empty,
                    text_count=text_cnt,
                    number_count=num_cnt,
                    bold_count=bold_cnt,
                    fill_count=fill_cnt,
                    border_count=border_cnt
                ))

        return rows_info

# ============================================================
# CAPA DE CASOS DE USO (Lógica de negocio)
# ============================================================

class TableRegionDetector:
    """Detecta la región tabular basándose en densidad de datos."""
    @staticmethod
    def detect_table_start(rows_info: List[RowInfo]) -> Optional[int]:
        if not rows_info:
            return None
        # Filtrar filas con al menos 2 celdas no vacías
        valid_rows = [r for r in rows_info if r.non_empty_count >= 2]
        if not valid_rows:
            return None
        # Buscar la primera fila donde la densidad de no-vacíos supere el 50% de la máxima
        max_non_empty = max(r.non_empty_count for r in valid_rows)
        threshold = max(3, int(max_non_empty * 0.5))
        for r in valid_rows:
            if r.non_empty_count >= threshold:
                return r.index
        # Fallback: primera fila con más de 2 celdas no vacías
        return valid_rows[0].index

class TaxonomyValidator:
    """Valida candidatos contra la taxonomía de AIPDP."""
    def __init__(self):
        try:
            from backend.pipelines.detectors import ColumnMapper
            self.mapper = ColumnMapper(confidence_threshold=0.0)
        except ImportError:
            self.mapper = None

    def validate(self, headers: List[str]) -> Tuple[float, float]:
        if not headers or self.mapper is None:
            return 0.0, 0.0
        dummy = pd.DataFrame([headers], columns=headers)
        mapping = self.mapper.map_columns(dummy)
        mapped = 0
        total_conf = 0.0
        for col, (field, conf) in mapping.items():
            if field is not None:
                mapped += 1
                total_conf += conf
        total = len(mapping)
        if total == 0:
            return 0.0, 0.0
        return mapped / total, total_conf / max(1, mapped)

class HeaderScorer:
    """Puntúa filas candidatas combinando densidad de texto, estilos y taxonomía."""
    def __init__(self):
        self.taxonomy_validator = TaxonomyValidator()

    def score_candidate(self, row_info: RowInfo, rows_info: List[RowInfo]) -> float:
        if row_info.non_empty_count < 2:
            return -1000.0

        total_cells = len(row_info.cells) or 1
        # 1. Densidad de texto vs números
        text_ratio = (row_info.text_count or 0) / total_cells
        # 2. Estilos visuales (negrita, relleno, borde)
        style_bonus = (row_info.bold_count * 2) + (row_info.fill_count * 1.5) + (row_info.border_count * 1.0)
        # 3. Taxonomía (si la fila tiene al menos 3 celdas no vacías)
        taxonomy_score = 0.0
        if row_info.non_empty_count >= 3:
            headers = [cell.value for cell in row_info.cells if cell.value is not None and str(cell.value).strip()]
            if headers:
                mapeo, conf = self.taxonomy_validator.validate(headers)
                taxonomy_score = (mapeo * 0.7 + conf * 0.3) * 5.0  # peso extra

        # 4. Validación con la fila siguiente (si existe)
        next_idx = row_info.index + 1
        next_bonus = 0.0
        if next_idx < len(rows_info):
            next_row = rows_info[next_idx]
            if next_row.number_count > 2:  # si la fila siguiente tiene números, refuerza la hipótesis
                next_bonus = 3.0

        score = (text_ratio * 10.0) + style_bonus + taxonomy_score + next_bonus + (row_info.non_empty_count * 0.2)
        return float(score)

# ============================================================
# ORQUESTADOR PRINCIPAL
# ============================================================

class WorkbookReader:
    @staticmethod
    def open_workbook(filepath):
        return load_workbook(filepath, read_only=True, data_only=True)

    @staticmethod
    def sheets(workbook):
        for sheet_name in workbook.sheetnames:
            yield workbook[sheet_name], sheet_name

    @staticmethod
    def close_workbook(workbook):
        workbook.close()

class ExcelImporter:
    def __init__(self, max_scan_rows: int = 60, max_scan_cols: int = 50):
        self.max_scan_rows = max_scan_rows
        self.max_scan_cols = max_scan_cols

    def import_from_bytes(self, data: bytes, filename: str) -> ImportResult:
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        try:
            return self.import_from_path(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def import_from_path(self, filepath: Path) -> ImportResult:
        result = ImportResult(filename=str(filepath))
        workbook = None
        try:
            workbook = WorkbookReader.open_workbook(filepath)
            for worksheet, sheet_name in WorkbookReader.sheets(workbook):
                try:
                    sheet_result = self._process_sheet(worksheet, sheet_name, filepath)
                    if sheet_result.success:
                        result.successful_sheets.append(sheet_result)
                    else:
                        result.failed_sheets.append(sheet_result)
                except Exception as e:
                    result.failed_sheets.append(SheetImportResult(
                        sheet_name=sheet_name,
                        success=False,
                        error=str(e)
                    ))
        except Exception as e:
            result.failed_sheets.append(SheetImportResult(
                sheet_name="<workbook>",
                success=False,
                error=f"Error al abrir el libro: {e}"
            ))
        finally:
            if workbook:
                WorkbookReader.close_workbook(workbook)

        result.total_sheets = len(result.successful_sheets) + len(result.failed_sheets)
        result.total_successful = len(result.successful_sheets)
        result.total_failed = len(result.failed_sheets)
        return result

    def _process_sheet(self, worksheet, sheet_name: str, filepath: Path) -> SheetImportResult:
        # 1. Escaneo seguro de las primeras filas
        rows_info = WorksheetScanner.scan_head(worksheet, self.max_scan_rows, self.max_scan_cols)
        if not rows_info:
            return SheetImportResult(
                sheet_name=sheet_name,
                success=False,
                error="No se pudieron escanear filas (hoja vacía o demasiado pequeña)."
            )

        # 2. Detectar región tabular (inicio de los datos)
        table_start = TableRegionDetector.detect_table_start(rows_info)
        if table_start is None:
            return SheetImportResult(
                sheet_name=sheet_name,
                success=False,
                error="No se pudo detectar una región tabular válida."
            )

        # 3. Generar candidatos a encabezado (alrededor del inicio de la tabla)
        candidates = self._generate_candidates(rows_info, table_start)

        # 4. Puntuar cada candidato
        scorer = HeaderScorer()
        scores = {}
        for row_idx in candidates:
            if row_idx < len(rows_info):
                score = scorer.score_candidate(rows_info[row_idx], rows_info)
                scores[row_idx] = score

        if not scores:
            return SheetImportResult(
                sheet_name=sheet_name,
                success=False,
                error="No se generaron candidatos a encabezado."
            )

        # 5. Seleccionar el mejor candidato
        best_row = max(scores, key=scores.get)
        best_score = scores[best_row]
        confidence = min(1.0, max(0.0, best_score / 30.0))  # normalización aproximada

        # 6. Si la confianza es baja, intentar fallback por taxonomía
        if confidence < 0.3:
            # Buscar fila con mejor mapeo a taxonomía entre las primeras 10
            fallback_candidates = list(range(min(10, len(rows_info))))
            best_taxonomy_score = -1
            best_taxonomy_row = 0
            for row_idx in fallback_candidates:
                if row_idx >= len(rows_info):
                    continue
                row_info = rows_info[row_idx]
                headers = [cell.value for cell in row_info.cells if cell.value is not None and str(cell.value).strip()]
                if headers:
                    mapeo, conf = TaxonomyValidator().validate(headers)
                    taxonomy_score = mapeo * 0.7 + conf * 0.3
                    if taxonomy_score > best_taxonomy_score:
                        best_taxonomy_score = taxonomy_score
                        best_taxonomy_row = row_idx
            if best_taxonomy_score > 0.5:
                best_row = best_taxonomy_row
                confidence = max(confidence, 0.4)

        header_result = HeaderDetectionResult(
            header_row=best_row,
            table_start=table_start,
            confidence=confidence,
            strategy="hybrid",
            diagnostics={'scores': scores, 'best_score': best_score}
        )

        if confidence < 0.2:
            return SheetImportResult(
                sheet_name=sheet_name,
                success=False,
                error="No se pudo detectar la fila de encabezados con confianza suficiente.",
                diagnostics={'header_result': header_result}
            )

        # 7. Leer la hoja con pandas a partir de la fila de encabezados detectada
        try:
            df = self._read_sheet_with_pandas(filepath, sheet_name, header_result)
        except Exception as e:
            return SheetImportResult(
                sheet_name=sheet_name,
                success=False,
                error=f"Error al leer la hoja con pandas: {e}",
                header_result=header_result
            )

        return SheetImportResult(
            sheet_name=sheet_name,
            success=True,
            header_result=header_result,
            dataframe=df,
            diagnostics={'scores': scores}
        )

    def _generate_candidates(self, rows_info: List[RowInfo], table_start: int) -> List[int]:
        """Genera candidatos alrededor del inicio de la tabla."""
        candidates = set()
        for offset in range(-4, 5):
            row = table_start + offset
            if 0 <= row < len(rows_info):
                candidates.add(row)
        # Si no hay candidatos, usar las primeras 5 filas
        if not candidates:
            candidates.update(range(min(5, len(rows_info))))
        return sorted(candidates)

    def _read_sheet_with_pandas(self, filepath: Path, sheet_name: str, header_result: HeaderDetectionResult) -> pd.DataFrame:
        header_row = header_result.header_row
        return pd.read_excel(
            filepath,
            sheet_name=sheet_name,
            header=header_row,
            engine='openpyxl'
        )

# ============================================================
# FUNCIÓN DE ENTRADA
# ============================================================

def import_excel(data: bytes, filename: str) -> ImportResult:
    """
    Función principal para importar archivos Excel.
    Retorna un objeto ImportResult con las hojas procesadas.
    """
    importer = ExcelImporter()
    return importer.import_from_bytes(data, filename)
