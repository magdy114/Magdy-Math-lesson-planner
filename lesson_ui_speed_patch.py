from __future__ import annotations


FAST_UI_SCRIPT = r"""
<script id="lesson-fast-download-ui">
(() => {
  const form = document.getElementById('plannerForm');
  if (!form || form.dataset.fastDownloadBound === '1') return;
  form.dataset.fastDownloadBound = '1';

  const overlay = document.getElementById('loadingOverlay');
  const preview = document.getElementById('previewBox');
  const generateButton = document.getElementById('generateBtn');
  const previewButton = document.getElementById('previewBtn');

  function isArabic() {
    return document.documentElement.lang !== 'en';
  }

  function htmlEscape(value) {
    return String(value || '').replace(/[&<>"']/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[char]));
  }

  function plainText(value) {
    return String(value || '')
      .replace(/<script[\s\S]*?<\/script>/gi, '')
      .replace(/<style[\s\S]*?<\/style>/gi, '')
      .replace(/<[^>]+>/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function busy(active, seconds = 0) {
    if (overlay) overlay.classList.toggle('hidden', !active);
    if (generateButton) generateButton.disabled = active;
    if (previewButton) previewButton.disabled = active;
    if (!overlay || !active) return;
    const heading = overlay.querySelector('h3');
    const paragraph = overlay.querySelector('p');
    if (heading) {
      heading.textContent = isArabic()
        ? 'جاري تجهيز ملف Word سريعًا...'
        : 'Preparing the Word file quickly...';
    }
    if (paragraph) {
      paragraph.textContent = isArabic()
        ? `يتم استخدام المحتوى الجاهز دون انتظار OpenAI — ${seconds} ثانية`
        : `Using ready content without waiting for OpenAI — ${seconds}s`;
    }
  }

  form.addEventListener('submit', async event => {
    event.preventDefault();
    event.stopImmediatePropagation();

    let elapsed = 0;
    busy(true, elapsed);
    const clock = window.setInterval(() => {
      elapsed += 1;
      busy(true, elapsed);
    }, 1000);

    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 45000);

    try {
      const response = await fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        cache: 'no-store',
        signal: controller.signal,
      });

      const contentType = response.headers.get('content-type') || '';
      const downloadable = response.ok && (
        contentType.includes('wordprocessingml') ||
        contentType.includes('application/zip') ||
        contentType.includes('application/octet-stream')
      );

      if (!downloadable) {
        const message = plainText(await response.text()).slice(0, 900);
        if (preview) {
          preview.innerHTML = `<div class="alert error">${
            isArabic() ? 'تعذر إنشاء ملف Word.' : 'Could not create the Word file.'
          }<br>${htmlEscape(message)}</div>`;
        }
        return;
      }

      // Hide the dark overlay immediately when the server response arrives.
      busy(false);

      const blob = await response.blob();
      const disposition = response.headers.get('content-disposition') || '';
      const match = disposition.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i);
      const filename = match
        ? decodeURIComponent(match[1].replace(/"/g, ''))
        : (contentType.includes('zip') ? 'Lesson_Plans.zip' : 'lesson_plan.docx');

      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 3000);

      if (preview) {
        preview.innerHTML = `<div class="alert success">${
          isArabic()
            ? `تم إنشاء الملف وبدأ التحميل خلال ${elapsed} ثانية.`
            : `The file was created and the download started in ${elapsed} seconds.`
        }</div>`;
      }
    } catch (error) {
      if (preview) {
        const message = error && error.name === 'AbortError'
          ? (isArabic()
              ? 'تجاوز الطلب 45 ثانية وتم إيقاف شاشة الانتظار. جرّب درسًا واحدًا أو أعد المحاولة بعد التأكد أن Render في حالة Live.'
              : 'The request exceeded 45 seconds. Try one lesson or retry after Render is Live.')
          : String(error || 'Connection error');
        preview.innerHTML = `<div class="alert error">${htmlEscape(message)}</div>`;
      }
    } finally {
      window.clearInterval(clock);
      window.clearTimeout(timeout);
      busy(false);
    }
  }, true);
})();
</script>
"""


def install(app) -> None:
    if getattr(app, "_fast_lesson_ui_installed", False):
        return

    @app.after_request
    def inject_fast_lesson_ui(response):
        try:
            content_type = response.headers.get("Content-Type", "")
            if (
                response.status_code == 200
                and "text/html" in content_type
                and response.direct_passthrough is False
            ):
                body = response.get_data(as_text=True)
                if (
                    'id="plannerForm"' in body
                    and 'id="lesson-fast-download-ui"' not in body
                    and "</body>" in body
                ):
                    body = body.replace("</body>", FAST_UI_SCRIPT + "\n</body>")
                    response.set_data(body)
                    response.headers["Content-Length"] = str(len(response.get_data()))
        except Exception:
            app.logger.exception("Could not inject fast lesson download UI")
        return response

    app._fast_lesson_ui_installed = True
