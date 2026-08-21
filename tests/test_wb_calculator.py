from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from wb_app.calculator import calculate_run, calculate_scenario
from wb_app.models import AccrualRow, BuyoutNoticeRow, ParsedSource, Product


def operation(
    row: int,
    reason: str,
    article: str = "A",
    *,
    document: str = "",
    quantity: float = 0,
    retail: float = 0,
    realized: float = 0,
    payout: float = 0,
    logistics: float = 0,
    storage: float = 0,
    loyalty_compensation: float = 0,
    commission: float = 0,
    acquiring: float = 0,
    carrier: float = 0,
    source_name: str = "weekly.xlsx",
) -> AccrualRow:
    return AccrualRow(
        source_name=source_name,
        sheet_name="Sheet1",
        row_number=row,
        report_number="1",
        operation_date=date(2026, 8, 3),
        sale_date=date(2026, 8, 3),
        document_type=document,
        payment_reason=reason,
        article=article,
        nm_id="100",
        product_name="Товар A",
        subject="Товар",
        quantity=quantity,
        retail_price=retail,
        realized_price=realized,
        seller_payout=payout,
        logistics=logistics,
        storage=storage,
        loyalty_compensation=loyalty_compensation,
        wb_commission=commission,
        acquiring=acquiring,
        carrier_reimbursement=carrier,
    )


