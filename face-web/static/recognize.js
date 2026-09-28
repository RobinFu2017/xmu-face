/**
 * 平板识别页：摄像头预览 + 可配置抓拍模式。
 *
 * capture_mode=manual|auto
 * capture_interval_ms：自动间隔，默认 1500，最小 500
 * URL 参数优先，其次 localStorage，最后默认值。
 * 自动模式：上一次 /api/recognize 未返回前不发起下一次，避免打满 CPU。
 */
(function () {
  const video = document.getElementById("video");
  const canvas = document.getElementById("canvas");
  const resultEl = document.getElementById("result");
  const debugEl = document.getElementById("debug");
  const modeEl = document.getElementById("captureMode");
  const intervalEl = document.getElementById("captureInterval");
  const labelEl = document.getElementById("deviceLabel");
  const btnCapture = document.getElementById("btnCapture");
  const btnStartCam = document.getElementById("btnStartCam");

  const LS_MODE = "faceweb_capture_mode";
  const LS_INTERVAL = "faceweb_capture_interval_ms";
  const LS_LABEL = "faceweb_device_label";

  let stream = null;
  let timer = null;
  let inFlight = false; // 请求进行中则跳过自动抓拍

  function readConfig() {
    const params = new URLSearchParams(location.search);
    const mode =
      params.get("capture_mode") ||
      localStorage.getItem(LS_MODE) ||
      "manual";
    let interval = Number(
      params.get("capture_interval_ms") ||
        localStorage.getItem(LS_INTERVAL) ||
        1500
    );
    if (!Number.isFinite(interval) || interval < 500) interval = 500;
    modeEl.value = mode === "auto" ? "auto" : "manual";
    intervalEl.value = String(interval);
    labelEl.value = localStorage.getItem(LS_LABEL) || "";
    persist();
    applyModeUi();
  }

  function persist() {
    localStorage.setItem(LS_MODE, modeEl.value);
    localStorage.setItem(LS_INTERVAL, String(intervalEl.value));
    localStorage.setItem(LS_LABEL, labelEl.value.trim());
  }

  function applyModeUi() {
    // 自动模式下仍保留按钮，便于立刻补拍一张
    btnCapture.textContent = modeEl.value === "auto" ? "立即识别" : "识别";
    restartTimer();
  }

  async function startCamera() {
    if (stream) return;
    try {
      // environment=后置，更适合闸机/签到；失败则回退到默认摄像头
      stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
      });
    } catch (e1) {
      stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    }
    video.srcObject = stream;
    await video.play();
    restartTimer();
  }

  function stopTimer() {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }

  function restartTimer() {
    stopTimer();
    if (modeEl.value !== "auto" || !stream) return;
    const ms = Math.max(500, Number(intervalEl.value) || 1500);
    // 用 setInterval 调度；真正抓拍前检查 inFlight
    timer = setInterval(() => {
      if (!inFlight) captureAndRecognize();
    }, ms);
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
    if (!stream) {
      resultEl.textContent = "请先打开摄像头";
      resultEl.className = "result fail";
      return;
    }
    if (inFlight) return;
    inFlight = true;
    btnCapture.disabled = true;
    try {
      const blob = await grabJpegBlob();
      if (!blob) throw new Error("抓拍失败");
      const fd = new FormData();
      fd.append("image", blob, "capture.jpg");
      fd.append("device_label", labelEl.value.trim());
      const res = await fetch("/api/recognize", { method: "POST", body: fd });
      const data = await res.json();
      renderResult(data);
    } catch (err) {
      resultEl.textContent = "请求失败: " + err.message;
      resultEl.className = "result fail";
    } finally {
      inFlight = false;
      btnCapture.disabled = false;
    }
  }

  function renderResult(data) {
    debugEl.textContent = JSON.stringify(data, null, 2);
    if (data.error_code === "no_face") {
      resultEl.textContent = "未检测到人脸";
      resultEl.className = "result fail";
      return;
    }
    if (data.matched && data.person) {
      resultEl.textContent = `${data.person.name}（${data.person.employee_no}）`;
      resultEl.className = "result ok";
      return;
    }
    resultEl.textContent = "未识别";
    resultEl.className = "result fail";
  }

  modeEl.addEventListener("change", () => {
    persist();
    applyModeUi();
  });
  intervalEl.addEventListener("change", () => {
    persist();
    restartTimer();
  });
  labelEl.addEventListener("change", persist);
  btnStartCam.addEventListener("click", () => startCamera().catch((e) => alert(e.message)));
  btnCapture.addEventListener("click", () => captureAndRecognize());
  window.addEventListener("beforeunload", stopTimer);
  document.addEventListener("visibilitychange", () => {
    // 切到后台暂停自动抓拍，回到前台再开
    if (document.hidden) stopTimer();
    else restartTimer();
  });

  readConfig();
})();
