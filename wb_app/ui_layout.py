from __future__ import annotations
from dataclasses import dataclass
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Callable
from .ui import WBPriceAnalyzerApp

UI_SCALE_LABELS={"Авто (рекомендуется)":"auto","100%":"1.0","90%":"0.9","80%":"0.8"}
UI_SCALE_VALUES={v:k for k,v in UI_SCALE_LABELS.items()}

def resolve_ui_scale(preference:str, screen_height:int)->float:
    n=str(preference or "auto").strip().casefold()
    explicit={"1":1.0,"1.0":1.0,"100%":1.0,"0.9":0.9,"90%":0.9,"0.8":0.8,"80%":0.8}
    if n in explicit:return explicit[n]
    if screen_height<=800:return 0.8
    if screen_height<=950:return 0.9
    return 1.0

def fitted_window_size(w:int,h:int)->tuple[int,int,int,int]:
    return (min(1540,max(1000,w-48)),min(920,max(620,h-80)),min(1180,max(900,w-140)),min(720,max(560,h-160)))

def _find_parent_for_button(root:tk.Misc,text:str)->tk.Misc|None:
    for child in root.winfo_children():
        if isinstance(child,ttk.Button):
            try:
                if str(child.cget("text"))==text:return child.master
            except tk.TclError:pass
        found=_find_parent_for_button(child,text)
        if found is not None:return found
    return None

class HeadingTooltipManager:
    def __init__(self,owner:tk.Tk)->None:
        self.owner=owner;self.tip=None;self.after_id=None;self.target=None
        owner.bind_class("Treeview","<Map>",self._map,add="+")
        owner.bind_class("Treeview","<Motion>",self._motion,add="+")
        owner.bind_class("Treeview","<Leave>",self._cancel,add="+")
        owner.bind_class("Treeview","<ButtonPress>",self._cancel,add="+")
    def ensure(self,tree:ttk.Treeview)->None:
        try:
            name=ttk.Style(tree).lookup("Treeview.Heading","font") or "TkDefaultFont"
            font=tkfont.nametofont(name)
        except (tk.TclError,ValueError):
            font=tkfont.nametofont("TkDefaultFont")
        for col in tuple(str(x) for x in tree.cget("columns")):
            try:
                text=str(tree.heading(col,"text") or "")
                req=max(70,int(font.measure(text))+28);opt=tree.column(col)
                tree.column(col,width=max(int(opt.get("width",70)),req),minwidth=max(int(opt.get("minwidth",70)),req))
            except (tk.TclError,TypeError,ValueError):pass
    def _map(self,e)->None:
        if isinstance(e.widget,ttk.Treeview):e.widget.after_idle(lambda t=e.widget:self.ensure(t))
    def _motion(self,e)->None:
        tree=e.widget
        if not isinstance(tree,ttk.Treeview):return
        try:
            if tree.identify_region(e.x,e.y)!="heading":self._cancel();return
            d=tree.identify_column(e.x)
            if not d:self._cancel();return
            idx=int(d[1:])-1
            raw=tree.cget("displaycolumns")
            cols=tuple(raw) if isinstance(raw,(tuple,list)) else tuple(tree.cget("columns"))
            if cols==("#all",):cols=tuple(str(x) for x in tree.cget("columns"))
            if idx<0 or idx>=len(cols):self._cancel();return
            col=str(cols[idx]);text=str(tree.heading(col if col!="#all" else "#0","text") or "")
            target=(str(tree),col)
            if not text:self._cancel();return
            if target==self.target and self.tip is not None:return
            self._cancel();self.target=target
            x=tree.winfo_rootx()+e.x;y=tree.winfo_rooty()+e.y
            self.after_id=tree.after(250,lambda:self._show(text,x,y))
        except (tk.TclError,ValueError):self._cancel()
    def _show(self,text:str,x:int,y:int)->None:
        self.after_id=None
        if self.target is None:return
        tip=tk.Toplevel(self.owner);tip.wm_overrideredirect(True)
        try:tip.attributes("-topmost",True)
        except tk.TclError:pass
        ttk.Label(tip,text=text,padding=(8,5),relief="solid",borderwidth=1).pack()
        tip.geometry(f"+{x+12}+{y+18}");self.tip=tip
    def _cancel(self,_e=None)->None:
        if self.after_id is not None:
            try:self.owner.after_cancel(self.after_id)
            except tk.TclError:pass
        self.after_id=None
        if self.tip is not None:
            try:self.tip.destroy()
            except tk.TclError:pass
        self.tip=None;self.target=None

@dataclass
class StaticTableLayout:
    tab:ttk.Frame;shell:ttk.Frame;upper:ttk.Frame;toolbar:ttk.Frame;table:ttk.Frame;min_upper:int

