# Vino's Office theme switching.
#
# LibreOffice applies a Light/Dark change only partly until it restarts (backgrounds change, but icons
# and menus keep the old theme), so with Windows in dark mode, choosing Light looks broken. This:
#   - adds View > Vino's Office Theme > Light / Dark / Same as Windows   (com.vinosoffice.theme:Light ...)
#   - watches the Appearance setting (also when changed in Tools > Options) and offers to restart
#     Vino's Office straight away so the new theme is applied completely.

import uno
import unohelper
from com.sun.star.beans import PropertyValue
from com.sun.star.frame import XDispatch, XDispatchProvider
from com.sun.star.lang import XInitialization, XServiceInfo
from com.sun.star.task import XJob
from com.sun.star.util import XChangesListener

PROTOCOL = "com.vinosoffice.theme:"
HANDLER_IMPL = "com.vinosoffice.ThemeHandler"
JOB_IMPL = "com.vinosoffice.ThemeWatcher"
APPEARANCE = "/org.openoffice.Office.Common/Appearance"
MODES = {"Auto": 0, "Light": 1, "Dark": 2}
NAMES = {0: "Same as Windows", 1: "Light", 2: "Dark"}

_state = {"watching": False, "asking": False, "last": None}


def _cfg(ctx, path, write=False):
    cp = ctx.getServiceManager().createInstanceWithContext("com.sun.star.configuration.ConfigurationProvider", ctx)
    svc = "com.sun.star.configuration.ConfigurationUpdateAccess" if write else "com.sun.star.configuration.ConfigurationAccess"
    return cp.createInstanceWithArguments(svc, (PropertyValue(Name="nodepath", Value=path),))


def current_mode(ctx):
    try:
        return int(_cfg(ctx, APPEARANCE).getPropertyValue("ApplicationAppearance"))
    except Exception:
        return 0


def _parent_window(ctx):
    try:
        desktop = ctx.getServiceManager().createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
        frame = desktop.getCurrentFrame() or desktop.getActiveFrame()
        return frame.getContainerWindow() if frame else None
    except Exception:
        return None


def ask(ctx, text, yes_no=True):
    """Message box. On Windows a native one: by the time we ask, Vino's Office is half-way between themes
    and its own dialogs would draw white text on white buttons."""
    try:
        import ctypes
        MB_YESNO, MB_OK, MB_ICONQUESTION, MB_ICONINFO = 0x4, 0x0, 0x20, 0x40
        MB_SETFOREGROUND, MB_TOPMOST, MB_TASKMODAL = 0x10000, 0x40000, 0x2000
        flags = (MB_YESNO | MB_ICONQUESTION if yes_no else MB_OK | MB_ICONINFO) | MB_SETFOREGROUND | MB_TOPMOST | MB_TASKMODAL
        return ctypes.windll.user32.MessageBoxW(None, text, "Vino's Office", flags) == 6  # IDYES
    except Exception:
        tk = ctx.getServiceManager().createInstanceWithContext("com.sun.star.awt.Toolkit", ctx)
        buttons = uno.getConstantByName("com.sun.star.awt.MessageBoxButtons.BUTTONS_YES_NO" if yes_no else
                                        "com.sun.star.awt.MessageBoxButtons.BUTTONS_OK")
        box = tk.createMessageBox(_parent_window(ctx), uno.Enum("com.sun.star.awt.MessageBoxType", "QUERYBOX" if yes_no else "INFOBOX"),
                                  buttons, "Vino's Office", text)
        return box.execute() == uno.getConstantByName("com.sun.star.awt.MessageBoxResults.YES")


def offer_restart(ctx, mode):
    """Ask once, then restart Vino's Office (documents get the usual save prompt)."""
    if _state["asking"]:
        return
    _state["asking"] = True
    try:
        if ask(ctx, "Vino's Office needs to restart to finish switching to the %s theme.\n\n"
                    "Restart now? You will be asked to save any open documents." % NAMES.get(mode, "new")):
            ctx.getValueByName("/singletons/com.sun.star.task.OfficeRestartManager").requestRestart(None)
    finally:
        _state["asking"] = False


def set_mode(ctx, mode):
    if mode == current_mode(ctx):
        return False
    upd = _cfg(ctx, APPEARANCE, True)
    upd.setPropertyValue("ApplicationAppearance", mode)
    upd.commitChanges()  # the watcher below sees this and offers the restart
    return True


class AppearanceWatcher(unohelper.Base, XChangesListener):
    def __init__(self, ctx):
        self.ctx = ctx

    def changesOccurred(self, event):
        mode = current_mode(self.ctx)
        if mode != _state["last"]:
            _state["last"] = mode
            offer_restart(self.ctx, mode)

    def disposing(self, event):
        _state["watching"] = False


def start_watching(ctx):
    if _state["watching"]:
        return
    try:
        _state["last"] = current_mode(ctx)
        node = _cfg(ctx, APPEARANCE)
        node.addChangesListener(AppearanceWatcher(ctx))
        _state["node"] = node  # keep the access object alive, or the listener goes away with it
        _state["watching"] = True
    except Exception:
        pass


class ThemeHandler(unohelper.Base, XInitialization, XDispatchProvider, XDispatch, XServiceInfo):
    def __init__(self, ctx, *args):
        self.ctx = ctx

    def initialize(self, args):
        pass

    def queryDispatch(self, url, target, flags):
        return self if (url.Complete or "").startswith(PROTOCOL) else None

    def queryDispatches(self, requests):
        return tuple(self.queryDispatch(r.FeatureURL, r.FrameName, r.SearchFlags) for r in requests)

    def dispatch(self, url, args):
        mode = MODES.get(url.Complete[len(PROTOCOL):].split("?")[0])
        if mode is None:
            return
        start_watching(self.ctx)
        if not set_mode(self.ctx, mode):
            ask(self.ctx, "Vino's Office is already using the %s theme." % NAMES[mode], yes_no=False)

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


class ThemeWatcher(unohelper.Base, XJob, XServiceInfo):
    """Started with Vino's Office, so theme changes made in Tools > Options also get the restart offer."""

    def __init__(self, ctx, *args):
        self.ctx = ctx

    def execute(self, args):
        start_watching(self.ctx)
        return None

    def getImplementationName(self):
        return JOB_IMPL

    def supportsService(self, name):
        return name == "com.sun.star.task.Job"

    def getSupportedServiceNames(self):
        return ("com.sun.star.task.Job",)


g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(ThemeHandler, HANDLER_IMPL, ("com.sun.star.frame.ProtocolHandler",))
g_ImplementationHelper.addImplementation(ThemeWatcher, JOB_IMPL, ("com.sun.star.task.Job",))
