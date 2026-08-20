from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import date

from .excel_reader import all_rows, normalize_text
from .models import AccrualRow, ParsedSource, Product, ProductResult, RunCalculation, ScenarioRow, UnknownProduct


class CalculationError(ValueError):
    pass


def _type_key(value: str) -> str:
    return normalize_text(value).replace("ё", "е")


def distribution_status(with_article: int, without_article: int, empty: str = "НЕТ ДАННЫХ") -> str:
    if with_article > 0 and without_article > 0:
        return "СМЕШАННОЕ РАСПРЕДЕЛЕНИЕ"
    if with_article > 0:
        return "ПО АРТИКУЛУ"
    if without_article > 0:
        return "НЕРАСПРЕДЕЛЕННЫЕ ДОХОДЫ/РАСХОДЫ"
    return empty


def accrual_category(accrual_type: str) -> tuple[str, str]:
    """Describe the principal WB component for the guide tab."""
    key = _type_key(accrual_type)
    if key in {_type_key("Продажа"), _type_key("Возврат")}:
        return "points", "К перечислению продавцу"
    if "логист" in key:
        return "delivery", "Логистика"
    if "хранен" in key:
        return "returns_cancels", "Хранение"
    if "штраф" in key:
        return "logistics", "Штрафы"
    if "обработка товара" in key or "приемк" in key:
        return "reverse_logistics", "Операции на приемке"
    if "лояльност" in key:
        return "stars", "Программа лояльности"
    if "удерж" in key or "коррект" in key or "срок перечисления" in key:
        return "compensation", "Корректировки и удержания"
    return "other", "Состав строки по полям WB"


def guide_target(accrual_type: str) -> str:
    component = accrual_category(accrual_type)[1]
    return f"С артикулом → товар ({component}); без артикула → разбивка"


def build_sku_map(rows, allowed_articles: set[str] | None = None) -> tuple[dict[str, str], set[str]]:
    mapping: dict[str, str] = {}
    conflicts: set[str] = set()
    for row in rows:
        if not row.sku or not row.article:
            continue
        if allowed_articles is not None and row.article not in allowed_articles:
            continue
        if row.sku in conflicts:
            continue
        existing = mapping.get(row.sku)
        if existing and existing != row.article:
            mapping.pop(row.sku, None)
            conflicts.add(row.sku)
        else:
            mapping[row.sku] = row.article
    return mapping, conflicts


def discover_unknown_products(sources: list[ParsedSource], products: dict[str, Product]) -> list[UnknownProduct]:
    rows, _unused = all_rows(sources)
    unknown: dict[str, UnknownProduct] = {}
    for row in rows:
        if not row.article or row.article in products:
            continue
        item = unknown.setdefault(
            row.article,
            UnknownProduct(
                article=row.article,
                name=row.product_name or row.article,
                sku=row.nm_id,
            ),
        )
        if item.name == item.article and row.product_name:
            item.name = row.product_name
        if not item.sku and row.nm_id:
            item.sku = row.nm_id
        item.source_names.add(row.source_name)
    return sorted(unknown.values(), key=lambda item: item.article.casefold())


def _document_sign(row: AccrualRow) -> float:
    return -1.0 if _type_key(row.document_type) == _type_key("Возврат") else 1.0


def _is_sale_document(row: AccrualRow) -> bool:
    return _type_key(row.document_type) in {
        _type_key("Продажа"),
        _type_key("Возврат"),
    }


def _apply_row(result: ProductResult, row: AccrualRow) -> None:
    sign = _document_sign(row)
    if _is_sale_document(row):
        # Quantity=2 on carrier reimbursement rows is explicitly not a sale.
        if _type_key(row.payment_reason) in {_type_key("Продажа"), _type_key("Возврат")}:
            result.units += sign * row.quantity
        result.retail_price_total += sign * row.retail_price
        result.realized_price_total += sign * row.realized_price
        result.seller_payout += sign * row.seller_payout
        result.wb_commission += -sign * row.wb_commission
        result.acquiring += -sign * row.acquiring
        result.pvz_reimbursement += -sign * row.pvz_reimbursement
    else:
        # Compensation/adjustment rows can carry payout without a sale document.
        # Keep it outside the sale payout ratio used by the price scenario.
        result.other += row.seller_payout

    result.logistics_cost += -row.logistics
    result.penalty_cost += -row.penalty
    result.storage_cost += -row.storage
    result.acceptance_cost += -row.acceptance
    result.loyalty_compensation += sign * row.loyalty_compensation
    result.loyalty_cost += -sign * (row.loyalty_fee + row.loyalty_points)
    result.adjustments += -(
        row.commission_adjustment + row.deductions + row.payout_fee
    )
    result.carrier_reimbursement += row.carrier_reimbursement
    result.financial_result += row.amount


