# Sheets Home for LibreOffice Calc
#
# Port of CellLite's "Sheets Home": a page that lists every sheet in the workbook with search,
# sorting, recent sheets, hidden sheets, a contents preview, and a "Contents" index sheet
# with a link to every sheet.
#
# Commands (menu Sheet ▸ Sheets Home…, toolbar button, Ctrl+Shift+H):
#   org.celllite.sheetshome:Home   open Sheets Home
#   org.celllite.sheetshome:Index  create / refresh the Contents index sheet
#
# Two UNO components live in this file:
#   ProtocolHandler  handles the commands above
#   Job              runs whenever a document view opens, to remember recently used sheets

import json
import os
import re

import uno
import unohelper
from com.sun.star.awt import XActionListener, XItemListener, XKeyListener, XMouseListener, XTextListener
from com.sun.star.awt.grid import XGridSelectionListener
from com.sun.star.frame import XDispatch, XDispatchProvider, XTerminateListener
from com.sun.star.lang import XInitialization, XServiceInfo
from com.sun.star.sheet import XActivationEventListener
from com.sun.star.task import XJob

PROTOCOL = "org.celllite.sheetshome:"
HANDLER_IMPL = "org.celllite.SheetsHome.ProtocolHandler"
JOB_IMPL = "org.celllite.SheetsHome.Job"
INDEX_NAME = "Contents"
INDEX_PROP = "SheetsHomeIndex"  # document property remembering which sheet is the index
GREEN = 0x1E8E3E


def const(name):
    return uno.getConstantByName(name)


# ------------------------------------------------------------------ recent sheets (per document)
_recent = []  # [{"model": XModel, "names": [sheet names, most recent first]}]


def _recent_entry(model, create=True):
    for e in _recent:
        try:
            if e["model"] == model:
                return e
        except Exception:
            pass
    if not create:
        return None
    e = {"model": model, "names": []}
    _recent.append(e)
    return e


def touch_recent(model, name):
    e = _recent_entry(model)
    e["names"] = [name] + [n for n in e["names"] if n != name][:11]


def rename_recent(model, old, new):
    e = _recent_entry(model, False)
    if e:
        e["names"] = [new if n == old else n for n in e["names"]]


def recent_names(model):
    e = _recent_entry(model, False)
    return list(e["names"]) if e else []


class ActivationListener(unohelper.Base, XActivationEventListener):
    def __init__(self, model):
        self.model = model

    def activeSpreadsheetChanged(self, ev):
        try:
            touch_recent(self.model, ev.ActiveSheet.Name)
        except Exception:
            pass

    def disposing(self, ev):
        for e in list(_recent):
            try:
                if e["model"] == self.model:
                    _recent.remove(e)
            except Exception:
                pass


_exit = {"terminating": False, "hooked": False}


class StopOnExit(unohelper.Base, XTerminateListener):
    """When Vino's Office closes or restarts (e.g. after changing the menu language), detach every
    listener, so none of our Python code is running while LibreOffice shuts down."""

    def queryTermination(self, event):
        pass

    def notifyTermination(self, event):
        untrack_all()

    def disposing(self, event):
        untrack_all()


def untrack_all():
    _exit["terminating"] = True
    for e in list(_recent):
        ctrl, listener = e.pop("ctrl", None), e.pop("listener", None)
        if ctrl is not None and listener is not None:
            try:
                ctrl.removeActivationEventListener(listener)
            except Exception:
                pass
    del _recent[:]


def track(model):
    """Start remembering sheet switches for this Calc document (once per document)."""
    if _exit["terminating"]:
        return
    try:
        if not model or not model.supportsService("com.sun.star.sheet.SpreadsheetDocument"):
            return
        e = _recent_entry(model)
        if e.get("listening"):
            return
        ctrl = model.getCurrentController()
        if ctrl is None:
            return
        listener = ActivationListener(model)
        ctrl.addActivationEventListener(listener)
        e["listening"], e["ctrl"], e["listener"] = True, ctrl, listener
        touch_recent(model, ctrl.getActiveSheet().getName())
        if not _exit["hooked"]:
            ctx = uno.getComponentContext()
            ctx.getServiceManager().createInstanceWithContext("com.sun.star.frame.Desktop", ctx).addTerminateListener(StopOnExit())
            _exit["hooked"] = True
    except Exception:
        pass


