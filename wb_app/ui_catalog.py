from __future__ import annotations
import tkinter as tk
from tkinter import messagebox,ttk
from .ui_categories import CategoryWBPriceAnalyzerApp
from .ui_layout import _find_parent_for_button

def delete_catalog_product(database,article:str)->int:
    with database.transaction() as db:
        cur=db.execute("DELETE FROM products WHERE article = ?",(article,));return int(cur.rowcount or 0)

class CatalogWBPriceAnalyzerApp(CategoryWBPriceAnalyzerApp):
    def _build_ui(self)->None:
        super()._build_ui();self._install_catalog_tab()
    def _install_catalog_tab(self)->None:
        old_container=self.products_tree.master
        try:old_container.grid_remove()
        except tk.TclError:pass
        old_header=_find_parent_for_button(self.settings_tab,"Редактировать справочник")
        if old_header is not None:
            try:old_header.grid_remove()
            except tk.TclError:pass
        settings_layout=self._table_layouts.pop(self.settings_tab,None)
        if settings_layout is not None:
            try:settings_layout.table.grid_remove();settings_layout.toolbar.grid_remove();settings_layout.shell.rowconfigure(0,weight=1);settings_layout.shell.rowconfigure(2,weight=0,minsize=0)
            except tk.TclError:pass
        self.catalog_tab=ttk.Frame(self.notebook,padding=4);self.notebook.insert(self.notebook.index(self.settings_tab),self.catalog_tab,text="Справочник себестоимости")
        upper,table=self._create_resizable_table_layout(self.catalog_tab,upper_minsize=175,table_minsize=150)
        title=ttk.Frame(upper);title.grid(row=0,column=0,sticky="ew",pady=(10,6));title.columnconfigure(0,weight=1)
        ttk.Label(title,text="Справочник себестоимости",style="Section.TLabel").grid(row=0,column=0,sticky="w")
        ttk.Label(title,text="Текущие товары, категории и себестоимость для будущих расчетов",style="Muted.TLabel").grid(row=1,column=0,sticky="w",pady=(3,0))
        actions=ttk.Frame(upper);actions.grid(row=1,column=0,sticky="ew",pady=(6,8))
        ttk.Button(actions,text="Редактировать справочник",style="Accent.TButton",command=self.open_cost_catalog_editor).grid(row=0,column=0,padx=(0,6))
        ttk.Button(actions,text="Добавить товар",command=self.add_product).grid(row=0,column=1,padx=4)
        ttk.Button(actions,text="Изменить выбранный",command=self.edit_product).grid(row=0,column=2,padx=4)
        ttk.Button(actions,text="В архив / восстановить",command=self.toggle_product).grid(row=0,column=3,padx=4)
        ttk.Button(actions,text="Журнал изменений",command=self.show_cost_history).grid(row=0,column=4,padx=4)
        ttk.Button(actions,text="Удалить",command=self.delete_selected_product).grid(row=0,column=5,padx=(8,4))
        warning=ttk.Frame(upper);warning.grid(row=2,column=0,sticky="ew",pady=(0,6));warning.columnconfigure(0,weight=1)
        ttk.Label(warning,textvariable=self.cost_catalog_warning_var,style="Warning.TLabel").grid(row=0,column=0,sticky="w")
        ttk.Button(warning,text="Показать пропущенные строки",command=self.show_cost_catalog_warnings).grid(row=0,column=1,padx=(12,0))
        filters=ttk.Frame(upper);filters.grid(row=3,column=0,sticky="ew");filters.columnconfigure(5,weight=1)
        ttk.Label(filters,text="Поиск:").grid(row=0,column=0,padx=(0,6));ttk.Entry(filters,textvariable=self.product_search_var,width=28).grid(row=0,column=1,padx=(0,12))
        ttk.Label(filters,text="Показывать:").grid(row=0,column=2,padx=(0,6));status=ttk.Combobox(filters,textvariable=self.product_status_var,state="readonly",values=("Все","Активные","Архив"),width=12);status.grid(row=0,column=3,padx=(0,12));status.bind("<<ComboboxSelected>>",lambda _e:self.refresh_products())
        ttk.Label(filters,textvariable=self.product_count_var,style="Muted.TLabel").grid(row=0,column=4,sticky="w")
        ttk.Button(filters,text="Выгрузить XLSX",command=self.export_product_catalog).grid(row=0,column=6,padx=4);ttk.Button(filters,text="Загрузить XLSX",command=self.import_product_catalog).grid(row=0,column=7,padx=4);ttk.Button(filters,text="Очистить справочник",command=self.clear_product_catalog).grid(row=0,column=8,padx=(12,4))
        self.products_tree=self._create_tree(table,["article","name","category","total","material","labor","status"],["Артикул","Наименование","Категория","Полная себестоимость","Материал","Трудозатраты","Статус"],row=0,widths=[150,320,220,180,150,150,110])
        self.products_tree.bind("<Double-1>",lambda _e:self.edit_product());self.products_tree.bind("<Delete>",lambda _e:self.delete_selected_product());self.refresh_products();self._refresh_cost_catalog_warning()
    def delete_selected_product(self)->None:
        sel=self.products_tree.selection()
        if not sel:messagebox.showinfo("Справочник себестоимости","Выберите товар для удаления.",parent=self);return
        article=str(sel[0]);values=self.products_tree.item(article,"values");name=str(values[1]) if len(values)>1 else article
        if not messagebox.askyesno("Удалить товар",f"Удалить «{name}» ({article}) из текущего справочника?\n\nСохраненные расчеты и исторические снимки себестоимости не изменятся.",icon="warning",parent=self):return
        if delete_catalog_product(self.db,article):self._refresh_after_catalog_change();self.status_var.set(f"Товар {article} удален из текущего справочника")
        else:messagebox.showinfo("Справочник себестоимости","Товар уже отсутствует в справочнике.",parent=self)
