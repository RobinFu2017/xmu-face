/** 管理后台：人员列表/导入/详情/日志。 */
const FACE_BADGE = {
  ok: "badge ok",
  missing: "badge warn",
  failed: "badge bad",
  none: "badge",
};

const AdminPeople = {
  async init() {
    document.getElementById("btnSearch").addEventListener("click", () => this.load());
    document.getElementById("importFile").addEventListener("change", (e) => this.importExcel(e));
    await this.load();
    const stats = await fetch("/api/stats").then((r) => r.json());
    document.getElementById("statsLine").textContent =
      `人员 ${stats.person_count} · 样本 ${stats.sample_count} · 索引 ${stats.index_size} · 人脸不合格 ${stats.face_failed} · 无照片 ${stats.face_missing} · 阈值 ${stats.match_threshold}`;
  },

  async importExcel(e) {
    const file = e.target.files && e.target.files[0];
    e.target.value = "";
    const msg = document.getElementById("importMsg");
    if (!file) return;
    msg.style.color = "";
    msg.textContent = "导入中，请稍候（含下载照片与录脸）…";
    const fd = new FormData();
    fd.append("file", file);
    try {
      const res = await fetch("/api/people/import", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) {
        msg.textContent = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
        return;
      }
      msg.style.color = "#0b6e4f";
      msg.textContent =
        `导入完成：新建 ${data.created}，更新 ${data.updated}，录脸成功 ${data.face_ok}，录脸失败 ${data.face_failed}` +
        (data.skipped && data.skipped.length ? `，跳过 ${data.skipped.length}` : "");
      this.load();
    } catch (err) {
      msg.textContent = "导入失败: " + err.message;
    }
  },

  async load() {
    const q = document.getElementById("searchQ").value.trim();
    const status = document.getElementById("statusFilter").value;
    const face_status = document.getElementById("faceFilter").value;
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (status) params.set("status", status);
    if (face_status) params.set("face_status", face_status);
    const data = await fetch("/api/people?" + params.toString()).then((r) => r.json());
    const tbody = document.querySelector("#peopleTable tbody");
    tbody.innerHTML = "";
    for (const p of data.items) {
      const tr = document.createElement("tr");
      const faceTitle = p.face_message ? ` title="${escapeAttr(p.face_message)}"` : "";
      tr.innerHTML = `
        <td><a href="/admin/people/${p.id}">${escapeHtml(p.name)}</a></td>
        <td>${escapeHtml(p.phone)}</td>
        <td>${escapeHtml(p.college || "")}</td>
        <td>${escapeHtml(p.ticket_type || "")}</td>
        <td>${escapeHtml(p.signup_status || "")}</td>
        <td><span class="${FACE_BADGE[p.face_status] || "badge"}"${faceTitle}>${escapeHtml(
          p.face_status_label || p.face_status
        )}</span></td>
        <td>${p.sample_count}</td>
        <td>${p.status === "active" ? "启用" : "停用"}</td>
        <td>
          <button data-id="${p.id}" data-act="toggle" type="button">${
            p.status === "active" ? "停用" : "启用"
          }</button>
          <button data-id="${p.id}" data-act="del" type="button">删除</button>
        </td>`;
      tbody.appendChild(tr);
    }
    tbody.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.getAttribute("data-id");
        const act = btn.getAttribute("data-act");
        if (act === "del") {
          if (!confirm("确认删除该人员及全部人脸？")) return;
          await fetch(`/api/people/${id}`, { method: "DELETE" });
        } else {
          const person = await fetch(`/api/people/${id}`).then((r) => r.json());
          const status = person.status === "active" ? "disabled" : "active";
          await fetch(`/api/people/${id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status }),
          });
        }
        this.load();
      });
    });
  },
};

const AdminPerson = {
  async init(personId) {
    this.personId = personId;
    const form = document.getElementById("personForm");
    form.addEventListener("submit", (e) => this.save(e));
    if (personId) {
      await this.load();
      document.getElementById("btnUpload").addEventListener("click", () => this.upload());
    }
  },

  fieldsFromForm() {
    return {
      name: document.getElementById("name").value.trim(),
      city: document.getElementById("city").value.trim(),
      college: document.getElementById("college").value.trim(),
      education: document.getElementById("education").value.trim(),
      enroll_year: document.getElementById("enroll_year").value.trim(),
      ticket_type: document.getElementById("ticket_type").value.trim(),
      signup_status: document.getElementById("signup_status").value.trim(),
      photo_url: document.getElementById("photo_url").value.trim(),
    };
  },

  async load() {
    const p = await fetch(`/api/people/${this.personId}`).then((r) => r.json());
    document.getElementById("phone").value = p.phone;
    document.getElementById("name").value = p.name;
    document.getElementById("city").value = p.city || "";
    document.getElementById("college").value = p.college || "";
    document.getElementById("education").value = p.education || "";
    document.getElementById("enroll_year").value = p.enroll_year || "";
    document.getElementById("ticket_type").value = p.ticket_type || "";
    document.getElementById("signup_status").value = p.signup_status || "";
    document.getElementById("photo_url").value = p.photo_url || "";
    document.getElementById("status").value = p.status;
    const faceLine = document.getElementById("faceStatusLine");
    faceLine.textContent =
      `人脸状态：${p.face_status_label || p.face_status}` +
      (p.face_message ? `（${p.face_message}）` : "");

    const box = document.getElementById("samples");
    box.innerHTML = "";
    for (const s of p.samples || []) {
      const div = document.createElement("div");
      div.className = "sample-card";
      div.innerHTML = `
        <img src="${s.image_url}" alt="face" />
        <div class="meta">质量 ${s.quality_score.toFixed(3)}
          <button data-id="${s.id}" type="button">删除</button>
        </div>`;
      box.appendChild(div);
    }
    box.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!confirm("删除该样本？")) return;
        await fetch(`/api/faces/${btn.getAttribute("data-id")}`, { method: "DELETE" });
        this.load();
      });
    });
  },

  async save(e) {
    e.preventDefault();
    const body = this.fieldsFromForm();
    if (!this.personId) {
      body.phone = document.getElementById("phone").value.trim();
      const res = await fetch("/api/people", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) {
        alert(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
        return;
      }
      location.href = `/admin/people/${data.id}`;
      return;
    }
    body.status = document.getElementById("status").value;
    const res = await fetch(`/api/people/${this.personId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const data = await res.json();
      alert(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
      return;
    }
    alert("已保存");
    this.load();
  },

  async upload() {
    const fileInput = document.getElementById("faceFile");
    const msg = document.getElementById("uploadMsg");
    msg.textContent = "";
    msg.style.color = "";
    if (!fileInput.files.length) {
      msg.textContent = "请选择图片";
      return;
    }
    const fd = new FormData();
    fd.append("file", fileInput.files[0]);
    const res = await fetch(`/api/people/${this.personId}/faces`, { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) {
      const d = data.detail;
      msg.textContent = typeof d === "string" ? d : d.message || JSON.stringify(d);
      return;
    }
    fileInput.value = "";
    msg.textContent = "上传成功";
    msg.style.color = "#0b6e4f";
    this.load();
  },
};

const AdminLogs = {
  async init() {
    document.getElementById("btnReload").addEventListener("click", () => this.load());
    this.load();
  },
  async load() {
    const matched = document.getElementById("matchedFilter").value;
    const phone = document.getElementById("phoneFilter").value.trim();
    const params = new URLSearchParams({ limit: "100" });
    if (matched) params.set("matched", matched);
    if (phone) params.set("phone", phone);
    const data = await fetch("/api/logs?" + params.toString()).then((r) => r.json());
    const tbody = document.querySelector("#logsTable tbody");
    tbody.innerHTML = "";
    for (const r of data.items) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(r.created_at || "")}</td>
        <td>${escapeHtml(r.device_label || "")}</td>
        <td>${r.matched ? "命中" : "未命中"}</td>
        <td>${escapeHtml((r.person_name || "") + " " + (r.phone || ""))}</td>
        <td>${Number(r.score).toFixed(3)}</td>
        <td>${Number(r.second_score).toFixed(3)}</td>
        <td>${escapeHtml(r.error_code || "")}</td>`;
      tbody.appendChild(tr);
    }
  },
};

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(s) {
  return escapeHtml(s).replace(/'/g, "&#39;");
}
