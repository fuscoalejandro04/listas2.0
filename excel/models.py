from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum

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
    """Información de una celda escaneada."""
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
    """Información de una fila escaneada."""
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
    """Resultado de la detección de encabezados y región tabular."""
    header_row: Optional[int]          # índice base 0 de la fila de encabezados
    table_start: Optional[int]         # índice base 0 de la primera fila de datos
    confidence: float                  # puntuación de confianza (0..1)
    strategy: str                      # estrategia usada (ej. "bottom_up+taxonomy")
    diagnostics: Dict[str, Any] = field(default_factory=dict)  # información de depuración

@dataclass
class SheetImportResult:
    """Resultado de la importación de una hoja."""
    sheet_name: str
    success: bool
    header_result: Optional[HeaderDetectionResult] = None
    dataframe: Optional[pd.DataFrame] = None
    error: Optional[str] = None
    diagnostics: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ImportResult:
    """Resultado global de la importación del archivo."""
    filename: str
    successful_sheets: List[SheetImportResult] = field(default_factory=list)
    failed_sheets: List[SheetImportResult] = field(default_factory=list)
    total_sheets: int = 0
    total_successful: int = 0
    total_failed: int = 0
