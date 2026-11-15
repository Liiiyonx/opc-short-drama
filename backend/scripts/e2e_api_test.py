"""API 级端到端冒烟测试（GUI 测试受阻时的补充验证）。

覆盖三端全部业务闭环：发布→提交→批改→能力分、发单→审核→投标→定标、管理端 CRUD。
用法：cd backend && python -m scripts.e2e_api_test
注意：会真实调用 LLM/TTS/ffmpeg（真实模式约 0.05-0.1 元），创建 gui_e2e_* 前缀测试数据。
"""
import os
import sys
import time

import httpx

BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000/api/v1")
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"{'✓' if ok else '✗'} {name}" + (f" —— {detail}" if detail and not ok else ""))


class Client:
    def __init__(self, token=None):
        self.http = httpx.Client(base_url=BASE, timeout=180)
        if token:
            self.http.headers["Authorization"] = f"Bearer {token}"

    def call(self, method, path, expected=200, **kw):
        resp = self.http.request(method, path, **kw)
        body = resp.json()
        code = body.get("code", 0)
        # 200 要求业务码为 0；非 200（如 409/403）只要求 HTTP 状态匹配（错误码必然非 0）
        ok = resp.status_code == expected and (expected != 200 or code == 0)
        return ok, body.get("data") if code == 0 else body.get("message"), resp.status_code, body


def login(username, password):
    c = Client()
    ok, data, status, _ = c.call("POST", "/auth/login", json={"username": username, "password": password})
    if not ok:
        print(f"✗ 登录失败 {username}: {data}")
        sys.exit(1)
    print(f"✓ 登录 {username}（{data['user']['role']}）")
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


def poll_visibility_and_note():
    """API 测试期间检测浏览器面板是否回到前台（供上层恢复 GUI 测试）。"""
    try:
        import json
        import urllib.request

        req = urllib.request.Request("http://127.0.0.1:5199/", method="GET")
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass


