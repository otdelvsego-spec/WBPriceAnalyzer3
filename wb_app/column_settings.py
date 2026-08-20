from __future__ import annotations

from dataclasses import dataclass, replace
import json
import tkinter as tk
from tkinter import messagebox, ttk

from .report_exports import ReportExportsWBPriceAnalyzerApp, _find_button
from .ui import OVERVIEW_COLUMN_SPECS, SCENARIO_COLUMN_SPECS


OVERVIEW_COLUMNS_SETTING = "overview_columns_v1"
SCENARIO_COLUMNS_SETTING = "scenario_columns_v1"

ColumnSpecs = tuple[tuple[str, str, int], ...]


@dataclass(frozen=True, slots=True)
class ColumnPreference:
    column_id: str
    visible: bool = True


def default_column_preferences(
    column_specs: ColumnSpecs = OVERVIEW_COLUMN_SPECS,
) -> list[ColumnPreference]:
    return [ColumnPreference(column_id) for column_id, _heading, _width in column_specs]


def normalize_column_preferences(
    value: object,
    column_specs: ColumnSpecs = OVERVIEW_COLUMN_SPECS,
) -> list[ColumnPreference]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            value = None
    if isinstance(value, dict):
        value = value.get("columns")

    available = [column_id for column_id, _heading, _width in column_specs]
    available_set = set(available)
    result: list[ColumnPreference] = []
    seen: set[str] = set()
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                column_id = item
                visible = True
            elif isinstance(item, dict):
                column_id = str(item.get("id", ""))
                visible = bool(item.get("visible", True))
            else:
                continue
            if column_id not in available_set or column_id in seen:
                continue
            result.append(ColumnPreference(column_id, visible))
            seen.add(column_id)

    for column_id in available:
        if column_id not in seen:
            result.append(ColumnPreference(column_id, True))

    if not any(item.visible for item in result):
        return default_column_preferences(column_specs)
    return result


