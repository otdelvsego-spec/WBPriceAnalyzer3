from __future__ import annotations

import inspect
import unittest
from unittest.mock import patch

from wb_app.ui import WBPriceAnalyzerApp


class _FakeTab:
    def columnconfigure(self, *_args, **_kwargs):
        return None

    def rowconfigure(self, *_args, **_kwargs):
        return None


class _FakeFrame:
    def __init__(self, _parent):
        self.requested_height = 280

    def columnconfigure(self, *_args, **_kwargs):
        return None

    def rowconfigure(self, *_args, **_kwargs):
        return None

    def winfo_reqheight(self):
        return self.requested_height


class _FakePane:
    def __init__(self, _parent, **options):
        self.options = options
        self.added = []
        self.sash = None

    def grid(self, **_kwargs):
        return None

    def add(self, child, **options):
        self.added.append((child, options))

    def winfo_exists(self):
        return True

    def winfo_height(self):
        return 700

    def sash_place(self, index, x, y):
        self.sash = (index, x, y)


class ResizableLayoutTests(unittest.TestCase):
    def test_layout_creates_vertical_pane_with_protected_table_height(self) -> None:
        app = WBPriceAnalyzerApp.__new__(WBPriceAnalyzerApp)
        app.colors = {"window": "#202020"}
        app.resizable_panes = []
        app.after_idle = lambda callback: callback()

        with patch("wb_app.ui.tk.PanedWindow", _FakePane), patch("wb_app.ui.ttk.Frame", _FakeFrame):
            upper, table = app._create_resizable_table_layout(
                _FakeTab(),
                upper_minsize=250,
                table_minsize=150,
            )

        pane = app.resizable_panes[0]
        self.assertEqual(pane.options["orient"], "vertical")
        self.assertEqual(pane.added[0], (upper, {"minsize": 250, "stretch": "never"}))
        self.assertEqual(pane.added[1], (table, {"minsize": 150, "stretch": "always"}))
        self.assertEqual(pane.sash, (0, 0, 280))

    def test_requested_tabs_use_resizable_table_layout(self) -> None:
        for method in (
            WBPriceAnalyzerApp._build_overview_tab,
            WBPriceAnalyzerApp._build_scenario_tab,
            WBPriceAnalyzerApp._build_settings_tab,
        ):
            self.assertIn("_create_resizable_table_layout", inspect.getsource(method))


if __name__ == "__main__":
    unittest.main()
