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

  const isArabic = () => document.documentElement.lang !== 'en';
  const htmlEscape = value => String(value || '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));
  const plainText = value => String(value || '')
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<style[\s\S]*?<\/style>/gi, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  function busy(active, seconds = 0) {
    if (overlay) overlay.classList.toggle('hidden', !active);
    if (generateButton) generateButton.disabled = active;
    if (previewButton) previewButton.disabled = active;
    if (!overlay || !active) return;

    const heading = overlay.querySelector('h3');
    const paragraph = overlay.querySelector('p');
    if (heading) {
      heading.textContent = isArabic()
        ? 'جاري تجهيز ملف Word...'
        : 'Preparing the Word file...';
    }
    if (paragraph) {
      const queued = seconds >= 8;
      paragraph.textContent = isArabic()
        ? (queued
            ? `الطلب في قائمة التنفيذ الآمنة مع طلبات المعلمين — ${seconds} ثانية`
            : `يتم استخدام المحتوى الجاهز دون انتظار OpenAI — ${seconds} ثانية`)
        : (queued
            ? `The request is safely queued with other teachers — ${seconds}s`
            : `Using ready content without waiting for OpenAI — ${seconds}s`);
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
    const timeout = window.setTimeout(() => controller.abort(), 95000);

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

      busy(false);
      const cacheHeader = response.headers.get('x-lesson-cache') || '';
      const cacheHits = response.headers.get('x-lesson-cache-hits') || '';
      const fromCache = cacheHeader === 'HIT' || (cacheHits && Number(cacheHits) > 0);

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
        const cacheText = fromCache
          ? (isArabic() ? ' وتم استخدام النسخة السريعة المحفوظة.' : ' A fast cached copy was used.')
          : '';
        preview.innerHTML = `<div class="alert success">${
          isArabic()
            ? `تم إنشاء الملف وبدأ التحميل خلال ${elapsed} ثانية.${cacheText}`
            : `The file was created and the download started in ${elapsed} seconds.${cacheText}`
        }</div>`;
      }
    } catch (error) {
      if (preview) {
        const message = error && error.name === 'AbortError'
          ? (isArabic()
              ? 'تجاوز الطلب 95 ثانية. لم تُفقد البيانات؛ أعد المحاولة بعد قليل أو أنشئ عددًا أقل من الدروس في الطلب الواحد.'
              : 'The request exceeded 95 seconds. Retry shortly or generate fewer lessons in one request.')
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
            if response.status_code == 200 and "text/html" in content_type and response.direct_passthrough is False:
                body = response.get_data(as_text=True)
                if 'id="plannerForm"' in body and 'id="lesson-fast-download-ui"' not in body and "</body>" in body:
                    body = body.replace("</body>", FAST_UI_SCRIPT + "\n</body>")
                    response.set_data(body)
                    response.headers["Content-Length"] = str(len(response.get_data()))
        except Exception:
            app.logger.exception("Could not inject fast lesson download UI")
        return response

    app._fast_lesson_ui_installed = True