class DetachedTableWindow:
    def __init__(self,controller:"TableModeController",action_label:str|None=None,action:Callable[[],None]|None=None)->None:
        self.controller=controller;self.owner=controller.owner;self.source=controller.tree;self.action=action
        self._closed=False;self._signature=None
        self.window=tk.Toplevel(self.owner);self.window.title(f"{controller.title} — отдельная таблица")
        self.window.geometry("1400x800");self.window.minsize(900,500)
        self.window.protocol("WM_DELETE_WINDOW",self.close);self.window.bind("<Escape>",lambda _e:self.close());self.window.bind("<F5>",lambda _e:self.refresh(force=True))
        bar=ttk.Frame(self.window,padding=(10,8));bar.grid(row=0,column=0,sticky="ew");bar.columnconfigure(0,weight=1)
        ttk.Label(bar,text="Таблица синхронизируется с основным окном автоматически.",style="Muted.TLabel").grid(row=0,column=0,sticky="w")
        if action_label and action:ttk.Button(bar,text=action_label,command=self._run_action).grid(row=0,column=1,padx=(8,0))
        ttk.Button(bar,text="Обновить",command=lambda:self.refresh(force=True)).grid(row=0,column=2,padx=(8,0))
        ttk.Button(bar,text="Закрыть",command=self.close).grid(row=0,column=3,padx=(8,0))
        table_row=1
        if controller.category_key is not None:self._category_bar(1);table_row=2
        box=ttk.Frame(self.window);box.grid(row=table_row,column=0,sticky="nsew");box.columnconfigure(0,weight=1);box.rowconfigure(0,weight=1)
        self.window.columnconfigure(0,weight=1);self.window.rowconfigure(table_row,weight=1)
        cols=tuple(str(x) for x in self.source.cget("columns"));self.tree=ttk.Treeview(box,columns=cols,show="headings")
        xs=ttk.Scrollbar(box,orient="horizontal",command=self.tree.xview);ys=ttk.Scrollbar(box,orient="vertical",command=self.tree.yview)
        self.tree.configure(xscrollcommand=xs.set,yscrollcommand=ys.set);self.tree.grid(row=0,column=0,sticky="nsew");ys.grid(row=0,column=1,sticky="ns");xs.grid(row=1,column=0,sticky="ew")
        for col in cols:
            h=self.source.heading(col);c=self.source.column(col);self.tree.heading(col,text=str(h.get("text","")))
            self.tree.column(col,width=max(int(c.get("width",120)),70),minwidth=max(int(c.get("minwidth",70)),70),stretch=bool(c.get("stretch",False)),anchor=c.get("anchor","center"))
        self.tree.bind("<<TreeviewSelect>>",self._sync)
        if action is not None:self.tree.bind("<Double-1>",lambda _e:self._run_action())
        if getattr(self.owner,"_heading_tooltips",None):self.owner._heading_tooltips.ensure(self.tree)
        self.refresh(force=True);self.window.after_idle(self._maximize);self.window.after(700,self._poll)
    def _category_bar(self,row:int)->None:
        key=self.controller.category_key
        bar=ttk.Frame(self.window,padding=(10,0,10,8));bar.grid(row=row,column=0,sticky="ew");bar.columnconfigure(3,weight=1)
        ttk.Label(bar,text="Категория:").grid(row=0,column=0,padx=(0,6))
        ttk.Button(bar,textvariable=self.owner._category_label_vars[key],command=lambda:self.owner._choose_categories(key),width=24).grid(row=0,column=1,padx=(0,10))
        ttk.Checkbutton(bar,text="Исключить выбранные",variable=self.owner._category_exclude_vars[key],command=lambda:self.owner._on_category_mode_changed(key)).grid(row=0,column=2,sticky="w")
        ttk.Label(bar,text="Фильтр синхронизирован с основной таблицей",style="Muted.TLabel").grid(row=0,column=3,sticky="e",padx=(16,0))
    def _rows(self)->tuple[object,...]:
        return tuple((iid,tuple(self.source.item(iid).get("values",())),tuple(self.source.item(iid).get("tags",()))) for iid in self.source.get_children(""))
    def _source_display_columns(self)->tuple[str,...]:
        configured=self.source.cget("displaycolumns")
        if configured in ("#all",("#all",)):
            return tuple(str(column) for column in self.source.cget("columns"))
        if isinstance(configured,(tuple,list)):
            return tuple(str(column) for column in configured)
        return tuple(str(column) for column in self.source.tk.splitlist(configured))
    def refresh(self,force:bool=False)->None:
        if self._closed:return
        try:
            if not self.window.winfo_exists():return
        except tk.TclError:return
        display_columns=self._source_display_columns();sig=(display_columns,self._rows())
        if not force and sig==self._signature:return
        selected=tuple(self.tree.selection());y=self.tree.yview();self.tree.configure(displaycolumns=display_columns);self.tree.delete(*self.tree.get_children(""))
        for iid,values,tags in sig[1]:self.tree.insert("","end",iid=str(iid),values=values,tags=tags)
        self.owner._configure_value_tags(self.tree);valid=[x for x in selected if self.tree.exists(x)]
        if valid:self.tree.selection_set(valid)
        if y:self.tree.yview_moveto(y[0])
        self._signature=sig
    def _poll(self)->None:
        if self._closed:return
        try:
            if not self.window.winfo_exists():return
        except tk.TclError:return
        self.refresh();self.window.after(700,self._poll)
    def _sync(self,_e=None)->None:
        sel=[x for x in self.tree.selection() if self.source.exists(x)]
        if sel:self.source.selection_set(sel);self.source.focus(sel[0]);self.source.see(sel[0])
    def _run_action(self)->None:
        self._sync()
        if self.action:self.action();self.owner.after_idle(lambda:self.refresh(force=True))
    def _maximize(self)->None:
        try:self.window.state("zoomed")
        except tk.TclError:pass
    def focus(self)->None:
        if self._closed:return
        try:self.window.deiconify();self.window.lift();self.window.focus_force()
        except tk.TclError:pass
    def close(self)->None:
        if self._closed:return
        self._closed=True
        try:self.window.grab_release()
        except tk.TclError:pass
        try:self.window.withdraw()
        except tk.TclError:pass
        try:self.window.destroy()
        except tk.TclError:
            try:self.window.tk.call("destroy",self.window._w)
            except tk.TclError:pass
        finally:
            if self.controller._detached is self:self.controller._detached=None