# ------------------------------------------------------------------ sheet information
def col_letters(c):
    s = ""
    c += 1
    while c:
        c, r = divmod(c - 1, 26)
        s = chr(65 + r) + s
    return s


def a1_range(lr, lc):
    return "A1" if lr == 0 and lc == 0 else "A1:%s%d" % (col_letters(lc), lr + 1)


def used_area(sheet):
    """(last row, last column), or (-1, -1) for an empty sheet."""
    cur = sheet.createCursor()
    cur.gotoEndOfUsedArea(False)
    ra = cur.getRangeAddress()
    lr, lc = ra.EndRow, ra.EndColumn
    if lr == 0 and lc == 0 and sheet.getCellByPosition(0, 0).Type.value == "EMPTY":
        return -1, -1
    return lr, lc


def index_sheet_name(doc):
    try:
        props = doc.getDocumentProperties().getUserDefinedProperties()
        name = props.getPropertyValue(INDEX_PROP)
        if name and doc.getSheets().hasByName(name):
            return name
    except Exception:
        pass
    return None


def sheet_infos(doc):
    sheets = doc.getSheets()
    active = doc.getCurrentController().getActiveSheet().getName()
    index = index_sheet_name(doc)
    out = []
    for i in range(sheets.getCount()):
        s = sheets.getByIndex(i)
        lr, lc = used_area(s)
        try:
            charts = s.getCharts().getCount()
        except Exception:
            charts = 0
        try:
            pivot = s.getDataPilotTables().getCount() > 0
        except Exception:
            pivot = False
        name = s.getName()
        out.append({
            "name": name, "index": i, "hidden": not s.IsVisible, "lastRow": lr, "lastCol": lc,
            "charts": charts, "pivot": pivot, "active": name == active, "isIndex": name == index,
        })
    return out


def score(name, q):
    """Same ranking as CellLite: exact > starts-with > word-start > substring > all words present."""
    t = (q or "").strip().lower()
    if not t:
        return 1
    n = name.lower()
    if n == t:
        return 100
    if n.startswith(t):
        return 80
    if re.search(r"(^|[\s_\-.])" + re.escape(t), n):
        return 60
    if t in n:
        return 40
    if all(k in n for k in t.split()):
        return 20
    return 0


def natural_key(s):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", s)]


def unique_name(sheets, base):
    if not sheets.hasByName(base):
        return base
    n = 2
    while sheets.hasByName("%s %d" % (base, n) if base == INDEX_NAME else "%s%d" % (base, n)):
        n += 1
    return "%s %d" % (base, n) if base == INDEX_NAME else "%s%d" % (base, n)


def notes(s):
    bits = []
    if s["active"]:
        bits.append("Current")
    if s["hidden"]:
        bits.append("Hidden")
    if s["pivot"]:
        bits.append("Pivot")
    if s["charts"]:
        bits.append("%d chart%s" % (s["charts"], "s" if s["charts"] > 1 else ""))
    if s["isIndex"]:
        bits.append("Index")
    return " · ".join(bits)


