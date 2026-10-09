/**
 * 正式识别展示页：无按钮，配置只读 URL。
 *
 * capture_interval_ms：自动间隔，默认 1500，最小 500
 * facing=user|environment：前置 / 后置，默认 environment
 * device_label：写入识别日志，页面不展示
 *
 * 上一次 /api/recognize 未返回前不发起下一次。命中后弹出气泡，
 * 连续约 3 秒没有新命中再收起。
 */
(function () {
  const video = document.getElementById("video");
  const canvas = document.getElementById("canvas");
  const hintEl = document.getElementById("statusHint");
  const bubbleEl = document.getElementById("successBubble");
  const bubbleName = document.getElementById("bubbleName");
  const bubblePhone = document.getElementById("bubblePhone");
  const bubbleCollege = document.getElementById("bubbleCollege");
  const bubbleYear = document.getElementById("bubbleYear");

  const HIDE_MS = 3000;

  let stream = null;
  let timer = null;
  let hideTimer = null;
  let inFlight = false;
  let intervalMs = 1500;
  let facing = "environment";
  let deviceLabel = "";

  function readConfig() {
    const params = new URLSearchParams(location.search);
    let interval = Number(params.get("capture_interval_ms") || 1500);
    if (!Number.isFinite(interval) || interval < 500) interval = 500;
    intervalMs = interval;
    facing = params.get("facing") === "user" ? "user" : "environment";
    deviceLabel = (params.get("device_label") || "").trim();
  }

  function showHint(text) {
    if (!text) {
      hintEl.hidden = true;
      hintEl.textContent = "";
      return;
    }
    hintEl.textContent = text;
    hintEl.hidden = false;
  }

  function maskPhone(phone) {
    const s = String(phone || "").trim();
    if (s.length >= 7) {
      return s.slice(0, 3) + "****" + s.slice(-4);
    }
    return s || "—";
  }

  function fillBubble(person) {
    bubbleName.textContent = person.name || "—";
    bubblePhone.textContent = maskPhone(person.phone);
    bubbleCollege.textContent = person.college || "—";
    bubbleYear.textContent = person.enroll_year || "—";
    bubbleEl.hidden = false;
    if (hideTimer) clearTimeout(hideTimer);
    hideTimer = setTimeout(() => {
      bubbleEl.hidden = true;
      hideTimer = null;
    }, HIDE_MS);
  }

  function stopStream() {
    if (!stream) return;
    stream.getTracks().forEach((t) => t.stop());
    stream = null;
    video.srcObject = null;
  }

  function stopTimer() {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }

  function restartTimer() {
    stopTimer();
    if (!stream) return;
    timer = setInterval(() => {
      if (!inFlight) captureAndRecognize();
    }, intervalMs);
  }

  async function startCamera() {
    stopTimer();
    stopStream();
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: { ideal: facing },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
      });
    } catch (e1) {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: true,
          audio: false,
        });
      } catch (e2) {
        showHint("无法打开摄像头：" + (e2.message || e2));
        return;
      }
    }
    video.classList.toggle("mirror", facing === "user");
    video.srcObject = stream;
    await video.play();
    showHint("");
    restartTimer();
    captureAndRecognize();
  }

  function grabJpegBlob() {
    const w = video.videoWidth || 640;
    const h = video.videoHeight || 480;
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0, w, h);
    return new Promise((resolve) => {
      canvas.toBlob((blob) => resolve(blob), "image/jpeg", 0.85);
    });
  }

  async function captureAndRecognize() {
    if (!stream || inFlight) return;
    inFlight = true;
    try {
      const blob = await grabJpegBlob();
      if (!blob) return;
      const fd = new FormData();
      fd.append("image", blob, "capture.jpg");
      fd.append("device_label", deviceLabel);
      const res = await fetch("/api/recognize", { method: "POST", body: fd });
      const data = await res.json();
      if (data.matched && data.person) {
        fillBubble(data.person);
      }
    } catch (err) {
      // 正式页不打断画面；失败等下一轮
    } finally {
      inFlight = false;
    }
  }

  window.addEventListener("beforeunload", () => {
    stopTimer();
    stopStream();
    if (hideTimer) clearTimeout(hideTimer);
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stopTimer();
    else restartTimer();
  });

  readConfig();
  startCamera();
})();
