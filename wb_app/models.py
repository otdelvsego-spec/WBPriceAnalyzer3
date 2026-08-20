from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Product:
    article: str
    name: str
    material_cost: float = 0.0
    labor_cost: float = 0.0
    active: bool = True
    sort_order: int | None = None
    category: str = ""

    @property
    def total_cost(self) -> float:
        return self.material_cost + self.labor_cost


@dataclass(slots=True)
class AccrualRow:
    """One operation from a WB weekly detailed financial report.

    The historical class name is kept so database and UI helpers inherited from
    OZ Price Analyzer can be migrated without a destructive storage change.
    """

    source_name: str
    sheet_name: str
    row_number: int
    report_number: str
    operation_date: date | None
    sale_date: date | None
    document_type: str
    payment_reason: str
    article: str
    nm_id: str
    product_name: str
    subject: str
    quantity: float
    retail_price: float
    realized_price: float
    seller_payout: float
    logistics: float = 0.0
    # Informational coefficient from newer WB exports. The monetary logistics
    # amount above already includes it, so calculations must not apply it again.
    logistics_coefficient: float = 0.0
    penalty: float = 0.0
    storage: float = 0.0
    acceptance: float = 0.0
    commission_adjustment: float = 0.0
    deductions: float = 0.0
    loyalty_compensation: float = 0.0
    loyalty_fee: float = 0.0
    loyalty_points: float = 0.0
    payout_fee: float = 0.0
    acquiring: float = 0.0
    pvz_reimbursement: float = 0.0
    wb_commission: float = 0.0
    carrier_reimbursement: float = 0.0
    country: str = ""
    srid: str = ""
    operation_detail: str = ""

    @property
    def accrual_id(self) -> str:
        return self.srid or f"{self.report_number}:{self.row_number}"

    @property
    def accrual_date(self) -> date | None:
        return self.sale_date or self.operation_date

    @property
    def accrual_type(self) -> str:
        return self.payment_reason

    @property
    def sku(self) -> str:
        return self.nm_id

    @property
    def seller_price(self) -> float:
        return self.retail_price

    @property
    def amount(self) -> float:
        """Net cash impact before tax and cost of goods."""
        sign = -1.0 if self.document_type.strip().casefold() == "возврат" else 1.0
        return (
            sign * self.seller_payout
            - self.logistics
            - self.penalty
            - self.storage
            - self.acceptance
            - self.commission_adjustment
            - self.deductions
            + sign * self.loyalty_compensation
            - sign * self.loyalty_fee
            - sign * self.loyalty_points
            - self.payout_fee
        )

    @property
    def service_group(self) -> str:
        return self.document_type


@dataclass(slots=True)
class RealizationRow:
    """Compatibility placeholder; WB imports do not use a separate sales file."""

    source_name: str = ""
    sheet_name: str = ""
    row_number: int = 0
    raw_article: str = ""
    sku: str = ""
    product_name: str = ""
    shipment: str = ""
    unit_price: float = 0.0
    quantity: float = 0.0
    amount: float = 0.0


@dataclass(slots=True)
class ParsedSource:
    path: Path
    file_hash: str
    report_type: str
    sheet_name: str
    header_row: int
    accrual_rows: list[AccrualRow] = field(default_factory=list)
    realization_rows: list[RealizationRow] = field(default_factory=list)
    period_start: date | None = None
    period_end: date | None = None
    duplicate_run_ids: list[int] = field(default_factory=list)
    report_number: str = ""
    report_variant: str = "основной"
    out_of_period_rows: int = 0
    unknown_columns: list[str] = field(default_factory=list)

    @property
    def row_count(self) -> int:
        return len(self.accrual_rows)

    @property
    def total_amount(self) -> float:
        return sum(row.amount for row in self.accrual_rows)


@dataclass(slots=True)
class UnknownProduct:
    article: str
    name: str
    sku: str
    source_names: set[str] = field(default_factory=set)