@dataclass
class TableModeController:
    owner:object;key:str;title:str;tab:ttk.Frame;tree:ttk.Treeview;layout:StaticTableLayout;category_key:str|None=None;action_label:str|None=None;action:Callable[[],None]|None=None
    def __post_init__(self)->None:
        self.fullscreen=False;self._detached=None;self.layout.toolbar.columnconfigure(0,weight=1)
        ttk.Button(self.layout.toolbar,text="⛶ На весь экран",style="TableTool.TButton",command=self.toggle_fullscreen).grid(row=0,column=1,padx=3,pady=2)
        ttk.Button(self.layout.toolbar,text="↗ Отдельно",style="TableTool.TButton",command=self.open_detached).grid(row=0,column=2,padx=3,pady=2)
        self.full_toolbar=ttk.Frame(self.tab,style="FloatingTools.TFrame",padding=(6,4))
        ttk.Button(self.full_toolbar,text="Вернуть обычный вид",style="TableTool.TButton",command=self.toggle_fullscreen).grid(row=0,column=0,padx=2)
        ttk.Button(self.full_toolbar,text="Открыть отдельно",style="TableTool.TButton",command=self.open_detached).grid(row=0,column=1,padx=2)
    def toggle_fullscreen(self)->None:self.restore() if self.fullscreen else self.expand()
    def expand(self)->None:
        if self.fullscreen:return
        self.owner._restore_other_table_modes(self.key);self.layout.upper.grid_remove();self.layout.toolbar.grid_remove()
        self.layout.table.grid_configure(row=0,rowspan=3);self.layout.shell.rowconfigure(0,weight=1,minsize=0);self.layout.shell.rowconfigure(1,weight=0,minsize=0);self.layout.shell.rowconfigure(2,weight=0,minsize=0)
        self.full_toolbar.place(relx=1.0,x=-10,y=8,anchor="ne");self.full_toolbar.lift();self.fullscreen=True
        self.owner.status_var.set(f"{self.title}: таблица развернута. F11 или Esc — вернуть обычный вид.")
    def restore(self)->None:
        if not self.fullscreen:return
        self.full_toolbar.place_forget();self.layout.table.grid_configure(row=2,rowspan=1);self.layout.upper.grid();self.layout.toolbar.grid()
        self.layout.shell.rowconfigure(0,weight=0,minsize=self.layout.min_upper);self.layout.shell.rowconfigure(2,weight=1,minsize=110);self.owner._protect_layout(self.layout)
        self.fullscreen=False;self.owner.status_var.set(self.owner._current_run_status())
    def open_detached(self)->None:
        if self._detached is not None and not self._detached._closed:self._detached.focus();return
        self._detached=DetachedTableWindow(self,self.action_label,self.action)
    def close_detached(self)->None:
        if self._detached:self._detached.close();self._detached=None

