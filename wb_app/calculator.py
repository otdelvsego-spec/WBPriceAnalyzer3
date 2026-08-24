from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import date

from .excel_reader import REPORT_BUYOUT_NOTICE, REPORT_WEEKLY, all_rows, normalize_text
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
    for source in sources:
        for row in source.buyout_notice_rows:
            if not row.article or row.article in products:
                continue
            item = unknown.setdefault(
                row.article,
                UnknownProduct(
                    article=row.article,
                    name=row.product_name or row.article,
                    sku="",
                ),
            )
            if item.name == item.article and row.product_name:
                item.name = row.product_name
            item.source_names.add(row.source_name)
    return sorted(unknown.values(), key=lambda item: item.article.casefold())


def _document_sign(row: AccrualRow) -> float:
    return -1.0 if _type_key(row.document_type) == _type_key("Возврат") else 1.0


def _is_sale_document(row: AccrualRow) -> bool:
    return _type_key(row.document_type) in {
        _type_key("Продажа"),
        _type_key("Возврат"),
    }


def _apply_row(result: ProductResult, row: AccrualRow, *, channel: str) -> None:
    sign = _document_sign(row)
    if _is_sale_document(row):
        # Quantity=2 on carrier reimbursement rows is explicitly not a sale.
        if (
            channel == "main"
            and _type_key(row.payment_reason) in {_type_key("Продажа"), _type_key("Возврат")}
        ):
            result.main_units = float(result.main_units or 0.0) + sign * row.quantity
        if channel == "main":
            result.main_revenue = float(result.main_revenue or 0.0) + sign * row.realized_price
            result.scenario_market_revenue = (
                float(result.scenario_market_revenue or 0.0) + sign * row.realized_price
            )
            result.main_seller_payout = (
                float(result.main_seller_payout or 0.0) + sign * row.seller_payout
            )
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
    if channel == "main":
        result.financial_result += row.amount


def _buyout_extra_amount(row: AccrualRow) -> float:
    """Cash impact not already embedded in a notice's contractual price."""
    sign = _document_sign(row)
    other_payout = row.seller_payout if not _is_sale_document(row) else 0.0
    return (
        other_payout
        - row.penalty
        - row.storage
        - row.acceptance
        - row.commission_adjustment
        - row.deductions
        - sign * row.loyalty_fee
        - sign * row.loyalty_points
        - row.payout_fee
    )


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
    referenced_articles.update(
        row.article
        for source in sources
        for row in source.buyout_notice_rows
        if row.article
    )
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
            main_units=0.0,
            buyout_units=0.0,
            main_revenue=0.0,
            buyout_revenue=0.0,
            main_seller_payout=0.0,
            scenario_market_revenue=0.0,
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

    source_variants = {
        source.path.name: source.report_variant
        for source in sources
        if source.report_type == REPORT_WEEKLY
    }
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

        channel = "buyout" if source_variants.get(row.source_name) == "по выкупам" else "main"
        _apply_row(result, row, channel=channel)
        allocated_total += row.amount

    buyout_sources = {
        source.report_number: source
        for source in sources
        if source.report_type == REPORT_WEEKLY and source.report_variant == "по выкупам"
    }
    notice_sources = {
        source.report_number: source
        for source in sources
        if source.report_type == REPORT_BUYOUT_NOTICE
    }
    missing_notices = sorted(set(buyout_sources) - set(notice_sources))
    orphan_notices = sorted(set(notice_sources) - set(buyout_sources))
    if missing_notices:
        raise CalculationError(
            "Не загружены уведомления о выкупе XLSX для отчетов №"
            + ", №".join(missing_notices)
        )
    if orphan_notices:
        raise CalculationError(
            "Не загружены соответствующие детализированные отчеты по выкупам №"
            + ", №".join(orphan_notices)
        )

    buyout_control_warnings: list[str] = []
    for report_number, notice in notice_sources.items():
        detail = buyout_sources[report_number]
        rows_by_article: dict[str, list[AccrualRow]] = defaultdict(list)
        for row in detail.accrual_rows:
            if row.article:
                rows_by_article[row.article].append(row)
        notice_articles = {row.article for row in notice.buyout_notice_rows}
        for article, linked_rows in rows_by_article.items():
            result = results.get(article)
            if result is None or article in skipped_articles:
                continue
            if article in notice_articles:
                result.financial_result += sum(_buyout_extra_amount(row) for row in linked_rows)
            else:
                result.financial_result += sum(row.amount for row in linked_rows)
                if any(_is_sale_document(row) and row.seller_payout for row in linked_rows):
                    buyout_control_warnings.append(
                        f"Выкуп №{report_number}, артикул {article}: в детализации есть "
                        "продажа, но товар отсутствует в уведомлении."
                    )
        for notice_row in notice.buyout_notice_rows:
            result = results.get(notice_row.article)
            if result is None or notice_row.article in skipped_articles:
                skipped_detail.setdefault(
                    notice_row.article,
                    f"{notice_row.article} — {notice_row.product_name or notice_row.article} "
                    f"({notice_row.source_name}, строка {notice_row.row_number})",
                )
                skipped_amounts[notice_row.article] += notice_row.amount
                continue
            result.buyout_units = float(result.buyout_units or 0.0) + notice_row.quantity
            result.buyout_revenue = float(result.buyout_revenue or 0.0) + notice_row.amount
            result.financial_result += notice_row.amount

            linked_rows = rows_by_article.get(notice_row.article, [])
            gross_sales = sum(
                row.quantity
                for row in linked_rows
                if _type_key(row.document_type) == _type_key("Продажа")
                and _type_key(row.payment_reason) == _type_key("Продажа")
            )
            gross_market_revenue = sum(
                row.realized_price
                for row in linked_rows
                if _type_key(row.document_type) == _type_key("Продажа")
            )
            result.scenario_market_revenue = (
                float(result.scenario_market_revenue or 0.0)
                + (gross_market_revenue or notice_row.amount)
            )
            # WB's contractual buyout price is bridged from gross sale payout
            # less all linked logistics. A later customer return does not undo
            # the already completed seller -> RWB buyout.
            bridge = sum(
                row.seller_payout
                for row in linked_rows
                if _type_key(row.document_type) == _type_key("Продажа")
            ) - sum(row.logistics for row in linked_rows)
            if abs(gross_sales - notice_row.quantity) > 0.001:
                buyout_control_warnings.append(
                    f"Выкуп №{report_number}, артикул {notice_row.article}: "
                    f"количество в уведомлении {notice_row.quantity:g}, "
                    f"продаж в детализации {gross_sales:g}."
                )
            if abs(bridge - notice_row.amount) > 0.01:
                buyout_control_warnings.append(
                    f"Выкуп №{report_number}, артикул {notice_row.article}: "
                    f"цена уведомления {notice_row.amount:.2f} руб., "
                    f"контроль по детализации {bridge:.2f} руб."
                )

    for result in results.values():
        result.units = result.main_units_total + result.buyout_units_total

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
        realization_revenue=sum(result.revenue_including_points for result in results.values()),
        realization_units=sum(result.units for result in results.values()),
        source_period_warnings=warnings,
        buyout_control_warnings=buyout_control_warnings,
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
    seller_revenue_rate = (
        result.revenue_including_points / result.pricing_revenue
        if result.pricing_revenue
        else 0.0
    )
    payout_rate = (
        result.scenario_receipt / result.revenue_including_points
        if result.revenue_including_points
        else 0.0
    )
    fixed_wb_costs = result.scenario_receipt - result.financial_result
    planned_market_revenue = planned_price * result.units
    planned_revenue = planned_market_revenue * seller_revenue_rate
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
