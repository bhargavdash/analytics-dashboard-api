from pydantic import BaseModel
from app.models.widgets import DataRow


class DatasetColumn(BaseModel):
    name: str
    type: str


class DatasetRecord(BaseModel):
    id: str
    name: str               # original filename (display)
    source: str             # 'csv' | 'xlsx'
    table_name: str         # DuckDB table backing this dataset
    columns: list[DatasetColumn] = []
    sample: list[DataRow] = []
    suggestions: list[str] = []
    row_count: int
    created_at: str
