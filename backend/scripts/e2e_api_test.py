"""API 级端到端冒烟测试（P0-06 可重复版）。

设计原则（对应 docs/08 P0-06）：
- 独立夹具：e2e 专用教师/学生/企业账号由管理员建号（409 = 已存在则复用），
  不依赖 seed 预置数据、不依赖数据库里恰好有待审核工单；
- 自建数据：任务/工单/作品全部本次运行创建，带唯一时间戳，可连续重复执行；
- UTF-8 安全：输出仅用 ASCII 标记（[OK]/[FAIL]），Windows 控制台不因 ✓ 崩溃；
- 一次失败保留现场：失败项打印 API 返回体（含 request 定位线索）。

用法：cd backend && python -m scripts.e2e_api_test
依赖：API 已在 127.0.0.1:8000 运行（真实或 mock provider 均可）。
真实模式会真实调用 LLM/TTS/ffmpeg（约 0.05-0.1 元）；数据带 e2e_ 前缀。
"""
import os
import sys
import time

try:
    # Windows 控制台 UTF-8 兜底（部分终端仍以 GBK 运行）
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    pass

import httpx

BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000/api/v1")
RESULTS = []

FIXTURE_PASSWORD = "e2ePass123"


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"[{'OK' if ok else 'FAIL'}] {name}" + (f" —— {detail}" if detail and not ok else ""))


class Client:
    def __init__(self, token=None):
        self.http = httpx.Client(base_url=BASE, timeout=180)
        if token:
            self.http.headers["Authorization"] = f"Bearer {token}"

    def call(self, method, path, expected=200, **kw):
        resp = self.http.request(method, path, **kw)
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001
            return resp.status_code == expected, None, resp.status_code, {}
        code = body.get("code", 0)
        ok = resp.status_code == expected and (expected != 200 or code == 0)
        return ok, body.get("data") if code == 0 else body.get("message"), resp.status_code, body


def login(username, password):
    c = Client()
    ok, data, status, body = c.call(
        "POST", "/auth/login", json={"username": username, "password": password}
    )
    if not ok:
        print(f"[FAIL] 登录 {username}: {data}（HTTP {status}）")
        sys.exit(1)
    print(f"[OK] 登录 {username}（{data['user']['role']}）")
    return Client(data["access_token"]), data["user"]


def wait_task(client, session_id, timeout=180):
    """轮询异步智能体任务直到 success/failed。"""
    start = time.time()
    while time.time() - start < timeout:
        ok, data, _, _ = client.call("GET", f"/agent-tasks/{session_id}")
        if ok and data["status"] in ("success", "failed"):
            return data["status"], data
        time.sleep(3)
    return "timeout", {}


def bootstrap_fixtures(admin):
    """P0-06 独立夹具：管理员创建 e2e 专属三角色账号（幂等，已存在则复用）。

    P0-02 之后教师/企业不能自助注册，管理员建号的企业自带已认证档案。
    """
    specs = [
        {"username": "e2e_teacher", "role": "teacher", "college": "经济贸易学院", "title": "讲师"},
        {"username": "e2e_student", "role": "student", "major": "电子商务", "grade": "2025"},
        {"username": "e2e_enterprise", "role": "enterprise", "company_name": "E2E 出海测试公司"},
    ]
    for spec in specs:
        payload = {"username": spec["username"], "password": FIXTURE_PASSWORD, "role": spec["role"]}
        payload.update({k: v for k, v in spec.items() if k not in ("username", "role")})
        ok, _, status, body = admin.call("POST", "/users", json=payload, expected=None)
        if status == 200:
            print(f"[OK] 夹具创建 {spec['username']}（{spec['role']}）")
        elif status == 409:
            print(f"[OK] 夹具复用 {spec['username']}（已存在）")
        else:
            print(f"[FAIL] 夹具创建 {spec['username']}: HTTP {status} {str(body)[:150]}")
            sys.exit(1)


