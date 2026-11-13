# Vino's Office "Reading Mode" (like WPS): highlight the selected cell's row and column.
#
# LibreOffice Calc already draws the highlight (View > Column/Row Highlighting, .uno:ViewColumnRowHighlighting,
# setting Calc/Content/Display/ColumnRowHighlighting). Its colour is the "cell focus" colour (CalcCellFocus,
# which also colours the cell cursor and the active row/column header); when unset it follows the accent.
# This component adds:
#   com.vinosoffice.reading:Toggle   turn Reading Mode on/off (ribbon button, Ctrl+Shift+Alt+R)
#   com.vinosoffice.reading:Color    pick the highlight colour (palette + "More colours..."), turns it on
# The colour is stored in both Vino colour schemes (and the current scheme if it's another one), so it
# survives switching between Light and Dark.

import uno
import unohelper
from com.sun.star.awt import XActionListener
from com.sun.star.beans import PropertyValue
from com.sun.star.frame import XDispatch, XDispatchProvider
from com.sun.star.lang import XInitialization, XServiceInfo

PROTOCOL = "com.vinosoffice.reading:"
HANDLER_IMPL = "com.vinosoffice.ReadingHandler"
TOGGLE = ".uno:ViewColumnRowHighlighting"
SCHEMES = "/org.openoffice.Office.UI/ColorScheme"
DISPLAY = "/org.openoffice.Office.Calc/Content/Display"
DEFAULT = 0x0E8FA3  # Vino teal (what it looks like before the user picks anything)

PALETTE = [  # (colour, en, zh-CN, zh-TW) - the band itself is drawn as a light tint of this colour
    (0x0E8FA3, "Teal", "青色", "青色"),
    (0xF5B800, "Yellow", "黄色", "黃色"),
    (0x2E9E44, "Green", "绿色", "綠色"),
    (0x2F6FD6, "Blue", "蓝色", "藍色"),
    (0x8E44C9, "Purple", "紫色", "紫色"),
    (0xE0457B, "Pink", "粉色", "粉色"),
    (0xF07B1A, "Orange", "橙色", "橙色"),
    (0x6B7785, "Grey", "灰色", "灰色"),
]
TEXT = {
    "en": {"title": "Reading Mode colour", "pick": "Highlight the selected cell's row and column in:",
           "more": "More colours...", "reset": "Default", "cancel": "Cancel", "col": 1},
    "zh-CN": {"title": "阅读模式颜色", "pick": "用以下颜色突出显示所选单元格的行和列：",
              "more": "更多颜色...", "reset": "默认", "cancel": "取消", "col": 2},
    "zh-TW": {"title": "閱讀模式色彩", "pick": "以下列色彩醒目提示所選儲存格的列和欄：",
              "more": "更多色彩...", "reset": "預設", "cancel": "取消", "col": 3},
}


def _cfg(ctx, path, write=False):
    cp = ctx.getServiceManager().createInstanceWithContext("com.sun.star.configuration.ConfigurationProvider", ctx)
    svc = "com.sun.star.configuration.ConfigurationUpdateAccess" if write else "com.sun.star.configuration.ConfigurationAccess"
    return cp.createInstanceWithArguments(svc, (PropertyValue(Name="nodepath", Value=path),))


def _lang(ctx):
    loc = ""
    for path, prop in (("/org.openoffice.Office.Linguistic/General", "UILocale"), ("/org.openoffice.Setup/L10N", "ooLocale")):
        try:
            loc = _cfg(ctx, path).getPropertyValue(prop) or ""
        except Exception:
            loc = ""
        if loc:
            break
    if loc.startswith(("zh-TW", "zh-HK", "zh-MO")):
        return TEXT["zh-TW"]
    return TEXT["zh-CN"] if loc.startswith("zh") else TEXT["en"]


def is_on(ctx):
    try:
        return bool(_cfg(ctx, DISPLAY).getPropertyValue("ColumnRowHighlighting"))
    except Exception:
        return False


def _dispatch(ctx, frame, url):
    ctx.getServiceManager().createInstanceWithContext("com.sun.star.frame.DispatchHelper", ctx).executeDispatch(frame, url, "", 0, ())


def _repaint(frame):
    """Redraw with the new colour now, instead of on the next cell move."""
    try:
        ctrl = frame.getController()
        ctrl.select(ctrl.getSelection())
        frame.getContainerWindow().invalidate(0)
    except Exception:
        pass


def current_color(ctx):
    try:
        scheme = _cfg(ctx, SCHEMES).getPropertyValue("CurrentColorScheme")
        v = _cfg(ctx, "%s/ColorSchemes/org.openoffice.Office.UI:ColorScheme['%s']/CalcCellFocus" % (SCHEMES, scheme)).getPropertyValue("Color")
        return int(v) if v is not None else DEFAULT
    except Exception:
        return DEFAULT


