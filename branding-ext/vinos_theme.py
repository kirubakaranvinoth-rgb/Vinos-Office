# Vino's Office theme switching.
#
# LibreOffice applies a Light/Dark change only partly until it restarts (backgrounds change, but icons
# and menus keep the old theme), so with Windows in dark mode, choosing Light looks broken. This:
#   - adds View > Vino's Office Theme > Light / Dark / Same as Windows   (com.vinosoffice.theme:Light ...)
#   - watches the Appearance setting (also when changed in Tools > Options) and offers to restart
#     Vino's Office so the new theme is applied completely.
#
# Rules that keep it from interfering with LibreOffice (an earlier version could freeze it when the theme
# and the menu language were changed together in Tools > Options):
#   - never block LibreOffice: the question is a native Windows box on a background thread, shown
#     1.5 s after the change so Tools > Options has finished saving;
#   - if the menu language changed too (or a restart is already on its way), LibreOffice asks to restart
#     on its own, so we stay quiet;
#   - when Vino's Office closes or restarts, our open question closes itself and the listener is removed.

import uno
import unohelper
from com.sun.star.beans import PropertyValue
from com.sun.star.frame import XDispatch, XDispatchProvider, XTerminateListener
from com.sun.star.lang import XInitialization, XServiceInfo
from com.sun.star.task import XJob
from com.sun.star.util import XChangesListener

PROTOCOL = "com.vinosoffice.theme:"
HANDLER_IMPL = "com.vinosoffice.ThemeHandler"
JOB_IMPL = "com.vinosoffice.ThemeWatcher"
APPEARANCE = "/org.openoffice.Office.Common/Appearance"
LINGU = "/org.openoffice.Office.Linguistic/General"
MODES = {"Auto": 0, "Light": 1, "Dark": 2}

TEXT = {
    "en": {"names": {0: "Same as Windows", 1: "Light", 2: "Dark"},
           "restart": "Vino's Office needs to restart to finish switching to the %s theme.\n\n"
                      "Restart now? You will be asked to save any open documents.",
           "already": "Vino's Office is already using the %s theme."},
    "zh-CN": {"names": {0: "跟随 Windows", 1: "浅色", 2: "深色"},
              "restart": "Vino's Office 需要重新启动才能完成切换到“%s”主题。\n\n现在重新启动吗？系统会提示您保存打开的文档。",
              "already": "Vino's Office 已经在使用“%s”主题。"},
    "zh-TW": {"names": {0: "跟隨 Windows", 1: "淺色", 2: "深色"},
              "restart": "Vino's Office 需要重新啟動才能完成切換到「%s」佈景主題。\n\n現在重新啟動嗎？系統會提示您儲存開啟的文件。",
              "already": "Vino's Office 已經在使用「%s」佈景主題。"},
}

_state = {"watching": False, "asking": False, "pending": False, "terminating": False,
          "last": None, "ui": None, "node": None, "listener": None}


def _cfg(ctx, path, write=False):
    cp = ctx.getServiceManager().createInstanceWithContext("com.sun.star.configuration.ConfigurationProvider", ctx)
    svc = "com.sun.star.configuration.ConfigurationUpdateAccess" if write else "com.sun.star.configuration.ConfigurationAccess"
    return cp.createInstanceWithArguments(svc, (PropertyValue(Name="nodepath", Value=path),))


def current_mode(ctx):
    try:
        return int(_cfg(ctx, APPEARANCE).getPropertyValue("ApplicationAppearance"))
    except Exception:
        return 0


def ui_locale(ctx):
    try:
        return _cfg(ctx, LINGU).getPropertyValue("UILocale") or ""
    except Exception:
        return ""


def texts(ctx):
    loc = ui_locale(ctx)
    if not loc:
        try:
            loc = _cfg(ctx, "/org.openoffice.Setup/L10N").getPropertyValue("ooLocale") or ""
        except Exception:
            loc = ""
    if loc.startswith(("zh-TW", "zh-HK", "zh-MO")):
        return TEXT["zh-TW"]
    if loc.startswith("zh"):
        return TEXT["zh-CN"]
    return TEXT["en"]


def _parent_window(ctx):
    try:
        desktop = ctx.getServiceManager().createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
        frame = desktop.getCurrentFrame() or desktop.getActiveFrame()
        return frame.getContainerWindow() if frame else None
    except Exception:
        return None


BOX_TITLE = "Vino's Office"


def ask(text, yes_no=True):
    """Native Windows message box. Always called on a background thread (see in_background), so
    LibreOffice's main thread never waits on it. Native, because by then Vino's Office is half-way
    between themes and its own dialogs would draw white text on white buttons."""
    import ctypes
    MB_YESNO, MB_OK, MB_ICONQUESTION, MB_ICONINFO = 0x4, 0x0, 0x20, 0x40
    MB_SETFOREGROUND, MB_TOPMOST = 0x10000, 0x40000
    flags = (MB_YESNO | MB_ICONQUESTION if yes_no else MB_OK | MB_ICONINFO) | MB_SETFOREGROUND | MB_TOPMOST
    return ctypes.windll.user32.MessageBoxW(None, text, BOX_TITLE, flags) == 6  # IDYES