class DisplayWBPriceAnalyzerApp(WBPriceAnalyzerApp):
    def __init__(self,*args,**kwargs)->None:
        self._table_layouts={};self._heading_tooltips=None;self._base_tk_scaling=1.0
        super().__init__(*args,**kwargs)
        try:self._base_tk_scaling=float(self.tk.call("tk","scaling"))
        except (tk.TclError,TypeError,ValueError):pass
        self._fit_to_screen();self._apply_saved_ui_scale()
    def _build_ui(self)->None:
        super()._build_ui();self._heading_tooltips=HeadingTooltipManager(self);self._install_scale_control();self.after_idle(self._protect_all_layouts)
    def _create_resizable_table_layout(self,tab:ttk.Frame,*,upper_minsize:int,table_minsize:int=150)->tuple[ttk.Frame,ttk.Frame]:
        tab.columnconfigure(0,weight=1);tab.rowconfigure(0,weight=1);shell=ttk.Frame(tab);shell.grid(row=0,column=0,sticky="nsew");shell.columnconfigure(0,weight=1)
        shell.rowconfigure(0,weight=0,minsize=upper_minsize);shell.rowconfigure(1,weight=0);shell.rowconfigure(2,weight=1,minsize=max(110,min(table_minsize,150)))
        upper=ttk.Frame(shell);upper.grid(row=0,column=0,sticky="nsew");upper.columnconfigure(0,weight=1)
        toolbar=ttk.Frame(shell,padding=(0,2));toolbar.grid(row=1,column=0,sticky="ew");ttk.Separator(toolbar,orient="horizontal").grid(row=0,column=0,sticky="ew",padx=(0,8))
        table=ttk.Frame(shell);table.grid(row=2,column=0,sticky="nsew");table.columnconfigure(0,weight=1);table.rowconfigure(0,weight=1)
        layout=StaticTableLayout(tab,shell,upper,toolbar,table,upper_minsize);self._table_layouts[tab]=layout;self.after_idle(lambda:self._protect_layout(layout));return upper,table
    def _create_tree(self,parent,columns:list[str],headings:list[str],row:int,widths:list[int]|None=None,height:int=18)->ttk.Treeview:
        tree=super()._create_tree(parent,columns,headings,row,widths,height);self.after_idle(lambda:self._ensure_tree(tree));return tree
    def _ensure_tree(self,tree:ttk.Treeview)->None:
        if self._heading_tooltips:self._heading_tooltips.ensure(tree)
    def _protect_layout(self,layout:StaticTableLayout)->None:
        try:layout.shell.rowconfigure(0,minsize=max(layout.min_upper,layout.upper.winfo_reqheight()),weight=0);layout.shell.rowconfigure(2,minsize=110,weight=1)
        except tk.TclError:pass
    def _protect_all_layouts(self)->None:
        for layout in self._table_layouts.values():self._protect_layout(layout)
    def _install_scale_control(self)->None:
        saved=self.db.get_setting("ui_scale","auto");self.ui_scale_var=tk.StringVar(value=UI_SCALE_VALUES.get(saved,"Авто (рекомендуется)"));target=_find_parent_for_button(self.settings_tab,"Сохранить настройки")
        if target is None:return
        ttk.Label(target,text="Масштаб интерфейса:").grid(row=3,column=2,sticky="e",padx=(24,8),pady=(10,0))
        combo=ttk.Combobox(target,textvariable=self.ui_scale_var,state="readonly",values=tuple(UI_SCALE_LABELS),width=22);combo.grid(row=3,column=3,sticky="w",pady=(10,0));combo.bind("<<ComboboxSelected>>",self._scale_changed)
    def _scale_changed(self,_e=None)->None:
        value=UI_SCALE_LABELS.get(self.ui_scale_var.get(),"auto");self.db.set_setting("ui_scale",value);self._apply_ui_scale(resolve_ui_scale(value,self.winfo_screenheight()))
    def _apply_saved_ui_scale(self)->None:self._apply_ui_scale(resolve_ui_scale(self.db.get_setting("ui_scale","auto"),self.winfo_screenheight()))
    def _apply_ui_scale(self,factor:float)->None:
        try:self.tk.call("tk","scaling",self._base_tk_scaling*factor)
        except tk.TclError:return
        ttk.Style(self).configure("Treeview",rowheight=max(20,int(24*factor)));self.after_idle(self._protect_all_layouts);self.after_idle(self._refresh_headings)
    def _refresh_headings(self)->None:
        for child in self.winfo_children():self._walk(child)
    def _walk(self,w:tk.Misc)->None:
        if isinstance(w,ttk.Treeview):self._ensure_tree(w)
        for child in w.winfo_children():self._walk(child)
    def _fit_to_screen(self)->None:
        w,h,mw,mh=fitted_window_size(self.winfo_screenwidth(),self.winfo_screenheight());self.geometry(f"{w}x{h}");self.minsize(mw,mh)