# ------------------------------------------------------------------ Contents (index) sheet
def build_index(doc):
    """Create or refresh a 'Contents' sheet (first position) with a link to every other sheet."""
    sheets = doc.getSheets()
    undo = doc.getUndoManager()
    undo.enterUndoContext("Create index sheet")
    try:
        name = index_sheet_name(doc)
        if name is None:
            name = unique_name(sheets, INDEX_NAME)
            sheets.insertNewByName(name, 0)
        else:
            sheets.moveByName(name, 0)
        idx = sheets.getByName(name)
        lr, lc = used_area(idx)
        if lr >= 0:
            idx.getCellRangeByPosition(0, 0, max(lc, 3), lr).clearContents(1023)

        props = doc.getDocumentProperties().getUserDefinedProperties()
        if props.getPropertySetInfo().hasPropertyByName(INDEX_PROP):
            props.setPropertyValue(INDEX_PROP, name)
        else:
            props.addProperty(INDEX_PROP, const("com.sun.star.beans.PropertyAttribute.REMOVABLE"), name)

        others = [sheets.getByIndex(i) for i in range(sheets.getCount()) if sheets.getByIndex(i).getName() != name]
        bold = const("com.sun.star.awt.FontWeight.BOLD")

        title = idx.getCellByPosition(0, 0)
        title.setString("Contents")
        title.CharWeight, title.CharHeight, title.CharColor = bold, 16, GREEN
        sub = idx.getCellByPosition(0, 1)
        sub.setString("%d sheets · Ctrl+click a name to open it" % len(others))
        sub.CharPosture = uno.Enum("com.sun.star.awt.FontSlant", "ITALIC")
        sub.CharColor = 0x666666

        head = idx.getCellRangeByPosition(0, 3, 3, 3)
        head.setDataArray((("#", "Sheet", "Used range", "Rows"),))
        head.CellBackColor, head.CharColor, head.CharWeight = GREEN, 0xFFFFFF, bold

        for i, s in enumerate(others):
            r = 4 + i
            slr, slc = used_area(s)
            idx.getCellByPosition(0, r).setValue(i + 1)
            link = idx.getCellByPosition(1, r)
            link.setString("")
            field = doc.createInstance("com.sun.star.text.TextField.URL")
            field.URL = "#'%s'.A1" % s.getName().replace("'", "''")
            field.Representation = s.getName()
            text = link.getText()
            text.insertTextContent(text.getEnd(), field, False)
            idx.getCellByPosition(2, r).setString("(empty)" if slr < 0 else a1_range(slr, slc))
            idx.getCellByPosition(3, r).setValue(0 if slr < 0 else slr + 1)

        cols = idx.getColumns()
        for c, w in enumerate((1300, 6800, 3700, 2400)):  # 1/100 mm
            cols.getByIndex(c).Width = w

        ctrl = doc.getCurrentController()
        ctrl.setActiveSheet(idx)
        ctrl.freezeAtPosition(0, 4)
    finally:
        undo.leaveUndoContext()
    return name, len(others)


# ------------------------------------------------------------------ preferences
def _pref_path(ctx):
    try:
        ps = ctx.getServiceManager().createInstanceWithContext("com.sun.star.util.PathSettings", ctx)
        return os.path.join(uno.fileUrlToSystemPath(ps.UserConfig), "sheetshome.json")
    except Exception:
        return None


def load_prefs(ctx):
    p = {"sort": 0, "hidden": True}
    try:
        with open(_pref_path(ctx), encoding="utf-8") as f:
            p.update(json.load(f))
    except Exception:
        pass
    return p


def save_prefs(ctx, p):
    try:
        with open(_pref_path(ctx), "w", encoding="utf-8") as f:
            json.dump(p, f)
    except Exception:
        pass


# ------------------------------------------------------------------ small UI helpers
def msgbox(ctx, parent, text, title="Sheets Home", kind="INFOBOX", buttons=1):
    tk = ctx.getServiceManager().createInstanceWithContext("com.sun.star.awt.Toolkit", ctx)
    box = tk.createMessageBox(parent, uno.Enum("com.sun.star.awt.MessageBoxType", kind), buttons, title, text)
    return box.execute()


def ask_yes_no(ctx, parent, text):
    yes_no = const("com.sun.star.awt.MessageBoxButtons.BUTTONS_YES_NO") | const("com.sun.star.awt.MessageBoxButtons.DEFAULT_BUTTON_YES")
    return msgbox(ctx, parent, text, kind="QUERYBOX", buttons=yes_no) == const("com.sun.star.awt.MessageBoxResults.YES")


class DialogBuilder:
    def __init__(self, ctx, title, w, h):
        self.ctx = ctx
        self.smgr = ctx.getServiceManager()
        self.model = self.smgr.createInstanceWithContext("com.sun.star.awt.UnoControlDialogModel", ctx)
        self.model.Title, self.model.Width, self.model.Height = title, w, h
        self.model.Moveable = True
        self.model.Closeable = True

    def add(self, kind, name, x, y, w, h, **props):
        m = self.model.createInstance("com.sun.star.awt.UnoControl%sModel" % kind if "." not in kind else kind)
        m.PositionX, m.PositionY, m.Width, m.Height = x, y, w, h
        for k, v in props.items():
            setattr(m, k, v)
        self.model.insertByName(name, m)
        return m

    def create(self, parent):
        dlg = self.smgr.createInstanceWithContext("com.sun.star.awt.UnoControlDialog", self.ctx)
        dlg.setModel(self.model)
        tk = self.smgr.createInstanceWithContext("com.sun.star.awt.Toolkit", self.ctx)
        dlg.createPeer(tk, parent)
        return dlg


