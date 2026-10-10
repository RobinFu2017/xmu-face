/**
 * 平板识别页：摄像头预览 + 可配置抓拍模式与前后摄切换。
 *
 * capture_mode=manual|auto
 * capture_interval_ms：自动间隔，默认 1500，最小 500
 * facing=user|environment：前置 / 后置，默认 environment
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
  const facingEl = document.getElementById("facingMode");
  const labelEl = document.getElementById("deviceLabel");
  const btnCapture = document.getElementById("btnCapture");
  const btnStartCam = document.getElementById("btnStartCam");
  const btnStopCam = document.getElementById("btnStopCam");
  const btnOpenStage = document.getElementById("btnOpenStage");

  const LS_MODE = "faceweb_capture_mode";
  const LS_INTERVAL = "faceweb_capture_interval_ms";
  const LS_LABEL = "faceweb_device_label";
  const LS_FACING = "faceweb_facing";

  let stream = null;
  let timer = null;
  let inFlight = false; // 请求进行中则跳过自动抓拍
  let starting = false; // 正在打开/切换摄像头

  function syncButtons() {
    const open = !!stream;
    btnStartCam.disabled = open || inFlight || starting;
    btnStopCam.disabled = !open || inFlight || starting;
    btnCapture.disabled = !open || inFlight || starting;
    btnOpenStage.disabled = false;
  }

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
    const facingRaw =
      params.get("facing") ||
      localStorage.getItem(LS_FACING) ||
      "environment";
    const facing = facingRaw === "user" ? "user" : "environment";

    modeEl.value = mode === "auto" ? "auto" : "manual";
    intervalEl.value = String(interval);
    facingEl.value = facing;
    labelEl.value = localStorage.getItem(LS_LABEL) || "";
    persist();
    applyModeUi();
    syncButtons();
  }

  function persist() {
    localStorage.setItem(LS_MODE, modeEl.value);
    localStorage.setItem(LS_INTERVAL, String(intervalEl.value));
    localStorage.setItem(LS_LABEL, labelEl.value.trim());
    localStorage.setItem(LS_FACING, facingEl.value);
  }

  function applyModeUi() {
    // 自动模式下仍保留按钮，便于立刻补拍一张
    btnCapture.textContent = modeEl.value === "auto" ? "立即识别" : "识别";
    restartTimer();
  }

  function stopStream() {
    if (!stream) return;
    stream.getTracks().forEach((t) => t.stop());
    stream = null;
    video.srcObject = null;
  }

  /**
   * 打开或按当前朝向重启摄像头。
   * @param {boolean} forceRestart 已有流时是否强制按新 facing 重开
   */
  async function startCamera(forceRestart) {
    if (stream && !forceRestart) return;
    if (starting) return;

    starting = true;
    syncButtons();
    stopTimer();
    stopStream();

    const facing = facingEl.value === "user" ? "user" : "environment";
    try {
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
          // 单摄或不支持 facingMode 时回退默认设备
          stream = await navigator.mediaDevices.getUserMedia({
            video: true,
            audio: false,
          });
          if (forceRestart) {
            alert("无法切换到所选摄像头，已使用默认摄像头");
          }
        } catch (e2) {
          throw e2;
        }
      }
      video.srcObject = stream;
      await video.play();
      restartTimer();
    } finally {
      starting = false;
      syncButtons();
    }
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
      syncButtons();
      return;
    }
    if (inFlight) return;
    inFlight = true;
    syncButtons();
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
      syncButtons();
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
      resultEl.textContent = `${data.person.name}（${data.person.phone}）`;
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
  facingEl.addEventListener("change", () => {
    persist();
    // 已打开摄像头时立即按新朝向重启
    if (stream) {
      startCamera(true).catch((e) => alert(e.message || "切换摄像头失败"));
    }
  });
  labelEl.addEventListener("change", persist);
  btnStartCam.addEventListener("click", () =>
    startCamera(false).catch((e) => {
      alert(e.message);
      syncButtons();
    })
  );
  btnStopCam.addEventListener("click", () => {
    stopTimer();
    stopStream();
    resultEl.textContent = "摄像头已关闭";
    resultEl.className = "result";
    syncButtons();
  });
  btnOpenStage.addEventListener("click", () => {
    persist();
    stopTimer();
    stopStream();
    let interval = Number(intervalEl.value) || 1500;
    if (!Number.isFinite(interval) || interval < 500) interval = 500;
    const facing = facingEl.value === "user" ? "user" : "environment";
    const params = new URLSearchParams();
    params.set("capture_interval_ms", String(interval));
    params.set("facing", facing);
    const label = labelEl.value.trim();
    if (label) params.set("device_label", label);
    location.href = "/recognize/stage?" + params.toString();
  });
  btnCapture.addEventListener("click", () => captureAndRecognize());
  window.addEventListener("beforeunload", () => {
    stopTimer();
    stopStream();
  });
  document.addEventListener("visibilitychange", () => {
    // 切到后台暂停自动抓拍，回到前台再开
    if (document.hidden) stopTimer();
    else restartTimer();
  });

  readConfig();
})();
