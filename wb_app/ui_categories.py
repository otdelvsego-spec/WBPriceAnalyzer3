from __future__ import annotations
import tkinter as tk
from tkinter import messagebox,ttk
from .ui import CATEGORY_ALL,CATEGORY_EMPTY,SORT_ASCENDING,SORT_NONE,_category_label,_money,_number,_profitability_text
from .ui_layout import DisplayWBPriceAnalyzerApp

def category_filter_label(selected:set[str]|None)->str:
    if selected is None:return CATEGORY_ALL
    if not selected:return "Ничего не выбрано"
    vals=sorted(selected,key=str.casefold)
    return vals[0] if len(vals)==1 else f"Выбрано: {len(vals)}"

def category_allowed(category:str,selected:set[str]|None,exclude:bool)->bool:
    if selected is None:return not exclude
    contains=category in selected
    return not contains if exclude else contains

class CategorySelectionDialog(tk.Toplevel):
    def __init__(self,owner:tk.Misc,categories:list[str],selected:set[str]|None)->None:
        super().__init__(owner);self.title("Выбор категорий");self.geometry("460x520");self.minsize(380,360);self.transient(owner.winfo_toplevel())
        self.categories=categories;self.result=None;self.cancelled=True;self.protocol("WM_DELETE_WINDOW",self._cancel);self.columnconfigure(0,weight=1);self.rowconfigure(1,weight=1)
        ttk.Label(self,text="Выберите одну или несколько категорий.",style="Muted.TLabel").grid(row=0,column=0,sticky="w",padx=16,pady=(14,8))
        box=ttk.Frame(self);box.grid(row=1,column=0,sticky="nsew",padx=16);box.columnconfigure(0,weight=1);box.rowconfigure(0,weight=1)
        self.listbox=tk.Listbox(box,selectmode=tk.MULTIPLE,exportselection=False,activestyle="none");scroll=ttk.Scrollbar(box,orient="vertical",command=self.listbox.yview);self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.grid(row=0,column=0,sticky="nsew");scroll.grid(row=0,column=1,sticky="ns")
        for item in categories:self.listbox.insert("end",item)
        if selected is None and categories:self.listbox.selection_set(0,"end")
        elif selected is not None:
            for i,item in enumerate(categories):
                if item in selected:self.listbox.selection_set(i)
        bar=ttk.Frame(self,padding=(16,12));bar.grid(row=2,column=0,sticky="ew");bar.columnconfigure(2,weight=1)
        ttk.Button(bar,text="Выбрать все",command=lambda:self.listbox.selection_set(0,"end")).grid(row=0,column=0,padx=(0,6))
        ttk.Button(bar,text="Снять выбор",command=lambda:self.listbox.selection_clear(0,"end")).grid(row=0,column=1,padx=6)
        ttk.Button(bar,text="Отмена",command=self._cancel).grid(row=0,column=3,padx=6);ttk.Button(bar,text="Применить",style="Accent.TButton",command=self._apply).grid(row=0,column=4,padx=(6,0))
        self.bind("<Escape>",lambda _e:self._cancel());self.bind("<Return>",lambda _e:self._apply());self.after_idle(self._open)
    def _open(self)->None:
        try:self.grab_set();self.lift();self.focus_force()
        except tk.TclError:pass
    def _apply(self)->None:
        selected={self.categories[int(i)] for i in self.listbox.curselection()};self.result=None if len(selected)==len(self.categories) else selected;self.cancelled=False;self.destroy()
    def _cancel(self)->None:self.cancelled=True;self.destroy()