@dataclass(slots=True)
class ProductResult:
    article: str
    name: str
    material_cost: float
    labor_cost: float
    category: str = ""
    units: float = 0.0

    # Persisted legacy field names and their WB meanings:
    revenue_no_points: float = 0.0       # retail price total
    partner_programs: float = 0.0        # WB realized price total
    points: float = 0.0                  # seller payout total
    commission: float = 0.0              # WB commission, analytic only
    processing: float = 0.0              # PVZ reimbursement, analytic only
    delivery: float = 0.0                # logistics
    logistics: float = 0.0               # penalties
    reverse_logistics: float = 0.0       # acceptance
    returns_cancels: float = 0.0         # storage
    acquiring: float = 0.0               # acquiring, analytic only
    stars: float = 0.0                   # loyalty compensation
    packaging: float = 0.0               # loyalty fee and points impact
    compensation: float = 0.0            # adjustments/deductions/payout fee
    other: float = 0.0                   # other mapped cash impact
    financial_result: float = 0.0
    carrier_reimbursement: float = 0.0   # neutral control field
    material_sold_override: float | None = None
    labor_sold_override: float | None = None
    tax_override: float | None = None

    @property
    def retail_price_total(self) -> float:
        return self.revenue_no_points

    @retail_price_total.setter
    def retail_price_total(self, value: float) -> None:
        self.revenue_no_points = value

    @property
    def realized_price_total(self) -> float:
        return self.partner_programs

    @realized_price_total.setter
    def realized_price_total(self, value: float) -> None:
        self.partner_programs = value

    @property
    def seller_payout(self) -> float:
        return self.points

    @seller_payout.setter
    def seller_payout(self, value: float) -> None:
        self.points = value

    @property
    def wb_commission(self) -> float:
        return self.commission

    @wb_commission.setter
    def wb_commission(self, value: float) -> None:
        self.commission = value

    @property
    def pvz_reimbursement(self) -> float:
        return self.processing

    @pvz_reimbursement.setter
    def pvz_reimbursement(self, value: float) -> None:
        self.processing = value

    @property
    def logistics_cost(self) -> float:
        return self.delivery

    @logistics_cost.setter
    def logistics_cost(self, value: float) -> None:
        self.delivery = value

    @property
    def penalty_cost(self) -> float:
        return self.logistics

    @penalty_cost.setter
    def penalty_cost(self, value: float) -> None:
        self.logistics = value

    @property
    def acceptance_cost(self) -> float:
        return self.reverse_logistics

    @acceptance_cost.setter
    def acceptance_cost(self, value: float) -> None:
        self.reverse_logistics = value

    @property
    def storage_cost(self) -> float:
        return self.returns_cancels

    @storage_cost.setter
    def storage_cost(self, value: float) -> None:
        self.returns_cancels = value

    @property
    def loyalty_compensation(self) -> float:
        return self.stars

    @loyalty_compensation.setter
    def loyalty_compensation(self, value: float) -> None:
        self.stars = value

    @property
    def loyalty_cost(self) -> float:
        return self.packaging

    @loyalty_cost.setter
    def loyalty_cost(self, value: float) -> None:
        self.packaging = value

    @property
    def adjustments(self) -> float:
        return self.compensation

    @adjustments.setter
    def adjustments(self, value: float) -> None:
        self.compensation = value

    @property
    def total_cost(self) -> float:
        return self.material_cost + self.labor_cost

    @property
    def material_sold(self) -> float:
        if self.material_sold_override is not None:
            return self.material_sold_override
        return self.material_cost * self.units

    @property
    def labor_sold(self) -> float:
        if self.labor_sold_override is not None:
            return self.labor_sold_override
        return self.labor_cost * self.units

    @property
    def cost_sold(self) -> float:
        return self.material_sold + self.labor_sold

    @property
    def revenue_including_points(self) -> float:
        return self.retail_price_total

    @property
    def taxable_income(self) -> float:
        return self.retail_price_total

    def tax(self, rate: float) -> float:
        if self.tax_override is not None:
            return self.tax_override
        return self.taxable_income * rate

    def net_profit(self, rate: float) -> float:
        return self.financial_result - self.cost_sold - self.tax(rate)

    def average_price(self) -> float | None:
        return self.retail_price_total / self.units if self.units else None

    def profit_per_unit(self) -> float:
        return self.financial_result / self.units if self.units else 0.0

    def net_profit_per_unit(self, rate: float) -> float:
        return self.net_profit(rate) / self.units if self.units else 0.0

    def profitability(self, rate: float) -> float:
        return self.net_profit(rate) / self.cost_sold if self.cost_sold else 0.0

    def commission_share(self) -> float:
        revenue = self.revenue_including_points
        return -self.wb_commission / revenue if revenue else 0.0

    def logistics_share(self) -> float:
        revenue = self.revenue_including_points
        return -self.logistics_cost / revenue if revenue else 0.0

    def points_share(self) -> float:
        revenue = self.revenue_including_points
        return -self.loyalty_cost / revenue if revenue else 0.0

    def net_margin(self, rate: float) -> float:
        revenue = self.revenue_including_points
        return self.net_profit(rate) / revenue if revenue else 0.0


