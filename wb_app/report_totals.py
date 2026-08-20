from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .column_settings import ColumnSettingsWBPriceAnalyzerApp
from .ui import _money, _percent, _profitability_text


def report_total_value(calculation) -> float:
    """Return the WB result including unallocated income and expenses."""
    return float(calculation.totals()["net_profit"])


def overview_revenue_kpi_values(calculation) -> dict[str, str]:
    """Format paired monetary and relative KPIs for the Overview tab."""
    amounts = calculation.revenue_amounts()
    shares = calculation.revenue_shares()
    return {
        "commission": f"{_money(amounts['commission'])} · {_percent(shares['commission_share'])}",
        "logistics": f"{_money(amounts['logistics'])} · {_percent(shares['logistics_share'])}",
        "points": f"{_money(amounts['points'])} · {_percent(shares['points_share'])}",
        "net_margin": _percent(shares["net_margin"]),
    }


class ReportTotalsWBPriceAnalyzerApp(ColumnSettingsWBPriceAnalyzerApp):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._install_report_total_kpi()
        self._install_revenue_share_kpis()
        self._refresh_report_kpis()

    def _install_report_total_kpi(self) -> None:
        self.kpi_frame.columnconfigure(6, weight=1)
        for child in self.kpi_frame.winfo_children():
            try:
                row = int(child.grid_info().get("row", -1))
            except (TypeError, ValueError, tk.TclError):
                continue
            if row in (0, 2):
                child.grid_configure(columnspan=7)

        self.kpi_vars["report_total"] = tk.StringVar(master=self, value="—")
        card = ttk.Frame(self.kpi_frame, style="Card.TFrame", padding=(16, 14))
        card.grid(row=1, column=6, sticky="nsew", padx=(5, 0))
        ttk.Label(
            card,
            text="Итог отчёта с нераспределёнными",
            style="CardMuted.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            card,
            textvariable=self.kpi_vars["report_total"],
            style="Kpi.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(5, 0))

    def _install_revenue_share_kpis(self) -> None:
        for child in self.kpi_frame.winfo_children():
            try:
                row = int(child.grid_info().get("row", -1))
            except (TypeError, ValueError, tk.TclError):
                continue
            if row == 2:
                child.grid_configure(row=3, columnspan=7)
            elif row == 3:
                child.grid_configure(row=4)

        share_frame = ttk.Frame(self.kpi_frame)
        share_frame.grid(row=2, column=0, columnspan=7, sticky="ew", pady=(10, 4))
        for column in range(4):
            share_frame.columnconfigure(column, weight=1)

        self.revenue_share_kpi_vars: dict[str, tk.StringVar] = {}
        cards = (
            ("commission", "Комиссия WB: сумма · % от выручки"),
            ("logistics", "Логистика: сумма · % от выручки"),
            ("points", "Баллы: сумма · % от выручки"),
            ("net_margin", "Чистая прибыль, % от выручки"),
        )
        for index, (key, title) in enumerate(cards):
            variable = tk.StringVar(master=self, value="—")
            self.revenue_share_kpi_vars[key] = variable
            card = ttk.Frame(share_frame, style="Card.TFrame", padding=(16, 12))
            card.grid(
                row=0,
                column=index,
                sticky="nsew",
                padx=(0 if index == 0 else 5, 0 if index == len(cards) - 1 else 5),
            )
            ttk.Label(card, text=title, style="CardMuted.TLabel").grid(
                row=0, column=0, sticky="w"
            )
            ttk.Label(card, textvariable=variable, style="Kpi.TLabel").grid(
                row=1, column=0, sticky="w", pady=(4, 0)
            )

    def _populate_overview(self) -> None:
        super()._populate_overview()
        self._refresh_report_kpis()

    def _clear_current_view(self) -> None:
        super()._clear_current_view()
        self._refresh_report_kpis()

    def _refresh_report_kpis(self) -> None:
        calculation = self.overview_calculation
        report_total = self.kpi_vars.get("report_total")
        share_variables = getattr(self, "revenue_share_kpi_vars", None)
        if calculation is None:
            if report_total is not None:
                report_total.set("—")
            if share_variables:
                for variable in share_variables.values():
                    variable.set("—")
            return

        product_net = sum(
            item.net_profit(calculation.tax_rate)
            for item in calculation.products
        )
        cost_sold = sum(item.cost_sold for item in calculation.products)
        units = sum(item.units for item in calculation.products)
        self.kpi_vars["net_profit"].set(_money(product_net))
        self.kpi_vars["profitability"].set(
            _profitability_text(
                product_net / cost_sold if cost_sold else None,
                units=units,
                cost_sold=cost_sold,
            )
        )
        if report_total is not None:
            report_total.set(_money(report_total_value(calculation)))
        if share_variables:
            values = overview_revenue_kpi_values(calculation)
            for key, variable in share_variables.items():
                variable.set(values[key])


def run_app() -> None:
    from .single_instance import launch_single_instance

    launch_single_instance(ReportTotalsWBPriceAnalyzerApp)
