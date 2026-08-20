from __future__ import annotations
from contextlib import contextmanager
import unittest
from wb_app.ui_categories import category_allowed, category_filter_label
from wb_app.ui_catalog import delete_catalog_product
from wb_app.ui_layout import fitted_window_size, resolve_ui_scale
from wb_app.ui import (
    OVERVIEW_COLUMN_SPECS,
    SCENARIO_COLUMN_SPECS,
    TREND_METRICS,
)

class _FakeCursor:
    rowcount=1
class _FakeConnection:
    def __init__(self):self.calls=[]
    def execute(self,sql,params):self.calls.append((sql,params));return _FakeCursor()
class _FakeDatabase:
    def __init__(self):self.connection=_FakeConnection()
    @contextmanager
    def transaction(self):yield self.connection

class UIParityTests(unittest.TestCase):
    def test_scale_and_window_fit(self):
        self.assertEqual(resolve_ui_scale("auto",768),0.8)
        self.assertEqual(resolve_ui_scale("auto",900),0.9)
        self.assertEqual(resolve_ui_scale("auto",1080),1.0)
        self.assertEqual(resolve_ui_scale("100%",768),1.0)
        self.assertEqual(fitted_window_size(1366,768),(1318,688,1180,608))
        self.assertEqual(fitted_window_size(1920,1080),(1540,920,1180,720))
    def test_category_include_exclude(self):
        selected={"Столы","Кровати"}
        self.assertTrue(category_allowed("Столы",selected,False))
        self.assertFalse(category_allowed("Шкафы",selected,False))
        self.assertFalse(category_allowed("Столы",selected,True))
        self.assertTrue(category_allowed("Шкафы",selected,True))
        self.assertTrue(category_allowed("Столы",None,False))
        self.assertFalse(category_allowed("Столы",None,True))
        self.assertEqual(category_filter_label(None),"Все категории")
        self.assertEqual(category_filter_label(set()),"Ничего не выбрано")
        self.assertEqual(category_filter_label({"Столы"}),"Столы")
    def test_delete_catalog_only_products(self):
        db=_FakeDatabase()
        self.assertEqual(delete_catalog_product(db,"ABC-1"),1)
        self.assertEqual(db.connection.calls,[("DELETE FROM products WHERE article = ?",("ABC-1",))])

    def test_recent_oz_controls_have_matching_wb_labels(self):
        self.assertEqual(
            tuple(TREND_METRICS),
            (
                "Выручка",
                "Чистая прибыль",
                "Доходность",
                "Продажи, шт.",
                "Нераспределенные доходы / расходы",
                "Средняя комиссия, % от выручки",
                "Логистика, % от выручки",
                "Баллы, % от выручки",
                "Чистая прибыль, % от выручки",
            ),
        )
        self.assertEqual(
            tuple(heading for _column, heading, _width in OVERVIEW_COLUMN_SPECS[-4:]),
            (
                "Средняя комиссия, % от выручки",
                "Логистика, % от выручки",
                "Баллы, % от выручки",
                "Чистая прибыль, % от выручки",
            ),
        )
        self.assertEqual(
            tuple(column for column, _heading, _width in SCENARIO_COLUMN_SPECS),
            (
                "article", "name", "category", "cost", "units", "current_price",
                "planned_price", "change", "profitability", "other_costs",
                "planned_revenue", "commission_rate", "commission", "points",
                "taxable", "tax", "profit", "profit_unit", "net_unit", "net_total",
            ),
        )

if __name__=="__main__":
    unittest.main()
