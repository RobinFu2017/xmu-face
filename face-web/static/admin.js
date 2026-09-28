/** 管理后台页面脚本：人员列表 / 详情上传 / 日志。 */
const AdminPeople = {
  async init() {
    document.getElementById("btnSearch").addEventListener("click", () => this.load());
    await this.load();
    const stats = await fetch("/api/stats").then((r) => r.json());
    document.getElementById("statsLine").textContent =
      `人员 ${stats.person_count} · 样本 ${stats.sample_count} · 索引 ${stats.index_size} · 阈值 ${stats.match_threshold}`;
  },

  async load() {
    const q = document.getElementById("searchQ").value.trim();
    const status = document.getElementById("statusFilter").value;
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (status) params.set("status", status);
    const data = await fetch("/api/people?" + params.toString()).then((r) => r.json());
    const tbody = document.querySelector("#peopleTable tbody");
    tbody.innerHTML = "";
    for (const p of data.items) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(p.employee_no)}</td>
        <td><a href="/admin/people/${p.id}">${escapeHtml(p.name)}</a></td>
        <td>${escapeHtml(p.department || "")}</td>
        <td>${p.sample_count}</td>
        <td>${p.status}</td>
        <td>
          <button data-id="${p.id}" data-act="toggle" type="button">${p.status === "active" ? "停用" : "启用"}</button>
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

  async load() {
    const p = await fetch(`/api/people/${this.personId}`).then((r) => r.json());
    document.getElementById("employee_no").value = p.employee_no;
    document.getElementById("name").value = p.name;
    document.getElementById("department").value = p.department || "";
    document.getElementById("status").value = p.status;
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
    const name = document.getElementById("name").value.trim();
    const department = document.getElementById("department").value.trim();
    if (!this.personId) {
      const employee_no = document.getElementById("employee_no").value.trim();
      const res = await fetch("/api/people", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ employee_no, name, department }),
      });
      const data = await res.json();
      if (!res.ok) {
        alert(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
        return;
      }
      location.href = `/admin/people/${data.id}`;
      return;
    }
    const status = document.getElementById("status").value;
    const res = await fetch(`/api/people/${this.personId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, department, status }),
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
    const employee_no = document.getElementById("empFilter").value.trim();
    const params = new URLSearchParams({ limit: "100" });
    if (matched) params.set("matched", matched);
    if (employee_no) params.set("employee_no", employee_no);
    const data = await fetch("/api/logs?" + params.toString()).then((r) => r.json());
    const tbody = document.querySelector("#logsTable tbody");
    tbody.innerHTML = "";
    for (const r of data.items) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(r.created_at || "")}</td>
        <td>${escapeHtml(r.device_label || "")}</td>
        <td>${r.matched ? "命中" : "未命中"}</td>
        <td>${escapeHtml((r.employee_no || "") + " " + (r.person_name || ""))}</td>
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