def ask_text(ctx, parent, title, label, value):
    b = DialogBuilder(ctx, title, 200, 62)
    b.add("FixedText", "lbl", 6, 6, 188, 10, Label=label)
    b.add("Edit", "ed", 6, 18, 188, 13, Text=value)
    b.add("Button", "ok", 84, 42, 52, 14, Label="OK", DefaultButton=True, PushButtonType=1)
    b.add("Button", "cancel", 142, 42, 52, 14, Label="Cancel", PushButtonType=2)
    dlg = b.create(parent)
    ed = dlg.getControl("ed")
    ed.setSelection(uno.createUnoStruct("com.sun.star.awt.Selection", 0, len(value)))
    ed.setFocus()
    ok = dlg.execute() == 1
    text = ed.getText().strip()
    dlg.dispose()
    return text if ok else None


# ------------------------------------------------------------------ Sheets Home dialog
SORTS = ("Workbook order", "Name A → Z", "Name Z → A", "Most data first")
RECENT_BUTTONS = 6


class SheetsHome(unohelper.Base, XActionListener, XTextListener, XItemListener, XKeyListener,
                 XMouseListener, XGridSelectionListener):
    def __init__(self, ctx, frame):
        self.ctx = ctx
        self.frame = frame
        self.doc = frame.getController().getModel()
        self.parent = frame.getContainerWindow()
        self.prefs = load_prefs(ctx)
        self.shown = []
        self.recent_shown = []
        self.busy = False
        track(self.doc)

    # ---- layout
    def build(self):
        b = DialogBuilder(self.ctx, "Sheets Home", 470, 272)
        self.b = b
        b.add("FixedText", "count", 6, 5, 300, 10, FontWeight=150.0)
        b.add("Edit", "search", 6, 19, 196, 13, HelpText="Search sheets by name")
        b.add("ListBox", "sort", 208, 19, 92, 13, Dropdown=True, StringItemList=SORTS,
              SelectedItems=(int(self.prefs.get("sort", 0)),))
        b.add("CheckBox", "hidden", 308, 21, 80, 10, Label="Show hidden", State=1 if self.prefs.get("hidden", True) else 0)
        b.add("FixedText", "recentLbl", 6, 40, 32, 10, Label="Recent:")
        for i in range(RECENT_BUTTONS):
            b.add("Button", "recent%d" % i, 38 + i * 50, 37, 48, 13, Label="", Enabled=False)

        smgr = self.ctx.getServiceManager()
        grid = b.add("com.sun.star.awt.grid.UnoControlGridModel", "grid", 6, 55, 302, 192,
                     ShowRowHeader=False, ShowColumnHeader=True, HScroll=False, VScroll=True,
                     SelectionModel=uno.Enum("com.sun.star.view.SelectionType", "SINGLE"))
        cols = smgr.createInstanceWithContext("com.sun.star.awt.grid.DefaultGridColumnModel", self.ctx)
        # widths are in dialog units and must fit the 302-unit grid (minus its scrollbar)
        for title, w, flex, align in (("#", 20, 0, "CENTER"), ("Sheet", 118, 1, "LEFT"), ("Used range", 54, 0, "LEFT"),
                                      ("Rows", 36, 0, "CENTER"), ("Notes", 58, 0, "LEFT")):
            c = cols.createColumn()
            c.Title, c.ColumnWidth, c.Flexibility = title, w, flex
            c.MinWidth = 80 if title == "Sheet" else 16
            c.HorizontalAlign = uno.Enum("com.sun.star.style.HorizontalAlignment", align)
            cols.addColumn(c)
        grid.ColumnModel = cols
        grid.GridDataModel = smgr.createInstanceWithContext("com.sun.star.awt.grid.DefaultGridDataModel", self.ctx)

        b.add("FixedText", "pvLbl", 314, 55, 150, 10, Label="Preview", FontWeight=150.0)
        pv = b.add("com.sun.star.awt.grid.UnoControlGridModel", "preview", 314, 66, 150, 94,
                   ShowRowHeader=True, ShowColumnHeader=True, HScroll=False, VScroll=False, RowHeaderWidth=22,
                   SelectionModel=uno.Enum("com.sun.star.view.SelectionType", "NONE"))
        pcols = smgr.createInstanceWithContext("com.sun.star.awt.grid.DefaultGridColumnModel", self.ctx)
        for c in range(4):
            col = pcols.createColumn()
            col.Title, col.ColumnWidth, col.Flexibility = col_letters(c), 30, 1
            pcols.addColumn(col)
        pv.ColumnModel = pcols
        pv.GridDataModel = smgr.createInstanceWithContext("com.sun.star.awt.grid.DefaultGridDataModel", self.ctx)

        y = 168
        for name, label in (("rename", "Rename…"), ("toggle", "Hide"), ("new", "+ New sheet"), ("index", "Create index sheet")):
            b.add("Button", name, 314, y, 150, 14, Label=label)
            y += 18
        b.add("FixedText", "hint", 6, 254, 300, 10, Label="Type to search · ↑ ↓ to choose · Enter to open · Esc to close")
        b.add("Button", "open", 352, 252, 54, 14, Label="Open", DefaultButton=True)
        b.add("Button", "close", 410, 252, 54, 14, Label="Close", PushButtonType=2)

        self.dlg = b.create(self.parent)
        c = self.dlg.getControl
        c("search").addTextListener(self)
        c("search").addKeyListener(self)
        c("grid").addKeyListener(self)
        c("sort").addItemListener(self)
        c("hidden").addItemListener(self)
        c("grid").addSelectionListener(self)
        c("grid").addMouseListener(self)
        for name in ["rename", "toggle", "new", "index", "open"] + ["recent%d" % i for i in range(RECENT_BUTTONS)]:
            c(name).setActionCommand(name)
            c(name).addActionListener(self)

    def run(self):
        self.build()
        self.render(select_name=self.doc.getCurrentController().getActiveSheet().getName())
        self.dlg.getControl("search").setFocus()
        self.dlg.execute()
        self.dlg.dispose()

    # ---- data
    def render(self, select_name=None):
        self.busy = True
        try:
            c = self.dlg.getControl
            q = c("search").getText()
            show_hidden = bool(self.prefs.get("hidden", True))
            sort = int(self.prefs.get("sort", 0))
            all_sheets = sheet_infos(self.doc)
            rows = [(s, score(s["name"], q)) for s in all_sheets if show_hidden or not s["hidden"]]
            rows = [r for r in rows if r[1] > 0]
            if q.strip():
                rows.sort(key=lambda r: (-r[1], r[0]["index"]))
            elif sort == 1:
                rows.sort(key=lambda r: natural_key(r[0]["name"]))
            elif sort == 2:
                rows.sort(key=lambda r: natural_key(r[0]["name"]), reverse=True)
            elif sort == 3:
                rows.sort(key=lambda r: -(r[0]["lastRow"] + 1) * (r[0]["lastCol"] + 1))
            self.shown = [r[0] for r in rows]

            hidden_n = sum(1 for s in all_sheets if s["hidden"])
            label = "%d sheet%s" % (len(all_sheets), "" if len(all_sheets) == 1 else "s")
            if hidden_n:
                label += " · %d hidden" % hidden_n
            if q.strip():
                label += " · %d match%s" % (len(self.shown), "" if len(self.shown) == 1 else "es")
            self.b.model.getByName("count").Label = label

            data = self.b.model.getByName("grid").GridDataModel
            data.removeAllRows()
            if self.shown:
                data.addRows(tuple("" for _ in self.shown), tuple((
                    str(s["index"] + 1), s["name"],
                    "—" if s["lastRow"] < 0 else a1_range(s["lastRow"], s["lastCol"]),
                    "{:,}".format(0 if s["lastRow"] < 0 else s["lastRow"] + 1),
                    notes(s)) for s in self.shown))

            # recent sheets (only when not searching)
            existing = {s["name"] for s in all_sheets}
            self.recent_shown = [] if q.strip() else [n for n in recent_names(self.doc) if n in existing][:RECENT_BUTTONS]
            for i in range(RECENT_BUTTONS):
                m = self.b.model.getByName("recent%d" % i)
                name = self.recent_shown[i] if i < len(self.recent_shown) else ""
                m.Label = name if len(name) <= 12 else name[:11] + "…"
                m.HelpText = name
                m.Enabled = bool(name)
            self.b.model.getByName("recentLbl").Enabled = bool(self.recent_shown)

            pick = 0
            if select_name:
                for i, s in enumerate(self.shown):
                    if s["name"] == select_name:
                        pick = i
                        break
            self.select(pick)
        finally:
            self.busy = False
        self.update_side()

    def select(self, i):
        grid = self.dlg.getControl("grid")
        grid.deselectAllRows()
        if not self.shown:
            return
        i = max(0, min(i, len(self.shown) - 1))
        grid.selectRow(i)
        try:
            grid.goToCell(1, i)
        except Exception:
            pass

    def current(self):
        rows = self.dlg.getControl("grid").getSelectedRows()
        if rows and 0 <= rows[0] < len(self.shown):
            return self.shown[rows[0]]
        return None

    def update_side(self):
        s = self.current()
        m = self.b.model
        for name in ("rename", "toggle", "open"):
            m.getByName(name).Enabled = s is not None
        m.getByName("toggle").Label = "Unhide" if s and s["hidden"] else "Hide"
        data = m.getByName("preview").GridDataModel
        data.removeAllRows()
        if not s:
            m.getByName("pvLbl").Label = "Preview"
            return
        m.getByName("pvLbl").Label = "Preview — " + ("empty sheet" if s["lastRow"] < 0 else s["name"])
        if s["lastRow"] < 0:
            return
        sheet = self.doc.getSheets().getByName(s["name"])
        rows = min(6, s["lastRow"] + 1)
        for r in range(rows):
            data.addRow(str(r + 1), tuple(sheet.getCellByPosition(c, r).getString()[:18] for c in range(4)))

    # ---- actions
    def open_sheet(self, name):
        sheets = self.doc.getSheets()
        if not sheets.hasByName(name):
            return
        sheet = sheets.getByName(name)
        if not sheet.IsVisible:
            if not ask_yes_no(self.ctx, self.dlg.getPeer(), '"%s" is hidden. Unhide it and open it?' % name):
                return
            sheet.IsVisible = True
        self.doc.getCurrentController().setActiveSheet(sheet)
        self.dlg.endExecute()

    def rename(self, s):
        new = ask_text(self.ctx, self.dlg.getPeer(), "Rename sheet", "New name for \"%s\":" % s["name"], s["name"])
        if not new or new == s["name"]:
            return
        try:
            self.doc.getSheets().getByName(s["name"]).setName(new)
        except Exception:
            msgbox(self.ctx, self.dlg.getPeer(), 'Could not rename to "%s". The name may be in use or contain a character '
                   'that is not allowed ( [ ] * ? : / \\ ).' % new, kind="ERRORBOX")
            return
        rename_recent(self.doc, s["name"], new)
        self.render(select_name=new)

    def toggle_hidden(self, s):
        sheets = self.doc.getSheets()
        sheet = sheets.getByName(s["name"])
        if sheet.IsVisible:
            visible = [sheets.getByIndex(i) for i in range(sheets.getCount()) if sheets.getByIndex(i).IsVisible]
            if len(visible) <= 1:
                msgbox(self.ctx, self.dlg.getPeer(), "A workbook must have at least one visible sheet.")
                return
            ctrl = self.doc.getCurrentController()
            if ctrl.getActiveSheet().getName() == s["name"]:
                ctrl.setActiveSheet(next(v for v in visible if v.getName() != s["name"]))
            sheet.IsVisible = False
        else:
            sheet.IsVisible = True
        self.render(select_name=s["name"])

    def new_sheet(self):
        sheets = self.doc.getSheets()
        ctrl = self.doc.getCurrentController()
        name = unique_name(sheets, "Sheet")
        pos = ctrl.getActiveSheet().getRangeAddress().Sheet + 1
        sheets.insertNewByName(name, pos)
        ctrl.setActiveSheet(sheets.getByName(name))
        self.dlg.endExecute()

    # ---- listeners
    def actionPerformed(self, ev):
        cmd = ev.ActionCommand
        s = self.current()
        if cmd == "open" and s:
            self.open_sheet(s["name"])
        elif cmd == "rename" and s:
            self.rename(s)
        elif cmd == "toggle" and s:
            self.toggle_hidden(s)
        elif cmd == "new":
            self.new_sheet()
        elif cmd == "index":
            build_index(self.doc)
            self.dlg.endExecute()
        elif cmd.startswith("recent"):
            i = int(cmd[6:])
            if i < len(self.recent_shown):
                self.open_sheet(self.recent_shown[i])

    def textChanged(self, ev):
        self.render()

    def itemStateChanged(self, ev):
        if self.busy:
            return
        m = self.b.model
        self.prefs["sort"] = (m.getByName("sort").SelectedItems or (0,))[0]
        self.prefs["hidden"] = m.getByName("hidden").State == 1
        save_prefs(self.ctx, self.prefs)
        s = self.current()
        self.render(select_name=s["name"] if s else None)

    def selectionChanged(self, ev):
        if not self.busy:
            self.update_side()

    def keyPressed(self, ev):
        key = ev.KeyCode
        rows = self.dlg.getControl("grid").getSelectedRows()
        i = rows[0] if rows else 0
        if key == const("com.sun.star.awt.Key.DOWN"):
            self.select(i + 1)
        elif key == const("com.sun.star.awt.Key.UP"):
            self.select(i - 1)
        elif key == const("com.sun.star.awt.Key.PAGEDOWN"):
            self.select(i + 10)
        elif key == const("com.sun.star.awt.Key.PAGEUP"):
            self.select(i - 10)
        else:
            return
        self.update_side()

    def keyReleased(self, ev):
        pass

    def mousePressed(self, ev):
        if ev.ClickCount == 2:
            s = self.current()
            if s:
                self.open_sheet(s["name"])

    def mouseReleased(self, ev):
        pass

    def mouseEntered(self, ev):
        pass

    def mouseExited(self, ev):
        pass

    def disposing(self, ev):
        pass