class WBCalculatorTests(unittest.TestCase):
    def test_financial_model_uses_payout_once_and_allocates_storage(self) -> None:
        source = ParsedSource(
            path=Path("weekly.xlsx"),
            file_hash="hash",
            report_type="WEEKLY_WB",
            sheet_name="Sheet1",
            header_row=1,
            period_start=date(2026, 8, 3),
            period_end=date(2026, 8, 9),
            accrual_rows=[
                operation(2, "Продажа", document="Продажа", quantity=2, retail=2000, realized=1600, payout=1400, commission=200, acquiring=20),
                operation(3, "Возврат", document="Возврат", quantity=1, retail=1000, realized=800, payout=700, commission=100, acquiring=10),
                operation(4, "Логистика", logistics=100),
                operation(5, "Хранение", article="", storage=50),
                operation(6, "Компенсация скидки по программе лояльности", document="Продажа", loyalty_compensation=30),
                operation(7, "Возмещение издержек", carrier=100),
            ],
        )
        calculation = calculate_run(
            [source],
            {"A": Product("A", "Товар A", material_cost=100)},
            tax_rate=0.06,
        )
        row = calculation.products[0]

        self.assertEqual(row.units, 1)
        self.assertEqual(row.retail_price_total, 1000)
        self.assertEqual(row.realized_price_total, 800)
        self.assertEqual(row.seller_payout, 700)
        self.assertEqual(row.wb_commission, -100)
        self.assertEqual(row.acquiring, -10)
        self.assertEqual(row.logistics_cost, -100)
        self.assertEqual(row.loyalty_compensation, 30)
        self.assertEqual(row.carrier_reimbursement, 100)
        self.assertEqual(row.financial_result, 630)
        self.assertEqual(row.main_revenue_total, 800)
        self.assertEqual(row.taxable_income, 800)
        self.assertEqual(row.net_profit(0.06), 482)
        self.assertEqual(calculation.unallocated_total, -50)
        self.assertEqual(calculation.unallocated["Хранение"], (1, -50))
        self.assertEqual(calculation.totals()["net_profit"], 432)

    def test_article_expense_is_kept_even_without_sales(self) -> None:
        source = ParsedSource(
            path=Path("weekly.xlsx"), file_hash="h", report_type="WEEKLY_WB",
            sheet_name="Sheet1", header_row=1,
            period_start=date(2026, 8, 3), period_end=date(2026, 8, 9),
            accrual_rows=[operation(2, "Логистика", article="B", logistics=96.72)],
        )
        calculation = calculate_run(
            [source], {"B": Product("B", "Товар B", material_cost=50)}, 0.06
        )
        self.assertEqual(calculation.products[0].units, 0)
        self.assertAlmostEqual(calculation.products[0].financial_result, -96.72)

    def test_scenario_uses_historical_payout_ratio_and_fixed_costs(self) -> None:
        source = ParsedSource(
            path=Path("weekly.xlsx"), file_hash="h", report_type="WEEKLY_WB",
            sheet_name="Sheet1", header_row=1,
            period_start=date(2026, 8, 3), period_end=date(2026, 8, 9),
            accrual_rows=[
                operation(2, "Продажа", document="Продажа", quantity=2, retail=2000, realized=2000, payout=1400),
                operation(3, "Логистика", logistics=200),
            ],
        )
        result = calculate_run([source], {"A": Product("A", "A", material_cost=100)}, 0.06).products[0]
        scenario = calculate_scenario(result, 0.06, planned_price=1200)
        self.assertAlmostEqual(scenario.commission_rate or 0, 0.7)
        self.assertAlmostEqual(scenario.planned_commission or 0, 1680)
        self.assertAlmostEqual(scenario.wb_costs_without_commission or 0, 200)
        self.assertAlmostEqual(scenario.net_profit_total or 0, 1136)

    def test_combines_main_revenue_with_notice_buyout_without_return_reversal(self) -> None:
        main = ParsedSource(
            path=Path("main.xlsx"), file_hash="main", report_type="WEEKLY_WB",
            sheet_name="Sheet1", header_row=1, report_number="1", report_variant="основной",
            period_start=date(2026, 8, 3), period_end=date(2026, 8, 9),
            accrual_rows=[
                operation(2, "Продажа", document="Продажа", quantity=2, retail=2000, realized=1600, payout=1400),
                operation(3, "Возврат", document="Возврат", quantity=1, retail=1000, realized=800, payout=700),
                operation(4, "Логистика", logistics=100),
            ],
        )
        buyout_rows = [
            operation(2, "Продажа", document="Продажа", quantity=3, retail=3000, realized=2400, payout=1800, source_name="buyout.xlsx"),
            operation(3, "Возврат", document="Возврат", quantity=1, retail=1000, realized=800, payout=600, source_name="buyout.xlsx"),
            operation(4, "Логистика", logistics=800, source_name="buyout.xlsx"),
        ]
        buyout = ParsedSource(
            path=Path("buyout.xlsx"), file_hash="buyout", report_type="WEEKLY_WB",
            sheet_name="Sheet1", header_row=1, report_number="2", report_variant="по выкупам",
            period_start=date(2026, 8, 3), period_end=date(2026, 8, 9),
            accrual_rows=buyout_rows,
        )
        notice = ParsedSource(
            path=Path("notice.xlsx"), file_hash="notice", report_type="BUYOUT_NOTICE_WB",
            sheet_name="Sheet1", header_row=10, report_number="2",
            report_variant="уведомление о выкупе",
            period_start=date(2026, 8, 3), period_end=date(2026, 8, 9),
            buyout_notice_rows=[
                BuyoutNoticeRow("notice.xlsx", "Sheet1", 11, "2", date(2026, 8, 3), "A", "Товар A", 3, 1000),
            ],
        )

        calculation = calculate_run(
            [main, buyout, notice],
            {"A": Product("A", "Товар A", material_cost=100)},
            0.06,
        )
        result = calculation.products[0]

        self.assertEqual(result.main_units_total, 1)
        self.assertEqual(result.buyout_units_total, 3)
        self.assertEqual(result.units, 4)
        self.assertEqual(result.main_revenue_total, 800)
        self.assertEqual(result.buyout_revenue_total, 1000)
        self.assertEqual(result.taxable_income, 1800)
        self.assertEqual(result.financial_result, 1600)
        self.assertEqual(result.cost_sold, 400)
        self.assertEqual(result.net_profit(0.06), 1092)
        self.assertEqual(calculation.buyout_control_warnings, [])


if __name__ == "__main__":
    unittest.main()
