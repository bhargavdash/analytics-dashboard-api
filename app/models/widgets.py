from __future__ import annotations
from typing import Literal, Union, Annotated
from pydantic import BaseModel, Field

# Mirrors src/types/index.ts exactly — same field names, same optional fields.
# DataRow matches TypeScript's `Record<string, string | number | null>`.
DataRow = dict[str, str | int | float | None]


# --- Payload models ---

class StatCardPayload(BaseModel):
    value: str
    delta: str | None = None
    up: bool | None = None
    vs: str | None = None


class LineSeries(BaseModel):
    key: str
    color: str
    label: str | None = None
    dashed: bool | None = None


class LineChartPayload(BaseModel):
    data: list[DataRow]
    xKey: str
    series: list[LineSeries]
    unit: str | None = None


class PieSlice(BaseModel):
    name: str
    value: float
    color: str


class PieChartPayload(BaseModel):
    slices: list[PieSlice]


class BarSeries(BaseModel):
    key: str
    color: str
    label: str | None = None


class BarChartPayload(BaseModel):
    data: list[DataRow]
    xKey: str
    series: list[BarSeries]
    unit: str | None = None


class TableColumn(BaseModel):
    key: str
    label: str


class TablePayload(BaseModel):
    data: list[DataRow]
    columns: list[TableColumn]


# --- Widget models (one per discriminator value) ---

class StatCardWidget(BaseModel):
    type: Literal['stat_card']
    span: int
    title: str
    payload: StatCardPayload


class LineChartWidget(BaseModel):
    type: Literal['line_chart']
    span: int
    title: str
    payload: LineChartPayload


class PieChartWidget(BaseModel):
    type: Literal['pie_chart']
    span: int
    title: str
    payload: PieChartPayload


class BarChartWidget(BaseModel):
    type: Literal['bar_chart']
    span: int
    title: str
    payload: BarChartPayload


class TableWidget(BaseModel):
    type: Literal['table']
    span: int
    title: str
    payload: TablePayload


# Discriminated union — Pydantic reads `type` field to pick the right model.
# Mirrors TypeScript: type Widget = | { type: 'stat_card'; ... } | { type: 'bar_chart'; ... } | ...
Widget = Annotated[
    Union[StatCardWidget, LineChartWidget, PieChartWidget, BarChartWidget, TableWidget],
    Field(discriminator='type')
]


# --- Top-level response ---

class DashboardSchema(BaseModel):
    summary: str
    widgets: list[Widget]
