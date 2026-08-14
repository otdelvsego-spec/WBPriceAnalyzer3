from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .exporter import export_calculation, export_run, suggested_export_name
from .ui_parity import OZParityWBPriceAnalyzerApp


def ordered_selected_iids(visible_iids, selected_iids) -> list[str]:
    """Return selected rows in their current visible table order."""
    selected = {str(iid) for iid in selected_iids}
    return [str(iid) for iid in visible_iids if str(iid) in selected]


def available_export_path(
    directory: str | Path,
    filename: str,
    reserved: set[str] | None = None,
) -> Path:
    """Return a non-overwriting path, adding (2), (3), ... when needed."""
    root = Path(directory).expanduser().resolve()
    requested = Path(filename)
    stem = requested.stem
    suffix = requested.suffix or ".xlsx"
    reserved_paths = reserved if reserved is not None else set()

    candidate = root / f"{stem}{suffix}"
    index = 2
    while candidate.exists() or str(candidate).casefold() in reserved_paths:
        candidate = root / f"{stem} ({index}){suffix}"
        index += 1
    reserved_paths.add(str(candidate).casefold())
    return candidate


def _find_button(root: tk.Misc, text: str) -> ttk.Button | None:
    for child in root.winfo_children():
        if isinstance(child, ttk.Button):
            try:
                if str(child.cget("text")) == text:
                    return child
            except tk.TclError:
                pass
        found = _find_button(child, text)
        if found is not None:
            return found
    return None


class ReportExportsWBPriceAnalyzerApp(OZParityWBPriceAnalyzerApp):
    """v0.2.1: batch history export and explicit combined Overview export."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._install_report_export_buttons()

    def _install_report_export_buttons(self) -> None:
        current_button = _find_button(self.overview_tab, "Только текущий")
        if current_button is not None:
            self.overview_export_button = ttk.Button(
                current_button.master,
                text="Выгрузить итог XLSX",
                command=self.export_overview_calculation,
            )
            self.overview_export_button.grid(row=0, column=4, padx=(8, 0))

        delete_button = _find_button(self.history_tab, "Удалить")
        if delete_button is not None:
            self.history_batch_export_button = ttk.Button(
                delete_button.master,
                text="Выгрузить выбранные XLSX",
                style="Accent.TButton",
                command=self.export_selected_history_runs,
            )
            self.history_batch_export_button.grid(row=0, column=5, padx=(8, 0))

    def export_selected_history_runs(self) -> None:
        selected_iids = ordered_selected_iids(
            self.history_tree.get_children(""),
            self.history_tree.selection(),
        )
        if not selected_iids:
            messagebox.showinfo(
                "Экспорт истории",
                "Выберите один или несколько отчетов в таблице истории.",
                parent=self,
            )
            return

        destination = filedialog.askdirectory(
            title="Выберите папку для выбранных отчетов",
            initialdir=str(self.service.paths["exports"]),
            parent=self,
        )
        if not destination:
            return

        target_dir = Path(destination).expanduser().resolve()
        reserved: set[str] = set()
        exported: list[Path] = []
        failed: list[tuple[int, str]] = []

        self.configure(cursor="watch")
        self.status_var.set(f"Выгрузка выбранных отчетов: {len(selected_iids)}…")
        self.update_idletasks()
        try:
            for iid in selected_iids:
                run_id = int(iid)
                try:
                    calculation = self.db.load_calculation(run_id)
                    output = available_export_path(
                        target_dir,
                        suggested_export_name(calculation),
                        reserved,
                    )
                    exported.append(export_run(self.db, run_id, output))
                except Exception as exc:
                    failed.append((run_id, str(exc)))
        finally:
            self.configure(cursor="")
            self.status_var.set(self._current_run_status())

        if failed:
            details = "\n".join(
                f"• Отчет №{self._run_number(run_id)}: {error}"
                for run_id, error in failed[:10]
            )
            if len(failed) > 10:
                details += f"\n• …и еще ошибок: {len(failed) - 10}"
            messagebox.showwarning(
                "Экспорт истории",
                f"Сохранено файлов: {len(exported)} из {len(selected_iids)}.\n"
                f"Папка:\n{target_dir}\n\n"
                f"Не удалось выгрузить:\n{details}",
                parent=self,
            )
            return

        messagebox.showinfo(
            "Экспорт истории",
            f"Сохранено отдельных XLSX-файлов: {len(exported)}.\n\n"
            f"Папка:\n{target_dir}",
            parent=self,
        )

    def export_overview_calculation(self) -> None:
        calculation = self.overview_calculation
        if calculation is None:
            messagebox.showinfo(
                "Экспорт обзора",
                "Сначала выберите один или несколько отчетов для обзора.",
                parent=self,
            )
            return

        destination = filedialog.asksaveasfilename(
            title="Сохранить итоговый отчет обзора",
            defaultextension=".xlsx",
            initialdir=str(self.service.paths["exports"]),
            initialfile=suggested_export_name(calculation),
            filetypes=[("Книга Excel", "*.xlsx")],
            parent=self,
        )
        if not destination:
            return

        try:
            source_control_total = sum(
                float(row["total_amount"])
                for run_id in self.overview_run_ids
                for row in self.db.list_source_files(run_id)
            )
            path = export_calculation(
                calculation,
                destination,
                source_control_total=source_control_total,
            )
            report_count = len(self.overview_run_ids)
            description = (
                f"Объединенный отчет по {report_count} отчетам"
                if report_count > 1
                else "Итоговый отчет"
            )
            messagebox.showinfo(
                "Экспорт обзора",
                f"{description} сохранен:\n{path}",
                parent=self,
            )
        except Exception as exc:
            messagebox.showerror("Экспорт обзора", str(exc), parent=self)


def run_app() -> None:
    app = ReportExportsWBPriceAnalyzerApp()
    app.mainloop()