def main():
    stamp = str(int(time.time()))[-6:]

    # ---------- 教师端 ----------
    teacher, t_user = login("teacher01", "teacher123")

    # T1.4 补充：发布任务（API 层）
    ok, task, _, _ = teacher.call("POST", "/tasks", json={
        "title": f"API E2E 任务 {stamp}",
        "brief": "API 级端到端测试任务",
        "team_rule": "free",
        "rubric": {
            "criteria": [
                {"key": "quality", "name": "剧本与内容质量", "dimension": "内容创作", "weight": 1}
            ],
            "pass_score": 60
        }
    })
    check("教师发布任务", ok, str(task))
    task_id = task["id"] if ok else None

    # T1.5 补充：工单审核（通过 + 驳回）
    ok, orders, _, _ = teacher.call("GET", "/orders")
    items = (orders or {}).get("items", []) if isinstance(orders, dict) else []
    pending = [o for o in items if o["status"] == "pending_review"]
    if len(pending) >= 2:
        ok1, _, s1, b1 = teacher.call("POST", f"/orders/{pending[0]['id']}/verify", json={"approved": True, "note": "E2E 通过"})
        check("教师审核-通过工单", ok1 and s1 == 200, str(b1))
        ok2, _, s2, b2 = teacher.call("POST", f"/orders/{pending[1]['id']}/verify", json={"approved": False, "note": "E2E 驳回"})
        check("教师审核-驳回工单", ok2 and s2 == 200, str(b2))
        ok3, od, _, _ = teacher.call("GET", f"/orders/{pending[1]['id']}")
        check("驳回后状态回 draft", ok3 and od["order"]["status"] == "draft", str(od and od["order"]["status"]))
        published_order = pending[0]["id"]
    else:
        check("工单审核", False, f"待审核工单不足 2 张（{len(pending)}）")
        published_order = None

    # ---------- 学生端 ----------
    student, s_user = login("student01", "student123")

    # T2 守卫：学生调用教师权限接口应 403
    ok, _, status, _ = student.call("POST", "/tasks", expected=403, json={"title": "x"})
    check("权限守卫-学生发布任务被拒(403)", ok, f"status={status}")

    # T2.2 创建剧集 + 全链路（真实 AI）
    ok, work, _, _ = student.call("POST", "/works", json={"title": f"API E2E 剧 {stamp}", "type": "script"})
    check("学生创建剧本作品", ok, str(work))
    script_id = work["id"]

    t0 = time.time()
    ok, gen, _, body = student.call("POST", f"/works/{script_id}/generate", json={
        "genre": "逆袭", "target_market": "北美", "episodes": 2, "episode_minutes": 2
    })
    check("剧本生成（真实 LLM）", ok and gen["work"]["status"] == "ready", str(body)[:200])
    print(f"    剧本耗时 {time.time()-t0:.1f}s")

    ok, sb, _, body = student.call("POST", f"/works/{script_id}/generate-sb", expected=404) if False else (True, None, 0, None)
    # 分镜
    ok, sb_work, _, _ = student.call("POST", "/works", json={"title": f"API E2E 剧 {stamp}-分镜", "type": "storyboard"})
    sb_id = sb_work["id"]
    t0 = time.time()
    ok, gen, _, body = student.call("POST", f"/works/{sb_id}/generate", json={"source_work_id": script_id, "episode": 1})
    check("分镜生成（真实 LLM）", ok and gen["work"]["status"] == "ready", str(body)[:200])
    print(f"    分镜耗时 {time.time()-t0:.1f}s")

    # 翻译本地化
    ok, tr_work, _, _ = student.call("POST", "/works", json={"title": f"API E2E 剧 {stamp}-翻译", "type": "translate"})
    tr_id = tr_work["id"]
    t0 = time.time()
    ok, gen, _, body = student.call("POST", f"/works/{tr_id}/generate", json={"storyboard_work_id": sb_id})
    check("翻译本地化（真实 LLM）", ok and gen["work"]["status"] == "ready", str(body)[:200])
    print(f"    翻译耗时 {time.time()-t0:.1f}s")

    # 配音（异步 worker + 真实 Edge-TTS）
    ok, au_work, _, _ = student.call("POST", "/works", json={"title": f"API E2E 剧 {stamp}-配音", "type": "audio"})
    au_id = au_work["id"]
    ok, gen, _, body = student.call("POST", f"/works/{au_id}/generate", json={"storyboard_work_id": sb_id})
    async_ok = ok and gen.get("async")
    check("配音任务入队（异步）", async_ok, str(body)[:200])
    if async_ok:
        status, data = wait_task(student, gen["session_id"])
        check("配音完成（真实 Edge-TTS worker）", status == "success", f"status={status}")
        ok, detail, _, _ = student.call("GET", f"/works/{au_id}")
        audio_assets = [a for a in (detail or {}).get("assets", []) if a["kind"] in ("audio", "audio_merged")]
        check("配音产物落库（音频+SRT）", len(audio_assets) >= 2, f"{len(audio_assets)} 个音频资产")

    # 字幕
    ok, st_work, _, _ = student.call("POST", "/works", json={"title": f"API E2E 剧 {stamp}-字幕", "type": "subtitle"})
    st_id = st_work["id"]
    ok, gen, _, body = student.call("POST", f"/works/{st_id}/generate", json={"audio_work_id": au_id})
    check("字幕生成（SRT 复制）", ok and gen["work"]["status"] == "ready", str(body)[:200])

    # 成片（异步 ffmpeg）
    ok, vd_work, _, _ = student.call("POST", "/works", json={"title": f"API E2E 剧 {stamp}-成片", "type": "video"})
    vd_id = vd_work["id"]
    ok, gen, _, body = student.call("POST", f"/works/{vd_id}/generate", json={
        "storyboard_work_id": sb_id, "audio_work_id": au_id
    })
    async_ok = ok and gen.get("async")
    check("成片任务入队（异步）", async_ok, str(body)[:200])
    if async_ok:
        status, data = wait_task(student, gen["session_id"], timeout=300)
        check("成片合成完成（真实 ffmpeg worker）", status == "success", f"status={status}")

    # 发布参数
    t0 = time.time()
    ok, gen, _, body = student.call("POST", f"/works/{vd_id}/publish-params", json={"source_work_id": script_id})
    check("发布参数生成（真实 LLM）", ok, str(body)[:200])
    print(f"    发布参数耗时 {time.time()-t0:.1f}s")

    # AI 使用声明
    ok, _, _, _ = student.call("POST", f"/works/{vd_id}/ai-declare", json={
        "agents_used": ["script", "storyboard", "tts", "compose"], "human_edit_ratio": 0.25
    })
    check("AI 使用声明保存", ok)

    # 提交作品到实训任务
    ok, _, _, body = student.call("POST", f"/tasks/{task_id}/submit", json={
        "work_ids": [script_id, sb_id, vd_id], "note": "API E2E 提交"
    })
    check("学生提交作品到任务", ok, str(body)[:200])

    # 工单投标
    if published_order:
        ok, _, status, body = student.call("POST", f"/orders/{published_order}/bid", json={
            "amount_cents": 250000, "proposal": "API E2E 投标：3 天交付，含双语字幕"
        })
        check("学生投标工单", ok and status == 200, str(body)[:150])
        ok, _, status, body = student.call("POST", f"/orders/{published_order}/bid", json={
            "amount_cents": 250000, "proposal": "重复投标"
        })
        check("重复投标被拒(409)", ok and status == 409, f"status={status}")

    # ---------- 教师批改（T6 闭环） ----------
    ok, _, _, body = teacher.call("POST", f"/works/{script_id}/review", json={
        "criterion_scores": [{"key": "quality", "score": 88}],
        "comment": "API E2E 批改：结构完整，钩子有力"
    })
    check("教师 Rubric 批改", ok, str(body)[:200])

    ok, ab, _, _ = student.call("GET", f"/ability/students/{s_user['id']}")
    latest = (ab or {}).get("latest", {})
    check("批改后能力分更新（内容创作）", ok and latest.get("内容创作", 0) >= 80, str(latest))

    # 教师截止任务（API E2E 任务）
    ok, _, _, _ = teacher.call("POST", f"/tasks/{task_id}/close")
    check("教师截止任务", ok)

    # ---------- 企业端 ----------
    ent, _ = login("enterprise01", "ent123456")
    ok, my_order, _, body = ent.call("POST", "/orders", json={
        "title": f"API E2E 工单 {stamp}",
        "requirements": {"genre": "逆袭", "market": "北美", "episodes": 2, "lang": "en-US", "delivery": "3 天"},
        "budget_cents": 300000,
        "submit": True
    })
    check("企业发布工单（送审）", ok and my_order["status"] == "pending_review", str(body)[:200])

    ok, _, _, _ = teacher.call("POST", f"/orders/{my_order['id']}/verify", json={"approved": True, "note": "E2E"})
    check("教师审核企业新工单", ok)
    ok, od, _, _ = ent.call("GET", f"/orders/{published_order}") if published_order else (False, None, 0, None)
    bids = (od or {}).get("bids", [])
    check("企业查看投标列表", ok and len(bids) >= 1, f"{len(bids)} 条")

    if published_order and bids:
        ok, _, status, body = ent.call("POST", f"/orders/{published_order}/award", json={"bid_id": bids[0]["id"]})
        check("企业定标", ok and status == 200, str(body)[:150])
        ok, od2, _, _ = ent.call("GET", f"/orders/{published_order}")
        check("定标后状态 awarded", ok and od2["order"]["status"] == "awarded", str(od2 and od2["order"]["status"]))

    # ---------- 管理端 ----------
    admin, _ = login("admin", "admin123")
    uname = f"gui_e2e_stu_{stamp}"
    ok, nu, _, body = admin.call("POST", "/users", json={
        "username": uname, "password": "e2e12345", "role": "student", "major": "电子商务", "grade": "2024"
    })
    check("管理员创建用户", ok, str(body)[:150])
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

    code = f"GE{stamp}"
    ok, _, _, _ = admin.call("POST", "/courses", json={"code": code, "name": "API E2E 课程", "classes": ["一班"]})
    check("管理员创建课程", ok)
    ok, _, status, _ = admin.call("POST", "/courses", expected=409, json={"code": code, "name": "重复课程"})
    check("重复课程代码被拒(409)", ok and status == 409, f"status={status}")

    # ---------- 汇总 ----------
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n========== E2E 结果：{passed}/{len(RESULTS)} 通过 ==========")
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"  ✗ {name} {detail}")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
