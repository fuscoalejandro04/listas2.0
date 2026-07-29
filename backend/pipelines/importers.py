"""
Módulo de Importadores - Adaptadores para leer datos desde diferentes fuentes.
Soporte inicial: Excel (.xlsx, .xls) y CSV.
Ahora permite leer todas las hojas de un Excel y unificarlas.
"""
import pandas as pd
from typing import Union, Dict, Optional
from pathlib import Path
import io

class Importer:
    """Clase base para importadores (por si queremos extender en el futuro)."""
    
    @staticmethod
    def read(file_path: Union[str, Path]) -> pd.DataFrame:
        """Lee un archivo y devuelve un DataFrame. Detecta extensión automáticamente."""
        path = Path(file_path)
        if path.suffix in ['.xlsx', '.xls']:
            # Leer todas las hojas y concatenarlas
            return Importer._read_excel_all_sheets(path)
        elif path.suffix == '.csv':
            # Intenta detectar separador automáticamente
            return pd.read_csv(path, encoding='utf-8', sep=None, engine='python')
        else:
            raise ValueError(f"Formato no soportado: {path.suffix}")

    @staticmethod
    def read_from_bytes(data: bytes, filename: str) -> pd.DataFrame:
        """Lee desde bytes (útil para archivos subidos por Streamlit)."""
        if filename.endswith('.xlsx') or filename.endswith('.xls'):
            # Leer todas las hojas del Excel
            return Importer._read_excel_all_sheets_from_bytes(data)
        elif filename.endswith('.csv'):
            return pd.read_csv(io.BytesIO(data), encoding='utf-8', sep=None, engine='python')
        else:
            raise ValueError(f"Formato no soportado: {filename}")

    @staticmethod
    def _read_excel_all_sheets(file_path: Path) -> pd.DataFrame:
        """Lee todas las hojas de un archivo Excel y las combina en un DataFrame."""
        # Leer todas las hojas en un diccionario
        sheets_dict = pd.read_excel(file_path, sheet_name=None, engine='openpyxl' if file_path.suffix == '.xlsx' else 'xlrd')
        return Importer._combine_sheets(sheets_dict)

    @staticmethod
    def _read_excel_all_sheets_from_bytes(data: bytes) -> pd.DataFrame:
        """Lee todas las hojas de un archivo Excel desde bytes."""
        sheets_dict = pd.read_excel(io.BytesIO(data), sheet_name=None, engine='openpyxl')
        return Importer._combine_sheets(sheets_dict)

    @staticmethod
    def _combine_sheets(sheets_dict: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        Combina un diccionario de hojas en un solo DataFrame, añadiendo una columna 'hoja_origen'.
        Ignora hojas vacías o con solo encabezados sin datos.
        """
        combined_dfs = []
        for sheet_name, df in sheets_dict.items():
            # Limpiar la hoja: eliminar filas vacías y resetear índices
            df_clean = df.dropna(how='all').reset_index(drop=True)
            if df_clean.empty:
                continue
            # Añadir columna con el nombre de la hoja
            df_clean['hoja_origen'] = sheet_name
            combined_dfs.append(df_clean)
        if not combined_dfs:
            raise ValueError("No se encontraron hojas con datos en el archivo.")
        # Concatenar todas las hojas
        return pd.concat(combined_dfs, ignore_index=True)

    @staticmethod
    def read_sheet(file_path: Union[str, Path], sheet_name: Optional[str] = None) -> pd.DataFrame:
        """Lee una hoja específica del Excel (para uso opcional)."""
        path = Path(file_path)
        if path.suffix in ['.xlsx', '.xls']:
            return pd.read_excel(path, sheet_name=sheet_name, engine='openpyxl' if path.suffix == '.xlsx' else 'xlrd')
        else:
            raise ValueError("Este método solo soporta archivos Excel.")