class CategoryWBPriceAnalyzerApp(DisplayWBPriceAnalyzerApp):
    def __init__(self,*args,**kwargs)->None:
        self._category_selected={"overview":None,"scenario":None};self._category_label_vars={};self._category_exclude_vars={}
        super().__init__(*args,**kwargs)
    def _build_ui(self)->None:
        super()._build_ui();self._install_category_filters()
    def _install_category_filters(self)->None:
        self._category_label_vars={"overview":tk.StringVar(value=CATEGORY_ALL),"scenario":tk.StringVar(value=CATEGORY_ALL)}
        self._category_exclude_vars={"overview":tk.BooleanVar(value=False),"scenario":tk.BooleanVar(value=False)}
        self._replace("overview",self.overview_category_combo,self.overview_category_var);self._replace("scenario",self.scenario_category_combo,self.scenario_category_var)
    def _replace(self,key:str,combo:ttk.Combobox,legacy_var:tk.StringVar)->None:
        parent=combo.master
        try:info=combo.grid_info();row=int(info.get("row",0));col=int(info.get("column",1))
        except (tk.TclError,TypeError,ValueError):return
        for child in parent.winfo_children():
            if child is combo or child.winfo_manager()!="grid":continue
            try:
                ci=child.grid_info();cc=int(ci.get("column",0))
                if cc>=col+1:child.grid_configure(column=cc+1)
            except (tk.TclError,TypeError,ValueError):pass
        combo.grid_remove();legacy_var.set(CATEGORY_ALL)
        ttk.Button(parent,textvariable=self._category_label_vars[key],command=lambda:self._choose_categories(key),width=24).grid(row=row,column=col,padx=(0,8))
        ttk.Checkbutton(parent,text="Исключить выбранные",variable=self._category_exclude_vars[key],command=lambda:self._on_category_mode_changed(key)).grid(row=row,column=col+1,sticky="w",padx=(0,12))
    def _available_categories(self,key:str)->list[str]:
        calc=self.overview_calculation if key=="overview" else self.current_calculation
        return sorted({_category_label(r.category) for r in (calc.products if calc else [])},key=str.casefold)
    def _normalize_category_selection(self,key:str)->None:
        cats=set(self._available_categories(key));selected=self._category_selected[key]
        if selected is not None:
            selected.intersection_update(cats)
            if selected==cats and cats:self._category_selected[key]=None
        self._category_label_vars[key].set(category_filter_label(self._category_selected[key]))
    def _choose_categories(self,key:str)->None:
        cats=self._available_categories(key)
        if not cats:messagebox.showinfo("Категории","В текущем расчете нет товаров для выбора.",parent=self);return
        d=CategorySelectionDialog(self,cats,self._category_selected[key]);self.wait_window(d)
        if d.cancelled:return
        self._category_selected[key]=d.result;self._category_label_vars[key].set(category_filter_label(d.result));self._refresh_category_view(key)
    def _on_category_mode_changed(self,key:str)->None:self._refresh_category_view(key)
    def _refresh_category_view(self,key:str)->None:self._populate_overview() if key=="overview" else self._populate_scenario()
    def _category_matches(self,key:str,category:str)->bool:return category_allowed(category,self._category_selected[key],bool(self._category_exclude_vars[key].get()))
    def _populate_overview(self)->None:
        if not hasattr(self,"_category_label_vars"):super()._populate_overview();return
        self.overview_category_var.set(CATEGORY_ALL);super()._populate_overview()
        if not self._category_label_vars:return
        self._normalize_category_selection("overview");calc=self.overview_calculation
        if calc is None:return
        for iid in tuple(self.overview_tree.get_children("")):
            v=self.overview_tree.item(iid,"values");cat=str(v[2]) if len(v)>2 else CATEGORY_EMPTY
            if not self._category_matches("overview",cat):self.overview_tree.delete(iid)
        rows=[r for r in calc.products if self._category_matches("overview",_category_label(r.category))]
        revenue=sum(r.revenue_including_points for r in rows);net=sum(r.net_profit(calc.tax_rate) for r in rows);cost=sum(r.cost_sold for r in rows);fin=sum(r.financial_result for r in rows);units=sum(r.units for r in rows)
        selected=self._category_selected["overview"];exclude=bool(self._category_exclude_vars["overview"].get())
        self.category_summary_title_var.set("Итоги по товарам всех категорий" if selected is None and not exclude else ("Итоги без выбранных категорий" if exclude else "Итоги по товарам выбранных категорий"))
        self.category_kpi_vars["revenue"].set(_money(revenue));self.category_kpi_vars["net_profit"].set(_money(net))
        self.category_kpi_vars["profitability"].set(_profitability_text(net/cost if cost else None,units=units,cost_sold=cost));self.category_kpi_vars["units"].set(_number(units));self.category_kpi_vars["cost_sold"].set(_money(cost));self.category_kpi_vars["financial_result"].set(_money(fin))
        self.overview_count_var.set(f"Показано: {len(self.overview_tree.get_children(''))} из {len(calc.products)}")
    def _populate_scenario(self)->None:
        if not hasattr(self,"_category_label_vars"):super()._populate_scenario();return
        self.scenario_category_var.set(CATEGORY_ALL);super()._populate_scenario()
        if not self._category_label_vars:return
        self._normalize_category_selection("scenario");calc=self.current_calculation
        if calc is None:return
        for iid in tuple(self.scenario_tree.get_children("")):
            v=self.scenario_tree.item(iid,"values");cat=str(v[2]) if len(v)>2 else CATEGORY_EMPTY
            if not self._category_matches("scenario",cat):self.scenario_tree.delete(iid)
        results=[r for r in calc.products if self._category_matches("scenario",_category_label(r.category))];arts={r.article for r in results};scenarios=[r for a,r in self.scenario_rows.items() if a in arts]
        current=sum(r.revenue_including_points for r in results);planned=sum(float(r.planned_revenue or 0) for r in scenarios);net=sum(float(r.net_profit_per_unit or 0)*r.units for r in scenarios);cost=sum(r.unit_cost*r.units for r in scenarios if r.net_profit_per_unit is not None);units=sum(r.units for r in scenarios)
        self.scenario_kpi_vars["current_revenue"].set(_money(current));self.scenario_kpi_vars["planned_revenue"].set(_money(planned));self.scenario_kpi_vars["planned_net"].set(_money(net));self.scenario_kpi_vars["planned_margin"].set(_profitability_text(net/cost if cost else None,units=units,cost_sold=cost))
        self.scenario_count_var.set(f"Показано: {len(self.scenario_tree.get_children(''))} из {len(self.scenario_rows)}")
    def _reset_overview_filters(self)->None:
        self._category_selected["overview"]=None
        if self._category_label_vars:self._category_label_vars["overview"].set(CATEGORY_ALL);self._category_exclude_vars["overview"].set(False)
        self.overview_category_var.set(CATEGORY_ALL);self.overview_article_var.set("");self.overview_sort_var.set(SORT_NONE);self.overview_sort_direction_var.set(SORT_ASCENDING);self._populate_overview()
    def _reset_scenario_filters(self)->None:
        self._category_selected["scenario"]=None
        if self._category_label_vars:self._category_label_vars["scenario"].set(CATEGORY_ALL);self._category_exclude_vars["scenario"].set(False)
        self.scenario_category_var.set(CATEGORY_ALL);self.scenario_article_var.set("");self.scenario_sort_var.set(SORT_NONE);self.scenario_sort_direction_var.set(SORT_ASCENDING);self._populate_scenario()