@dataclass(slots=True)
class RunCalculation:
    run_id: int | None
    period_start: date | None
    period_end: date | None
    tax_rate: float
    products: list[ProductResult]
    unallocated_total: float
    unallocated: dict[str, tuple[int, float]]
    accrual_stats: dict[str, tuple[int, int]]
    source_files: list[ParsedSource] = field(default_factory=list)
    skipped_articles: dict[str, str] = field(default_factory=dict)
    sku_conflicts: set[str] = field(default_factory=set)
    duplicate_realization_rows: int = 0
    already_accrued_realization_rows: int = 0
    realization_revenue: float = 0.0
    realization_units: float = 0.0
    source_period_warnings: list[str] = field(default_factory=list)

    def totals(self) -> dict[str, float]:
        return {
            "units": sum(item.units for item in self.products),
            "revenue": sum(item.revenue_including_points for item in self.products),
            "realized_revenue": sum(item.realized_price_total for item in self.products),
            "seller_payout": sum(item.seller_payout for item in self.products),
            "financial_result": (
                sum(item.financial_result for item in self.products)
                + self.unallocated_total
            ),
            "cost_sold": sum(item.cost_sold for item in self.products),
            "tax": sum(item.tax(self.tax_rate) for item in self.products),
            "net_profit": (
                sum(item.net_profit(self.tax_rate) for item in self.products)
                + self.unallocated_total
            ),
            "unallocated": self.unallocated_total,
        }

    def revenue_shares(self) -> dict[str, float]:
        revenue = sum(item.revenue_including_points for item in self.products)
        if not revenue:
            return {
                "commission_share": 0.0,
                "logistics_share": 0.0,
                "points_share": 0.0,
                "net_margin": 0.0,
            }
        return {
            "commission_share": -sum(item.wb_commission for item in self.products) / revenue,
            "logistics_share": -sum(item.logistics_cost for item in self.products) / revenue,
            "points_share": -sum(item.loyalty_cost for item in self.products) / revenue,
            "net_margin": (
                sum(item.net_profit(self.tax_rate) for item in self.products)
                + self.unallocated_total
            ) / revenue,
        }

    def revenue_amounts(self) -> dict[str, float]:
        """Return the monetary numerators used by the revenue-share KPIs."""
        return {
            "commission": -sum(item.wb_commission for item in self.products),
            "logistics": -sum(item.logistics_cost for item in self.products),
            "points": -sum(item.loyalty_cost for item in self.products),
        }


@dataclass(slots=True)
class ScenarioRow:
    article: str
    name: str
    category: str
    unit_cost: float
    units: float
    current_price: float | None
    planned_price: float | None
    price_change: float | None
    profitability: float | None
    ozon_costs_without_commission: float | None
    planned_revenue: float | None
    commission_rate: float | None
    planned_commission: float | None
    planned_points: float | None
    taxable_base: float | None
    tax: float | None
    profit: float | None
    profit_per_unit_before_cost: float | None
    net_profit_per_unit: float | None

    @property
    def wb_costs_without_commission(self) -> float | None:
        return self.ozon_costs_without_commission

    @property
    def net_profit_total(self) -> float | None:
        if self.net_profit_per_unit is None:
            return None
        return self.net_profit_per_unit * self.units


@dataclass(slots=True)
class RunSummary:
    id: int
    created_at: str
    period_start: str | None
    period_end: str | None
    source_count: int
    units: float
    revenue: float
    net_profit: float
    unallocated_total: float
    status: str
    report_name: str = ""
    profitability: float = 0.0
    commission_share: float = 0.0
    logistics_share: float = 0.0
    points_share: float = 0.0
    net_margin: float = 0.0


def as_serializable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value