def calculate_run(
    sources: list[ParsedSource],
    products: dict[str, Product],
    tax_rate: float,
    skipped_articles: set[str] | None = None,
) -> RunCalculation:
    skipped_articles = skipped_articles or set()
    rows, _unused = all_rows(sources)
    if not rows:
        raise CalculationError("В выбранных файлах нет операций Wildberries")

    referenced_articles = {row.article for row in rows if row.article}
    calculation_products = {
        article: product
        for article, product in products.items()
        if (product.active or article in referenced_articles)
        and article not in skipped_articles
    }
    results = {
        article: ProductResult(
            article=product.article,
            name=product.name,
            material_cost=product.material_cost,
            labor_cost=product.labor_cost,
            category=product.category,
        )
        for article, product in calculation_products.items()
    }
    _sku_map, sku_conflicts = build_sku_map(rows, set(results))

    stats_raw: dict[str, list[object]] = {}
    breakdown_raw: dict[str, list[object]] = {}
    skipped_detail: dict[str, str] = {}
    skipped_amounts: dict[str, float] = defaultdict(float)
    allocated_total = 0.0
    skipped_total = 0.0
    unallocated_total = 0.0

    for row in rows:
        type_key = _type_key(row.payment_reason) or "без обоснования"
        stat = stats_raw.setdefault(type_key, [row.payment_reason or "Без обоснования", 0, 0])
        stat[1 if row.article else 2] = int(stat[1 if row.article else 2]) + 1

        if not row.article:
            unallocated_total += row.amount
            detail = breakdown_raw.setdefault(type_key, [row.payment_reason or "Без обоснования", 0, 0.0])
            detail[1] = int(detail[1]) + 1
            detail[2] = float(detail[2]) + row.amount
            continue

        result = results.get(row.article)
        if result is None or row.article in skipped_articles:
            skipped_detail.setdefault(
                row.article,
                f"{row.article} — {row.product_name or row.article} "
                f"({row.source_name}, строка {row.row_number})",
            )
            skipped_amounts[row.article] += row.amount
            skipped_total += row.amount
            continue

        _apply_row(result, row)
        allocated_total += row.amount

    source_total = sum(row.amount for row in rows)
    allocation_difference = source_total - allocated_total - unallocated_total - skipped_total
    if abs(allocation_difference) > 0.01:
        raise CalculationError(
            "Не сошелся контроль распределения операций WB: "
            f"расхождение {allocation_difference:.2f} руб."
        )

    for article, amount in skipped_amounts.items():
        skipped_detail[article] = (
            f"{skipped_detail[article]}; пропущенный финансовый результат — "
            f"{_money_ru(amount)}"
        )

    starts = [source.period_start for source in sources if source.period_start]
    ends = [source.period_end for source in sources if source.period_end]
    warnings = []
    for source in sources:
        if source.out_of_period_rows:
            warnings.append(
                f"«{source.path.name}»: {source.out_of_period_rows} строк относятся "
                "к другой неделе; они учтены как корректировки текущего отчета."
            )
        if source.unknown_columns:
            warnings.append(
                f"«{source.path.name}»: найдены неизвестные столбцы WB: "
                + ", ".join(source.unknown_columns)
                + ". Проверьте их назначение перед подтверждением расчета."
            )

    stats = {
        str(values[0]): (int(values[1]), int(values[2]))
        for values in sorted(stats_raw.values(), key=lambda value: str(value[0]).casefold())
    }
    unallocated = {
        str(values[0]): (int(values[1]), float(values[2]))
        for values in sorted(breakdown_raw.values(), key=lambda value: str(value[0]).casefold())
    }
    return RunCalculation(
        run_id=None,
        period_start=min(starts) if starts else None,
        period_end=max(ends) if ends else None,
        tax_rate=tax_rate,
        products=sorted(results.values(), key=lambda item: item.article.casefold()),
        unallocated_total=unallocated_total,
        unallocated=unallocated,
        accrual_stats=stats,
        source_files=sources,
        skipped_articles=skipped_detail,
        sku_conflicts=sku_conflicts,
        realization_revenue=sum(result.realized_price_total for result in results.values()),
        realization_units=sum(result.units for result in results.values()),
        source_period_warnings=warnings,
    )


def calculate_scenario(result: ProductResult, tax_rate: float, planned_price: float | None = None) -> ScenarioRow:
    current_price = result.average_price()
    if planned_price is None:
        planned_price = current_price
    if result.units <= 0 or planned_price is None or current_price is None:
        return ScenarioRow(
            article=result.article,
            name=result.name,
            category=result.category,
            unit_cost=result.total_cost,
            units=result.units,
            current_price=current_price,
            planned_price=planned_price,
            price_change=None,
            profitability=None,
            ozon_costs_without_commission=None,
            planned_revenue=None,
            commission_rate=None,
            planned_commission=None,
            planned_points=None,
            taxable_base=None,
            tax=None,
            profit=None,
            profit_per_unit_before_cost=None,
            net_profit_per_unit=None,
        )

    price_change = planned_price / current_price - 1 if current_price else None
    payout_rate = result.seller_payout / result.retail_price_total if result.retail_price_total else 0.0
    fixed_wb_costs = result.seller_payout - result.financial_result
    planned_revenue = planned_price * result.units
    planned_payout = planned_revenue * payout_rate
    taxable_base = planned_revenue
    tax = taxable_base * tax_rate
    profit = planned_payout - fixed_wb_costs - tax
    profit_per_unit_before_cost = profit / result.units
    net_profit_per_unit = profit_per_unit_before_cost - result.total_cost
    profitability = net_profit_per_unit / result.total_cost if result.total_cost else 0.0
    return ScenarioRow(
        article=result.article,
        name=result.name,
        category=result.category,
        unit_cost=result.total_cost,
        units=result.units,
        current_price=current_price,
        planned_price=planned_price,
        price_change=price_change,
        profitability=profitability,
        ozon_costs_without_commission=fixed_wb_costs,
        planned_revenue=planned_revenue,
        commission_rate=payout_rate,
        planned_commission=planned_payout,
        planned_points=0.0,
        taxable_base=taxable_base,
        tax=tax,
        profit=profit,
        profit_per_unit_before_cost=profit_per_unit_before_cost,
        net_profit_per_unit=net_profit_per_unit,
    )


def _money_ru(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".", ",") + " руб."


def clone_result(result: ProductResult) -> ProductResult:
    return replace(result)