def serialize_column_preferences(
    preferences: list[ColumnPreference],
    column_specs: ColumnSpecs = OVERVIEW_COLUMN_SPECS,
) -> str:
    normalized = normalize_column_preferences(
        [{"id": item.column_id, "visible": item.visible} for item in preferences],
        column_specs,
    )
    return json.dumps(
        {
            "version": 1,
            "columns": [
                {"id": item.column_id, "visible": item.visible}
                for item in normalized
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def visible_column_ids(preferences: list[ColumnPreference]) -> tuple[str, ...]:
    return tuple(item.column_id for item in preferences if item.visible)


class ColumnSettingsDialog(tk.Toplevel):
    def __init__(
        self,
        owner: tk.Misc,
        preferences: list[ColumnPreference],
        headings: dict[str, str],
        *,
        column_specs: ColumnSpecs = OVERVIEW_COLUMN_SPECS,
        section_title: str = "Обзор",
    ) -> None:
        super().__init__(owner)
        self.title(f"Настройка столбцов — {section_title}")
        self.geometry("720x720")
        self.minsize(600, 520)
        self.transient(owner)
        self.confirmed = False
        self.preferences = list(
            normalize_column_preferences(
                [{"id": item.column_id, "visible": item.visible} for item in preferences],
                column_specs,
            )
        )
        self.headings = headings

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        ttk.Label(
            self,
            text=f"Столбцы таблицы «{section_title}»",
            style="Section.TLabel",
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(18, 3))
        ttk.Label(
            self,
            text="Галочка управляет видимостью. Кнопки справа меняют порядок столбцов.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 10))

        content = ttk.Frame(self)
        content.grid(row=2, column=0, sticky="nsew", padx=20)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            content,
            columns=("enabled", "name"),
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("enabled", text="В таблице")
        self.tree.heading("name", text="Название столбца")
        self.tree.column("enabled", width=100, minwidth=90, stretch=False, anchor="center")
        self.tree.column("name", width=470, minwidth=260, stretch=True, anchor="w")
        scrollbar = ttk.Scrollbar(content, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        ordering = ttk.Frame(content, padding=(10, 0, 0, 0))
        ordering.grid(row=0, column=2, sticky="n")
        ttk.Button(ordering, text="↑ Вверх", width=13, command=lambda: self._move(-1)).grid(
            row=0, column=0, sticky="ew", pady=(0, 6)
        )
        ttk.Button(ordering, text="↓ Вниз", width=13, command=lambda: self._move(1)).grid(
            row=1, column=0, sticky="ew", pady=(0, 14)
        )
        ttk.Button(ordering, text="Включить все", width=13, command=self._select_all).grid(
            row=2, column=0, sticky="ew", pady=(0, 6)
        )
        ttk.Button(ordering, text="Снять все", width=13, command=self._clear_all).grid(
            row=3, column=0, sticky="ew"
        )

        footer = ttk.Frame(self, padding=(20, 14, 20, 18))
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self.selection_var = tk.StringVar()
        ttk.Label(footer, textvariable=self.selection_var, style="Muted.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(footer, text="Отмена", command=self.destroy).grid(row=0, column=1, padx=4)
        ttk.Button(
            footer,
            text="Сохранить",
            style="Accent.TButton",
            command=self._save,
        ).grid(row=0, column=2, padx=4)

        self.tree.bind("<Button-1>", self._toggle_from_click, add="+")
        self.tree.bind("<Double-1>", self._toggle_selected)
        self.tree.bind("<space>", self._toggle_selected)
        self.bind("<Control-Up>", lambda _event: self._move(-1))
        self.bind("<Control-Down>", lambda _event: self._move(1))
        self.bind("<Escape>", lambda _event: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._refresh_tree()
        self.grab_set()
        self.tree.focus_set()

    def _refresh_tree(self, selected: str | None = None) -> None:
        previous = selected or next(iter(self.tree.selection()), None)
        self.tree.delete(*self.tree.get_children(""))
        for item in self.preferences:
            self.tree.insert(
                "",
                "end",
                iid=item.column_id,
                values=("☑" if item.visible else "☐", self.headings.get(item.column_id, item.column_id)),
            )
        if previous and self.tree.exists(previous):
            self.tree.selection_set(previous)
            self.tree.focus(previous)
            self.tree.see(previous)
        visible = sum(item.visible for item in self.preferences)
        self.selection_var.set(f"Включено столбцов: {visible} из {len(self.preferences)}")

    def _selected_index(self) -> int | None:
        selection = self.tree.selection()
        if not selection:
            return None
        selected = str(selection[0])
        return next(
            (index for index, item in enumerate(self.preferences) if item.column_id == selected),
            None,
        )

    def _toggle_from_click(self, event) -> None:
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) != "#1":
            return
        row_id = self.tree.identify_row(event.y)
        if row_id:
            self.tree.selection_set(row_id)
            self.tree.focus(row_id)
            self._toggle_selected()

    def _toggle_selected(self, _event=None) -> str:
        index = self._selected_index()
        if index is None:
            return "break"
        current = self.preferences[index]
        self.preferences[index] = replace(current, visible=not current.visible)
        self._refresh_tree(current.column_id)
        return "break"

    def _move(self, direction: int) -> str:
        index = self._selected_index()
        if index is None:
            return "break"
        target = index + direction
        if target < 0 or target >= len(self.preferences):
            return "break"
        item = self.preferences.pop(index)
        self.preferences.insert(target, item)
        self._refresh_tree(item.column_id)
        return "break"

    def _select_all(self) -> None:
        self.preferences = [replace(item, visible=True) for item in self.preferences]
        self._refresh_tree()

    def _clear_all(self) -> None:
        self.preferences = [replace(item, visible=False) for item in self.preferences]
        self._refresh_tree()

    def _save(self) -> None:
        if not any(item.visible for item in self.preferences):
            messagebox.showwarning(
                "Настройка столбцов",
                "Включите хотя бы один столбец.",
                parent=self,
            )
            return
        self.confirmed = True
        self.destroy()


class ColumnSettingsWBPriceAnalyzerApp(ReportExportsWBPriceAnalyzerApp):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.overview_column_preferences = normalize_column_preferences(
            self.db.get_setting(OVERVIEW_COLUMNS_SETTING, "")
        )
        self.scenario_column_preferences = normalize_column_preferences(
            self.db.get_setting(SCENARIO_COLUMNS_SETTING, ""),
            SCENARIO_COLUMN_SPECS,
        )
        self._apply_overview_column_preferences()
        self._apply_scenario_column_preferences()
        self._install_column_settings_buttons()

    def _install_column_settings_buttons(self) -> None:
        overview_anchor = _find_button(self.overview_tab, "Только текущий")
        if overview_anchor is not None:
            self.overview_columns_button = ttk.Button(
                overview_anchor.master,
                text="Настроить столбцы…",
                command=self.open_overview_column_settings,
            )
            self.overview_columns_button.grid(row=0, column=5, padx=(8, 0))

        scenario_anchor = _find_button(self.scenario_tab, "Сбросить")
        if scenario_anchor is not None:
            self.scenario_columns_button = ttk.Button(
                scenario_anchor.master,
                text="Настроить столбцы…",
                command=self.open_scenario_column_settings,
            )
            self.scenario_columns_button.grid(
                row=1,
                column=0,
                columnspan=2,
                sticky="w",
                pady=(8, 0),
            )

    def open_overview_column_settings(self) -> None:
        self._open_column_settings(
            table_key="overview",
            tree=self.overview_tree,
            preferences=self.overview_column_preferences,
            column_specs=OVERVIEW_COLUMN_SPECS,
            setting_key=OVERVIEW_COLUMNS_SETTING,
            section_title="Обзор",
        )

    def open_scenario_column_settings(self) -> None:
        self._open_column_settings(
            table_key="scenario",
            tree=self.scenario_tree,
            preferences=self.scenario_column_preferences,
            column_specs=SCENARIO_COLUMN_SPECS,
            setting_key=SCENARIO_COLUMNS_SETTING,
            section_title="Сценарий цены",
        )

    def _open_column_settings(
        self,
        *,
        table_key: str,
        tree: ttk.Treeview,
        preferences: list[ColumnPreference],
        column_specs: ColumnSpecs,
        setting_key: str,
        section_title: str,
    ) -> None:
        headings = {
            column_id: str(tree.heading(column_id).get("text", "") or column_id)
            for column_id, _heading, _width in column_specs
        }
        dialog = ColumnSettingsDialog(
            self,
            preferences,
            headings,
            column_specs=column_specs,
            section_title=section_title,
        )
        self.wait_window(dialog)
        if not dialog.confirmed:
            return
        try:
            payload = serialize_column_preferences(dialog.preferences, column_specs)
            self.db.set_setting(setting_key, payload)
        except Exception as exc:
            messagebox.showerror("Настройка столбцов", str(exc), parent=self)
            return
        normalized = normalize_column_preferences(payload, column_specs)
        if table_key == "overview":
            self.overview_column_preferences = normalized
        else:
            self.scenario_column_preferences = normalized
        self._apply_column_preferences(tree, normalized, table_key)
        self.status_var.set(f"Настройка столбцов «{section_title}» сохранена")

    def _apply_overview_column_preferences(self) -> None:
        self._apply_column_preferences(
            self.overview_tree,
            self.overview_column_preferences,
            "overview",
        )

    def _apply_scenario_column_preferences(self) -> None:
        self._apply_column_preferences(
            self.scenario_tree,
            self.scenario_column_preferences,
            "scenario",
        )

    def _apply_column_preferences(
        self,
        tree: ttk.Treeview,
        preferences: list[ColumnPreference],
        table_key: str,
    ) -> None:
        tree.configure(displaycolumns=visible_column_ids(preferences))
        tooltips = getattr(self, "_heading_tooltips", None)
        if tooltips is not None:
            self.after_idle(lambda: tooltips.ensure(tree))
        controller = getattr(self, "_table_modes", {}).get(table_key)
        detached = getattr(controller, "_detached", None)
        if detached is not None:
            try:
                detached.refresh(force=True)
            except tk.TclError:
                pass


def run_app() -> None:
    app = ColumnSettingsWBPriceAnalyzerApp()
    app.mainloop()
