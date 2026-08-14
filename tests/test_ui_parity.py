from __future__ import annotations
from contextlib import contextmanager
import unittest
from wb_app.ui_categories import category_allowed, category_filter_label
from wb_app.ui_catalog import delete_catalog_product
from wb_app.ui_layout import fitted_window_size, resolve_ui_scale

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

if __name__=="__main__":
    unittest.main()
