# Vino's Office: modern ribbon layout.
#
# Switches each app (Calc, Writer, Impress, Draw) to LibreOffice's "Tabbed" ribbon (notebookbar.ui) the
# first time it opens, once per user. It uses the same command as View > User Interface > Tabbed, so the
# classic toolbars and menu bar are tidied away properly. Anyone who switches back to another layout keeps
# their choice: the switch is remembered in <user profile>/config/vinosoffice-ui.json and never repeated.

import json
import os

import uno
import unohelper
from com.sun.star.awt import XCallback
from com.sun.star.beans import PropertyValue
from com.sun.star.frame import XTerminateListener
from com.sun.star.lang import XServiceInfo
from com.sun.star.task import XJob

JOB_IMPL = "com.vinosoffice.RibbonJob"
RIBBON = "notebookbar.ui"
APPS = {
    "com.sun.star.sheet.SpreadsheetDocument": "Calc",
    "com.sun.star.text.TextDocument": "Writer",
    "com.sun.star.presentation.PresentationDocument": "Impress",
    "com.sun.star.drawing.DrawingDocument": "Draw",
}
_state = {"terminating": False, "hooked": False, "busy": set(), "models": {}}


def _log(ctx, msg):
    """Problems go to <user profile>/config/vinosoffice-ui.log (never shown to the user)."""
    try:
        with open(_flag_file(ctx).replace(".json", ".log"), "a", encoding="utf-8") as f:
            f.write(msg + chr(10))
    except Exception:
        pass


def _cfg(ctx, path):
    cp = ctx.getServiceManager().createInstanceWithContext("com.sun.star.configuration.ConfigurationProvider", ctx)
    return cp.createInstanceWithArguments("com.sun.star.configuration.ConfigurationAccess",
                                          (PropertyValue(Name="nodepath", Value=path),))


def _flag_file(ctx):
    ps = ctx.getServiceManager().createInstanceWithContext("com.sun.star.util.PathSettings", ctx)
    return os.path.join(uno.fileUrlToSystemPath(ps.UserConfig), "vinosoffice-ui.json")


def _done(ctx):
    try:
        with open(_flag_file(ctx), encoding="utf-8") as f:
            return set(json.load(f).get("ribbon", []))
    except Exception:
        return set()


def _mark_done(ctx, app):
    try:
        done = _done(ctx) | {app}
        with open(_flag_file(ctx), "w", encoding="utf-8") as f:
            json.dump({"ribbon": sorted(done)}, f)
    except Exception:
        pass


def current_layout(ctx, app):
    try:
        return _cfg(ctx, "/org.openoffice.Office.UI.ToolbarMode/Applications/"
                         "org.openoffice.Office.UI.ToolbarMode:Application['%s']" % app).getPropertyValue("Active")
    except Exception:
        return ""


class _Later(unohelper.Base, XCallback):
    def __init__(self, fn):
        self.fn = fn

    def notify(self, data):
        try:
            self.fn()
        except Exception as e:
            _log(self.ctx, "switch failed: %r" % (e,))


def on_main_thread(ctx, fn):
    cb = _Later(fn)
    cb.ctx = ctx
    ctx.getServiceManager().createInstanceWithContext("com.sun.star.awt.AsyncCallback", ctx).addCallback(cb, None)


class StopOnExit(unohelper.Base, XTerminateListener):
    def queryTermination(self, event):
        pass

    def notifyTermination(self, event):
        _state["terminating"] = True

    def disposing(self, event):
        _state["terminating"] = True


def _module_of(ctx, frame):
    try:
        return ctx.getServiceManager().createInstanceWithContext("com.sun.star.frame.ModuleManager", ctx).identify(frame)
    except Exception:
        return ""


def _live_frame(ctx, app):
    """The app's window as it is *now*. While an app starts, LibreOffice may replace the first window,
    so the frame seen in the event can already be gone."""
    model = _state["models"].get(app)
    try:
        frame = model.getCurrentController().getFrame()
        if APPS.get(_module_of(ctx, frame)) == app:
            return frame
    except Exception:
        pass
    try:
        frames = ctx.getServiceManager().createInstanceWithContext("com.sun.star.frame.Desktop", ctx).getFrames()
        for i in range(frames.getCount()):
            f = frames.getByIndex(i)
            if APPS.get(_module_of(ctx, f)) == app:
                return f
    except Exception:
        pass
    return None


MAX_TRIES = 20      # x 0.5 s: a window that is still starting up can't take the command yet


def retry_later(ctx, app, tries):
    import threading
    import time

    def wait_then_post():
        time.sleep(0.5)
        if not _state["terminating"]:
            on_main_thread(ctx, lambda: switch_to_ribbon(ctx, app, tries + 1))
    threading.Thread(target=wait_then_post, daemon=True).start()


def switch_to_ribbon(ctx, app, tries=0):
    """Main thread: same as View > User Interface > Tabbed."""
    if _state["terminating"] or app in _done(ctx):
        _state["busy"].discard(app)
        return
    if current_layout(ctx, app) == RIBBON:
        _state["busy"].discard(app)
        _mark_done(ctx, app)
        return
    frame = _live_frame(ctx, app)
    sent = False
    if frame is not None:
        try:
            helper = ctx.getServiceManager().createInstanceWithContext("com.sun.star.frame.DispatchHelper", ctx)
            helper.executeDispatch(frame, ".uno:ToolbarMode", "", 0, (PropertyValue(Name="Mode", Value=RIBBON),))
            sent = True
        except Exception as e:
            _log(ctx, "ribbon switch error: %r" % (e,))
    if sent and current_layout(ctx, app) == RIBBON:
        _state["busy"].discard(app)
        _mark_done(ctx, app)
    elif tries < MAX_TRIES:
        retry_later(ctx, app, tries)
    else:
        _state["busy"].discard(app)  # give up for now; the next window of this app tries again
        _log(ctx, "could not switch %s to the ribbon" % app)


def maybe_switch(ctx, model):
    if _state["terminating"] or model is None:
        return
    try:
        frame = model.getCurrentController().getFrame()
    except Exception as e:
        _log(ctx, "no frame: %r" % (e,))
        return
    app = APPS.get(_module_of(ctx, frame))
    if not app or app in _done(ctx):
        return
    _state["models"][app] = model  # newest window of this app; used when the switch actually runs
    if app in _state["busy"]:
        return
    if not _state["hooked"]:
        ctx.getServiceManager().createInstanceWithContext("com.sun.star.frame.Desktop", ctx).addTerminateListener(StopOnExit())
        _state["hooked"] = True
    _state["busy"].add(app)
    on_main_thread(ctx, lambda: switch_to_ribbon(ctx, app))


class RibbonJob(unohelper.Base, XJob, XServiceInfo):
    def __init__(self, ctx, *args):
        self.ctx = ctx

    def execute(self, args):
        for a in args:
            if a.Name == "Environment":
                for e in a.Value:
                    if e.Name == "Model":
                        maybe_switch(self.ctx, e.Value)
        return None

    def getImplementationName(self):
        return JOB_IMPL

    def supportsService(self, name):
        return name == "com.sun.star.task.Job"

    def getSupportedServiceNames(self):
        return ("com.sun.star.task.Job",)


g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(RibbonJob, JOB_IMPL, ("com.sun.star.task.Job",))
