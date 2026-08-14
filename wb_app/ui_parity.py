from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from .ui_catalog import CatalogWBPriceAnalyzerApp
from .ui_layout import TableModeController

class OZParityWBPriceAnalyzerApp(CatalogWBPriceAnalyzerApp):
    def __init__(self,*args,**kwargs)->None:
        self._table_modes={};self._shutting_down=False
        super().__init__(*args,**kwargs)
        self.protocol("WM_DELETE_WINDOW",self.destroy);self.bind("<F11>",self._toggle_current_table_mode);self.bind("<Escape>",self._escape_table_mode)
    def _build_ui(self)->None:
        super()._build_ui();self._install_table_modes()
    def _install_table_modes(self)->None:
        style=ttk.Style(self);style.configure("TableTool.TButton",padding=(8,3));style.configure("FloatingTools.TFrame",relief="solid",borderwidth=1)
        defs=[("overview","Обзор",self.overview_tab,self.overview_tree,"overview",None,None),("scenario","Сценарий цены",self.scenario_tab,self.scenario_tree,"scenario",None,None),("catalog","Справочник себестоимости",self.catalog_tab,self.products_tree,None,"Изменить выбранный",self.edit_product)]
        for key,title,tab,tree,cat,label,action in defs:
            layout=self._table_layouts.get(tab)
            if layout:self._table_modes[key]=TableModeController(self,key,title,tab,tree,layout,cat,label,action)
    def _current_table_mode(self):
        try:selected=self.nametowidget(self.notebook.select())
        except (KeyError,tk.TclError):return None
        for c in self._table_modes.values():
            if c.tab is selected:return c
        return None
    def _toggle_current_table_mode(self,_e=None):
        c=self._current_table_mode()
        if c:c.toggle_fullscreen();return "break"
        return None
    def _escape_table_mode(self,_e=None):
        c=self._current_table_mode()
        if c and c.fullscreen:c.restore();return "break"
        return None
    def _restore_other_table_modes(self,key:str)->None:
        for other,c in self._table_modes.items():
            if other!=key and c.fullscreen:c.restore()
    def destroy(self)->None:
        if self._shutting_down:return
        self._shutting_down=True
        try:
            try:self.withdraw()
            except tk.TclError:pass
            for c in list(self._table_modes.values()):
                try:c.close_detached()
                except (tk.TclError,RuntimeError):pass
            try:raw=self.tk.call("winfo","children",".");names=self.tk.splitlist(raw)
            except (tk.TclError,TypeError):names=()
            for name in names:
                try:self.tk.call("destroy",name)
                except tk.TclError:pass
            try:self.quit()
            except tk.TclError:pass
        finally:
            try:super().destroy()
            except tk.TclError:pass

def run_app()->None:
    app=OZParityWBPriceAnalyzerApp();app.mainloop()