# ------------------------------------------------------------------ UNO components
class ProtocolHandler(unohelper.Base, XInitialization, XDispatchProvider, XDispatch, XServiceInfo):
    def __init__(self, ctx, *args):
        self.ctx = ctx
        self.frame = None

    def initialize(self, args):
        if args:
            self.frame = args[0]

    def queryDispatch(self, url, target, flags):
        return self if (url.Complete or "").startswith(PROTOCOL) else None

    def queryDispatches(self, requests):
        return tuple(self.queryDispatch(r.FeatureURL, r.FrameName, r.SearchFlags) for r in requests)

    def dispatch(self, url, args):
        frame = self.frame
        if frame is None:
            return
        doc = frame.getController().getModel()
        if not doc.supportsService("com.sun.star.sheet.SpreadsheetDocument"):
            return
        cmd = url.Complete[len(PROTOCOL):].split("?")[0]
        if cmd == "Home":
            SheetsHome(self.ctx, frame).run()
        elif cmd == "Index":
            build_index(doc)

    def addStatusListener(self, listener, url):
        pass

    def removeStatusListener(self, listener, url):
        pass

    def getImplementationName(self):
        return HANDLER_IMPL

    def supportsService(self, name):
        return name == "com.sun.star.frame.ProtocolHandler"

    def getSupportedServiceNames(self):
        return ("com.sun.star.frame.ProtocolHandler",)


class Job(unohelper.Base, XJob, XServiceInfo):
    """Runs on OnViewCreated / OnLoad to start tracking recently used sheets."""

    def __init__(self, ctx, *args):
        self.ctx = ctx

    def execute(self, args):
        for a in args:
            if a.Name == "Environment":
                for e in a.Value:
                    if e.Name == "Model":
                        track(e.Value)
        return None

    def getImplementationName(self):
        return JOB_IMPL

    def supportsService(self, name):
        return name == "com.sun.star.task.Job"

    def getSupportedServiceNames(self):
        return ("com.sun.star.task.Job",)


g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(ProtocolHandler, HANDLER_IMPL, ("com.sun.star.frame.ProtocolHandler",))
g_ImplementationHelper.addImplementation(Job, JOB_IMPL, ("com.sun.star.task.Job",))
