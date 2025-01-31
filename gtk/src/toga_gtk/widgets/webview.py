from travertino.size import at_least

from toga.widgets.webview import JavaScriptResult

from ..libs import GLib, WebKit2
from .base import Widget


class WebView(Widget):
    """GTK WebView implementation."""

    def create(self):
        if WebKit2 is None:  # pragma: no cover
            raise RuntimeError(
                "Unable to import WebKit2. Ensure that the system package "
                "providing Webkit2 and its GTK bindings have been installed."
            )

        self.native = WebKit2.WebView()

        settings = self.native.get_settings()
        settings.set_property("enable-developer-extras", True)

        # The default cache model is WEB_BROWSER, which will
        # use the backing cache to minimize hits on the web server.
        # This can result in stale web content being served, even if
        # the source document (and the web server response) changes.
        context = self.native.get_context()
        context.set_cache_model(WebKit2.CacheModel.DOCUMENT_VIEWER)

        self.native.connect("load-changed", self.gtk_on_load_changed)

        self.load_future = None

    def gtk_on_load_changed(self, widget, load_event, *args):
        if load_event == WebKit2.LoadEvent.FINISHED:
            self.interface.on_webview_load(None)

            if self.load_future:
                self.load_future.set_result(None)
                self.load_future = None

    def get_url(self):
        url = self.native.get_uri()
        return None if url == "about:blank" else url

    def _loaded(self, data):
        # Internal method to fake a load event.
        self.native.emit("load-changed", WebKit2.LoadEvent.FINISHED)
        return False

    def set_url(self, value, future=None):
        if value:
            self.native.load_uri(value)
        else:
            self.native.load_plain_text("")
            # GTK doesn't emit a load-changed signal when plain text is loaded; so we
            # fake it. We can't emit the signal directly because it will be handled
            # immediately. During creation of an empty webview, the URL is set to None,
            # which means an event can be triggered before the widget instance has
            # finished construction. So, we defer the call with a 0 timeout.
            GLib.timeout_add(0, self._loaded, None)

        self.load_future = future

    def get_user_agent(self):
        return self.native.get_settings().props.user_agent

    def set_user_agent(self, value):
        # replace user agent of webview (webview has own one)
        self.native.get_settings().props.user_agent = value

    def set_content(self, root_url, content):
        self.native.load_html(content, root_url)

    def evaluate_javascript(self, javascript, on_result=None):
        # Construct a future on the event loop
        result = JavaScriptResult()

        # Define a callback that will update the future when
        # the Javascript is complete.
        def gtk_js_finished(webview, task, *user_data):
            """If `run_javascript_finish` from GTK returns a result, unmarshal it, and
            call back with the result."""
            try:
                js_result = webview.run_javascript_finish(task)
                value = js_result.get_js_value()
                if value.is_boolean():
                    value = value.to_boolean()
                elif value.is_number():
                    value = value.to_double()
                else:
                    value = value.to_string()

                result.future.set_result(value)
                if on_result:
                    on_result(value)
            except Exception as e:
                exc = RuntimeError(str(e))
                result.future.set_exception(exc)
                if on_result:
                    on_result(None, exception=exc)

        # Invoke the javascript method, with a callback that will set
        # the future when a result is available.
        self.native.run_javascript(javascript, None, gtk_js_finished)

        # wait for the future, and return the result
        return result

    def rehint(self):
        self.interface.intrinsic.width = at_least(self.interface._MIN_WIDTH)
        self.interface.intrinsic.height = at_least(self.interface._MIN_HEIGHT)
