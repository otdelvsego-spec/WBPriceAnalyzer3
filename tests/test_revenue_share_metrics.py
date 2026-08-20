from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

from wb_app.database import Database
from wb_app.exporter import export_calculation
from wb_app.models import ProductResult, RunCalculation
from wb_app.report_totals import report_total_value
from wb_app.ui import _result_values


def calculation() -> RunCalculation:
    product = ProductResult(
        article="A",
        name="Товар",
        material_cost=50,
        labor_cost=50,
        units=2,
        revenue_no_points=1000,
        commission=-200,
        delivery=-80,
        packaging=-20,
        financial_result=600,
    )
    return RunCalculation(
        run_id=None,
        period_start=None,
        period_end=None,
        tax_rate=0.06,
        products=[product],
        unallocated_total=-50,
        unallocated={"Общие расходы": (1, -50)},
        accrual_stats={},
    )


class RevenueShareMetricTests(unittest.TestCase):
    def test_product_and_report_shares_use_retail_revenue(self) -> None:
        report = calculation()
        product = report.products[0]

        self.assertAlmostEqual(product.commission_share(), 0.20)
        self.assertAlmostEqual(product.logistics_share(), 0.08)
        self.assertAlmostEqual(product.points_share(), 0.02)
        self.assertAlmostEqual(product.net_margin(report.tax_rate), 0.34)
        self.assertEqual(
            report.revenue_shares(),
            {
                "commission_share": 0.20,
                "logistics_share": 0.08,
                "points_share": 0.02,
                "net_margin": 0.29,
            },
        )
        self.assertEqual(
            _result_values(product, report.tax_rate)[-4:],
            ("20.00%", "8.00%", "2.00%", "34.00%"),
        )
        self.assertEqual(report_total_value(report), 290)

    def test_history_uses_product_profitability_and_total_net_margin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "app.sqlite3")
            run_id = database.save_run(calculation(), {})

            summary = next(run for run in database.list_runs() if run.id == run_id)

            self.assertEqual(summary.net_profit, 340)
            self.assertAlmostEqual(summary.profitability, 1.7)
            self.assertAlmostEqual(summary.commission_share, 0.20)
            self.assertAlmostEqual(summary.logistics_share, 0.08)
            self.assertAlmostEqual(summary.points_share, 0.02)
            self.assertAlmostEqual(summary.net_margin, 0.29)

    def test_export_contains_the_same_percentage_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "report.xlsx"
            export_calculation(calculation(), destination)
            workbook = load_workbook(destination, data_only=False)
            try:
                sheet = workbook["Итог"]
                self.assertEqual(sheet["AC4"].value, "Средняя комиссия, % от выручки")
                self.assertEqual(sheet["AD4"].value, "Логистика, % от выручки")
                self.assertEqual(sheet["AE4"].value, "Баллы, % от выручки")
                self.assertEqual(sheet["AF4"].value, "Чистая прибыль, % от выручки")
                self.assertAlmostEqual(sheet["AC5"].value, 0.20)
                self.assertAlmostEqual(sheet["AD5"].value, 0.08)
                self.assertAlmostEqual(sheet["AE5"].value, 0.02)
                self.assertAlmostEqual(sheet["AF5"].value, 0.34)
                self.assertAlmostEqual(sheet["AF7"].value, 0.29)
                self.assertEqual(sheet["Y7"].value, sheet["Y6"].value)
                self.assertEqual(sheet["AF7"].number_format, "0.00%")
            finally:
                workbook.close()


if __name__ == "__main__":
    unittest.main()