def set_color(ctx, color):
    names = {"VINO_LIGHT", "VINO_DARK"}
    try:
        names.add(_cfg(ctx, SCHEMES).getPropertyValue("CurrentColorScheme"))
    except Exception:
        pass
    for scheme in names:
        try:
            u = _cfg(ctx, "%s/ColorSchemes/org.openoffice.Office.UI:ColorScheme['%s']/CalcCellFocus" % (SCHEMES, scheme), True)
            u.setPropertyValue("Color", int(color))
            u.commitChanges()
        except Exception:
            pass


def more_colours(ctx, parent, initial):
    """LibreOffice's own colour picker; returns the colour or None."""
    try:
        picker = ctx.getServiceManager().createInstanceWithArgumentsAndContext(
            "com.sun.star.ui.dialogs.ColorPicker", (PropertyValue(Name="ParentWindow", Value=parent),), ctx)
        picker.setPropertyValues((PropertyValue(Name="Color", Value=int(initial)),))
        if picker.execute() == 1:
            for p in picker.getPropertyValues():
                if p.Name == "Color":
                    return int(p.Value)
    except Exception:
        pass
    return None


class _Click(unohelper.Base, XActionListener):
    def __init__(self, dlg, result, value):
        self.dlg, self.result, self.value = dlg, result, value

    def actionPerformed(self, ev):
        self.result["value"] = self.value
        self.dlg.endExecute()

    def disposing(self, ev):
        pass


def choose_colour(ctx, frame):
    """Small palette dialog. Returns a colour, 'more', 'reset' or None (cancelled)."""
    t = _lang(ctx)
    smgr = ctx.getServiceManager()
    m = smgr.createInstanceWithContext("com.sun.star.awt.UnoControlDialogModel", ctx)
    m.Title, m.Width, m.Height = t["title"], 228, 104
    lbl = m.createInstance("com.sun.star.awt.UnoControlFixedTextModel")
    lbl.PositionX, lbl.PositionY, lbl.Width, lbl.Height, lbl.Label = 8, 6, 212, 10, t["pick"]
    m.insertByName("lbl", lbl)
    current = current_color(ctx)
    for i, entry in enumerate(PALETTE):
        b = m.createInstance("com.sun.star.awt.UnoControlButtonModel")
        b.PositionX, b.PositionY, b.Width, b.Height = 8 + (i % 4) * 53, 20 + (i // 4) * 26, 50, 22
        b.BackgroundColor = entry[0]
        b.TextColor = 0xFFFFFF if entry[0] not in (0xF5B800,) else 0x1B2733
        b.Label = ("✓ " if entry[0] == current else "") + entry[t["col"]]
        m.insertByName("c%d" % i, b)
    for name, label, x in (("more", t["more"], 8), ("reset", t["reset"], 100), ("cancel", t["cancel"], 164)):
        b = m.createInstance("com.sun.star.awt.UnoControlButtonModel")
        b.PositionX, b.PositionY, b.Width, b.Height, b.Label = x, 80, 88 if name == "more" else 56, 16, label
        if name == "cancel":
            b.PushButtonType = 2
        m.insertByName(name, b)
    dlg = smgr.createInstanceWithContext("com.sun.star.awt.UnoControlDialog", ctx)
    dlg.setModel(m)
    dlg.createPeer(smgr.createInstanceWithContext("com.sun.star.awt.Toolkit", ctx), frame.getContainerWindow())
    try:  # centre over the Vino's Office window
        win, me = frame.getContainerWindow().getPosSize(), dlg.getPosSize()
        dlg.setPosSize(win.X + max(0, (win.Width - me.Width) // 2), win.Y + max(0, (win.Height - me.Height) // 3),
                       0, 0, uno.getConstantByName("com.sun.star.awt.PosSize.POS"))
    except Exception:
        pass
    result = {"value": None}
    for i, entry in enumerate(PALETTE):
        dlg.getControl("c%d" % i).addActionListener(_Click(dlg, result, entry[0]))
    dlg.getControl("more").addActionListener(_Click(dlg, result, "more"))
    dlg.getControl("reset").addActionListener(_Click(dlg, result, "reset"))
    dlg.execute()
    dlg.dispose()
    return result["value"]


class ReadingHandler(unohelper.Base, XInitialization, XDispatchProvider, XDispatch, XServiceInfo):
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
        cmd = url.Complete[len(PROTOCOL):].split("?")[0]
        if cmd == "Toggle":
            _dispatch(self.ctx, frame, TOGGLE)
        elif cmd == "Color":
            choice = choose_colour(self.ctx, frame)
            if choice == "more":
                choice = more_colours(self.ctx, frame.getContainerWindow(), current_color(self.ctx))
            elif choice == "reset":
                choice = DEFAULT
            if choice is None:
                return
            set_color(self.ctx, choice)
            if not is_on(self.ctx):
                _dispatch(self.ctx, frame, TOGGLE)
            _repaint(frame)

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


g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(ReadingHandler, HANDLER_IMPL, ("com.sun.star.frame.ProtocolHandler",))