def close_open_question():
    """Close our question if it is still open (Vino's Office is closing or restarting anyway)."""
    try:
        import ctypes
        u = ctypes.windll.user32
        hwnd = u.FindWindowW("#32770", BOX_TITLE)
        while hwnd:
            u.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE = answer "No"
            hwnd = u.FindWindowExW(None, hwnd, "#32770", BOX_TITLE)
    except Exception:
        pass


def in_background(fn):
    import threading
    threading.Thread(target=fn, daemon=True).start()


def restart_already_requested(ctx):
    try:
        return ctx.getValueByName("/singletons/com.sun.star.task.OfficeRestartManager").isRestartRequested(False)
    except Exception:
        return False


def offer_restart(ctx):
    """Background thread: wait for the settings change to settle, then ask once and maybe restart."""
    import time
    time.sleep(1.5)  # let Tools > Options finish saving everything (theme and language are saved separately)
    _state["pending"] = False
    if _state["asking"] or _state["terminating"]:
        return
    if ui_locale(ctx) != _state["ui"] or restart_already_requested(ctx):
        # The menu language changed as well: LibreOffice asks to restart by itself, and that restart
        # applies the theme too. A second question (and a second restart) is what caused the freeze.
        _state["ui"] = ui_locale(ctx)
        return
    _state["asking"] = True
    try:
        t = texts(ctx)
        yes = ask(t["restart"] % t["names"].get(current_mode(ctx), ""))
        if yes and not _state["terminating"] and not restart_already_requested(ctx):
            ctx.getValueByName("/singletons/com.sun.star.task.OfficeRestartManager").requestRestart(None)
    except Exception:
        pass
    finally:
        _state["asking"] = False


COLORSCHEME = "/org.openoffice.Office.UI/ColorScheme"
VINO_SCHEMES = ("VINO_LIGHT", "VINO_DARK")             # defined in VinoTheme.xcu
MANAGED_SCHEMES = ("", "COLOR_SCHEME_LIBREOFFICE_AUTOMATIC") + VINO_SCHEMES


def windows_is_dark():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except Exception:
        return False


def sync_scheme(ctx, mode=None):
    """Select the Vino colour scheme that matches Light / Dark / Same as Windows. Leaves a colour scheme
    the user picked themselves in Tools > Options alone. Returns True if it changed anything."""
    try:
        cur = _cfg(ctx, COLORSCHEME).getPropertyValue("CurrentColorScheme") or ""
        if cur not in MANAGED_SCHEMES:
            return False
        mode = current_mode(ctx) if mode is None else mode
        want = "VINO_DARK" if mode == 2 or (mode == 0 and windows_is_dark()) else "VINO_LIGHT"
        if cur == want:
            return False
        upd = _cfg(ctx, COLORSCHEME, True)
        upd.setPropertyValue("CurrentColorScheme", want)
        upd.commitChanges()
        return True
    except Exception:
        return False


def set_mode(ctx, mode):
    if mode == current_mode(ctx):
        return False
    sync_scheme(ctx, mode)  # colours for the new theme, ready for the restart
    upd = _cfg(ctx, APPEARANCE, True)
    upd.setPropertyValue("ApplicationAppearance", mode)
    upd.commitChanges()  # the watcher below sees this and offers the restart
    return True


class AppearanceWatcher(unohelper.Base, XChangesListener):
    def __init__(self, ctx):
        self.ctx = ctx

    def changesOccurred(self, event):
        # Only note the change here; never show UI or restart from inside a settings commit.
        if _state["terminating"]:
            return
        mode = current_mode(self.ctx)
        if mode != _state["last"]:
            _state["last"] = mode
            ctx = self.ctx
            in_background(lambda: sync_scheme(ctx))  # matching Vino colours, also when the language restart comes first
            if not _state["pending"]:
                _state["pending"] = True
                in_background(lambda: offer_restart(ctx))

    def disposing(self, event):
        _state["watching"] = False


class StopOnExit(unohelper.Base, XTerminateListener):
    """Detach everything when Vino's Office closes or restarts."""

    def queryTermination(self, event):
        close_open_question()

    def notifyTermination(self, event):
        stop_watching()

    def disposing(self, event):
        stop_watching()


def stop_watching():
    _state["terminating"] = True
    close_open_question()
    node, listener = _state.get("node"), _state.get("listener")
    _state["node"] = _state["listener"] = None
    _state["watching"] = False
    if node is not None and listener is not None:
        try:
            node.removeChangesListener(listener)
        except Exception:
            pass


def start_watching(ctx):
    if _state["watching"] or _state["terminating"]:
        return
    try:
        _state["last"] = current_mode(ctx)
        _state["ui"] = ui_locale(ctx)
        # first start after install, or Windows switched light/dark while using "Same as Windows"
        _state["scheme_changed_at_start"] = sync_scheme(ctx)
        node = _cfg(ctx, APPEARANCE)
        listener = AppearanceWatcher(ctx)
        node.addChangesListener(listener)
        _state["node"], _state["listener"] = node, listener  # keep alive; removed again on exit
        _state["watching"] = True
        ctx.getServiceManager().createInstanceWithContext("com.sun.star.frame.Desktop", ctx).addTerminateListener(StopOnExit())
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
            t = texts(self.ctx)
            in_background(lambda: ask(t["already"] % t["names"][mode], yes_no=False))

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