def main():
    stamp = str(int(time.time()))[-6:]

    # ---------- 管理员 + 独立夹具 ----------
    admin, _ = login("admin", "admin123")
    bootstrap_fixtures(admin)

    # ---------- 教师端（全部使用本次自建数据） ----------
    teacher, t_user = login("e2e_teacher", FIXTURE_PASSWORD)

    ok, task, _, body = teacher.call("POST", "/tasks", json={
        "title": f"E2E 任务 {stamp}",
        "brief": "API 级端到端测试任务（自建数据）",
        "team_rule": "free",
        "rubric": {
            "criteria": [
                {"key": "quality", "name": "剧本与内容质量", "dimension": "内容创作", "weight": 1}
            ],
            "pass_score": 60
        }
    })
    check("教师发布任务", ok, str(body)[:200])
    task_id = task["id"] if ok else None

    # ---------- 学生端 ----------
    student, s_user = login("e2e_student", FIXTURE_PASSWORD)

    # 权限守卫：学生调用教师权限接口应 403
    ok, _, status, _ = student.call("POST", "/tasks", expected=403, json={"title": "x"})
    check("权限守卫-学生发布任务被拒(403)", ok, f"status={status}")

    # 注册红线：教师/企业身份不能自助获取（P0-02）
    ok, _, status, _ = student.call("POST", "/auth/register", expected=403, json={
        "username": f"e2e_hack_{stamp}", "password": "hack12345", "role": "teacher"
    })
    check("注册红线-教师身份自助注册被拒(403)", ok, f"status={status}")

    # 剧集全链路（provider 取决于服务器：mock 快速 / 真实计费）
    ok, work, _, body = student.call("POST", "/works", json={"title": f"E2E 剧 {stamp}", "type": "script"})
    check("学生创建剧本作品", ok, str(body)[:200])
    script_id = work["id"]

    t0 = time.time()
    ok, gen, _, body = student.call("POST", f"/works/{script_id}/generate", json={
        "genre": "逆袭", "target_market": "北美", "episodes": 2, "episode_minutes": 2
    })
    check("剧本生成", ok and gen["work"]["status"] == "ready", str(body)[:200])
    print(f"    剧本耗时 {time.time()-t0:.1f}s")

    ok, sb_work, _, _ = student.call("POST", "/works", json={"title": f"E2E 剧 {stamp}-分镜", "type": "storyboard"})
    sb_id = sb_work["id"]
    t0 = time.time()
    ok, gen, _, body = student.call("POST", f"/works/{sb_id}/generate", json={"source_work_id": script_id, "episode": 1})
    check("分镜生成", ok and gen["work"]["status"] == "ready", str(body)[:200])
    print(f"    分镜耗时 {time.time()-t0:.1f}s")

    ok, tr_work, _, _ = student.call("POST", "/works", json={"title": f"E2E 剧 {stamp}-翻译", "type": "translate"})
    tr_id = tr_work["id"]
    ok, gen, _, body = student.call("POST", f"/works/{tr_id}/generate", json={"storyboard_work_id": sb_id})
    check("翻译本地化", ok and gen["work"]["status"] == "ready", str(body)[:200])

    # 配音（异步 worker）
    ok, au_work, _, body = student.call("POST", "/works", json={"title": f"E2E 剧 {stamp}-配音", "type": "audio"})
    au_id = au_work["id"]
    ok, gen, _, body = student.call("POST", f"/works/{au_id}/generate", json={"storyboard_work_id": sb_id})
    async_ok = ok and gen.get("async")
    check("配音任务入队（异步）", async_ok, str(body)[:200])
    if async_ok:
        status, _data = wait_task(student, gen["session_id"])
        check("配音完成（worker）", status == "success", f"status={status}")
        ok, detail, _, _ = student.call("GET", f"/works/{au_id}")
        audio_assets = [a for a in (detail or {}).get("assets", []) if a["kind"] in ("audio", "audio_merged")]
        check("配音产物落库（音频+SRT）", len(audio_assets) >= 2, f"{len(audio_assets)} 个音频资产")

    # 字幕
    ok, st_work, _, _ = student.call("POST", "/works", json={"title": f"E2E 剧 {stamp}-字幕", "type": "subtitle"})
    st_id = st_work["id"]
    ok, gen, _, body = student.call("POST", f"/works/{st_id}/generate", json={"audio_work_id": au_id})
    check("字幕生成（SRT 复制）", ok and gen["work"]["status"] == "ready", str(body)[:200])

    # 成片（异步 ffmpeg + P0-08 质检）
    ok, vd_work, _, _ = student.call("POST", "/works", json={"title": f"E2E 剧 {stamp}-成片", "type": "video"})
    vd_id = vd_work["id"]
    ok, gen, _, body = student.call("POST", f"/works/{vd_id}/generate", json={
        "storyboard_work_id": sb_id, "audio_work_id": au_id
    })
    async_ok = ok and gen.get("async")
    check("成片任务入队（异步）", async_ok, str(body)[:200])
    if async_ok:
        status, data = wait_task(student, gen["session_id"], timeout=300)
        check("成片合成完成（worker）", status == "success", f"status={status}")
        # P0-08：无上传图片 → 演示帧路径，质检应通过（非纯色、有音轨）
        result = (data or {}).get("result") if isinstance(data, dict) else None
        qc = (result or {}).get("qc") if isinstance(result, dict) else None
        if qc:
            check("成片质检闸门通过（非纯色/有音轨）", qc.get("pass") is True, str(qc.get("issues"))[:200])
        else:
            check("成片质检报告存在", False, "result.qc 缺失（P0-08）")

    # 发布参数
    t0 = time.time()
    ok, gen, _, body = student.call("POST", f"/works/{vd_id}/publish-params", json={"source_work_id": script_id})
    check("发布参数生成", ok, str(body)[:200])
    print(f"    发布参数耗时 {time.time()-t0:.1f}s")

    # AI 使用声明
    ok, _, _, _ = student.call("POST", f"/works/{vd_id}/ai-declare", json={
        "agents_used": ["script", "storyboard", "tts", "compose"], "human_edit_ratio": 0.25
    })
    check("AI 使用声明保存", ok)

    # 提交作品到实训任务
    ok, _, _, body = student.call("POST", f"/tasks/{task_id}/submit", json={
        "work_ids": [script_id, sb_id, vd_id], "note": "E2E 提交"
    })
    check("学生提交作品到任务", ok, str(body)[:200])

    # ---------- 工单闭环（本次自建工单，不依赖预置数据） ----------
    ok, _, status, body = student.call("POST", "/orders", expected=403, json={
        "title": f"E2E 工单 {stamp}", "requirements": {
            "genre": "逆袭", "market": "北美", "episodes": 2, "lang": "en-US", "delivery": "3 天"
        },
        "budget_cents": 300000, "submit": True
    })
    check("学生不能发布工单(403)", ok, f"status={status}")
    ok, my_order, _, body = _create_order_as_enterprise(stamp)
    published_order = my_order["id"] if ok else None

    if published_order:
        ok, _, _, body = teacher.call("POST", f"/orders/{published_order}/verify", json={"approved": True, "note": "E2E"})
        check("教师审核工单通过", ok, str(body)[:150])
        ok, _, status, body = student.call("POST", f"/orders/{published_order}/bid", json={
            "amount_cents": 250000, "proposal": "E2E 投标：3 天交付，含双语字幕"
        })
        check("学生投标工单", ok and status == 200, str(body)[:150])
        ok, _, status, body = student.call("POST", f"/orders/{published_order}/bid", expected=409, json={
            "amount_cents": 250000, "proposal": "重复投标"
        })
        check("重复投标被拒(409)", ok, f"status={status}")

    # ---------- 教师批改（闭环） ----------
    ok, _, _, body = teacher.call("POST", f"/works/{script_id}/review", json={
        "criterion_scores": [{"key": "quality", "score": 88}],
        "comment": "E2E 批改：结构完整，钩子有力"
    })
    check("教师 Rubric 批改", ok, str(body)[:200])

    ok, ab, _, _ = student.call("GET", f"/ability/students/{s_user['id']}")
    latest = (ab or {}).get("latest", {})
    check("批改后能力分更新（内容创作）", ok and latest.get("内容创作", 0) >= 80, str(latest))

    ok, _, _, _ = teacher.call("POST", f"/tasks/{task_id}/close")
    check("教师截止任务", ok)

    # ---------- 企业端 ----------
    ent, _ = login("e2e_enterprise", FIXTURE_PASSWORD)
    ok, od, _, _ = ent.call("GET", f"/orders/{published_order}") if published_order else (False, None, 0, None)
    bids = (od or {}).get("bids", [])
    check("企业查看投标列表", ok and len(bids) >= 1, f"{len(bids)} 条")
    if published_order and bids:
        ok, _, status, body = ent.call("POST", f"/orders/{published_order}/award", json={"bid_id": bids[0]["id"]})
        check("企业定标", ok and status == 200, str(body)[:150])
        ok, od2, _, _ = ent.call("GET", f"/orders/{published_order}")
        check("定标后状态 awarded", ok and od2["order"]["status"] == "awarded", str(od2 and od2["order"]["status"]))

    # ---------- 管理端 CRUD（唯一命名，可重复） ----------
    uname = f"e2e_stu_{stamp}"
    ok, nu, _, body = admin.call("POST", "/users", json={
        "username": uname, "password": "e2e12345", "role": "student", "major": "电子商务", "grade": "2024"
    })
    check("管理员创建用户（含档案）", ok, str(body)[:150])
    ok, _, status, body = admin.call("POST", "/users", expected=409, json={
        "username": uname, "password": "e2e12345", "role": "student"
    })
    check("重复用户名被拒(409)", ok and status == 409, f"status={status}")
    uid = nu["id"]
    ok, _, _, _ = admin.call("PATCH", f"/users/{uid}/status", json={"status": 0})
    check("管理员禁用用户", ok)
    c2 = Client()
    ok, _, status, _ = c2.call("POST", "/auth/login", expected=403, json={"username": uname, "password": "e2e12345"})
    check("被禁用户登录被拒(403)", ok, f"status={status}")
    ok, _, _, _ = admin.call("PATCH", f"/users/{uid}/status", json={"status": 1})
    check("管理员启用用户", ok)

    code = f"E2E{stamp}"
    ok, _, _, _ = admin.call("POST", "/courses", json={"code": code, "name": "E2E 课程", "classes": ["一班"]})
    check("管理员创建课程", ok)
    ok, _, status, _ = admin.call("POST", "/courses", expected=409, json={"code": code, "name": "重复课程"})
    check("重复课程代码被拒(409)", ok and status == 409, f"status={status}")

    # ---------- 健康检查三档（P0-01，演示闸门同款口径） ----------
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=10) as hc:
        live = hc.get("/livez")
        ready = hc.get("/readyz")
        deep = hc.get("/health")
        check("/livez 存活探针", live.status_code == 200, f"HTTP {live.status_code}")
        check("/readyz 就绪探针", ready.status_code == 200, f"HTTP {ready.status_code} {ready.text[:120]}")
        deep_data = deep.json().get("data", {})
        check(
            "/health 全量诊断字段齐全",
            all(k in deep_data for k in ("db", "redis", "worker", "storage", "ffmpeg", "ai")),
            str(list(deep_data.keys())),
        )

    # ---------- 汇总 ----------
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n========== E2E 结果：{passed}/{len(RESULTS)} 通过 ==========")
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"  [FAIL] {name} {detail}")
    return 0 if passed == len(RESULTS) else 1


def _create_order_as_enterprise(stamp):
    """企业账号发布工单并送审（自建数据，可重复执行）。"""
    ent, _ = login("e2e_enterprise", FIXTURE_PASSWORD)
    ok, order, _, body = ent.call("POST", "/orders", json={
        "title": f"E2E 工单 {stamp}",
        "requirements": {"genre": "逆袭", "market": "北美", "episodes": 2, "lang": "en-US", "delivery": "3 天"},
        "budget_cents": 300000,
        "submit": True,
    })
    check("企业发布工单（送审）", ok and (order or {}).get("status") == "pending_review", str(body)[:200])
    return ok, (order or {}), 200, body


if __name__ == "__main__":
    sys.exit(main())
