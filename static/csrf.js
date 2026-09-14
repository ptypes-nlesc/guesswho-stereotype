// CSRF helper for same-origin fetch POSTs (Flask-WTF X-CSRFToken).
(function (global) {
  function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : "";
  }

  function csrfHeaders(extra) {
    const headers = Object.assign({}, extra || {});
    const token = csrfToken();
    if (token) {
      headers["X-CSRFToken"] = token;
    }
    return headers;
  }

  global.csrfToken = csrfToken;
  global.csrfHeaders = csrfHeaders;
})(window);
