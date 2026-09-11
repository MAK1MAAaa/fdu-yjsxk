"""从已登录浏览器只读采集课程表，导出待人工审核的配置条目。"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import re
import time
import tempfile

from .settings import BASE_DIR

CATEGORIES = {
    "政治理论课": ("7", "1"), "第一外国语": ("7", "2"),
    "专业外语": ("7", "3"), "学位基础课": ("8", "4"),
    "学位专业课": ("8", "5"), "专业选修课": ("8", "6"),
}
CLASS_CODE = re.compile(r"\d{10}[A-Za-z]+\d+\.\d+")


def parse_rows(rows: list[dict], category: str = "") -> tuple[list[dict], list[dict]]:
    courses, unresolved = [], []
    for row in rows:
        cells = row.get("cells", [])
        match = CLASS_CODE.search(row.get("code", "") or " ".join(cells))
        if not match:
            continue
        code = match.group()
        title = next((cell.replace(code, "").strip() for cell in cells if code in cell), code)
        kind = next((cell for cell in cells if cell in CATEGORIES), category)
        record = {"name": title, "kcdm": code[10:].split(".")[0], "bjdm": code,
                  "enabled": False, "_页面列": cells, "_分类": kind}
        if kind in CATEGORIES:
            record["lx"], record["bqmc"] = CATEGORIES[kind]
            courses.append(record)
        else:
            record["_待核对"] = "页面未提供可识别分类，不能确定 lx / bqmc"
            unresolved.append(record)
    return courses, unresolved


def collect(driver) -> dict:
    """读取已核实的两级分类表格，不点击任何选退课控件。"""
    from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    wait = WebDriverWait(driver, 15, ignored_exceptions=(StaleElementReferenceException,))
    result = {"captured_at": dt.datetime.now().isoformat(timespec="seconds"),
              "courses": [], "unresolved": [], "notes": [], "categories": [],
              "scope": "学位公共课和学科专业课六个子分类；不含公选、重修及其他分类"}
    seen = set()
    active_parent = None
    for category, (parent, tab) in CATEGORIES.items():
        prefix = "ggkc" if parent == "7" else "xwzyk"
        try:
            if active_parent != parent:
                wait.until(EC.element_to_be_clickable(("css selector", f"#xkkctab_{parent}"))).click()
                active_parent = parent
            selector = f"#{prefix}_tab_container li[tabwid='{tab}']"
            wait.until(EC.element_to_be_clickable(("css selector", selector))).click()
            grid_selector = f"#grid_{prefix}_{tab}"
            wait.until(lambda d: d.execute_script("""
                const grid = document.querySelector(arguments[0]);
                return grid && grid.getClientRects().length &&
                  grid.querySelector('tbody') &&
                  !grid.innerText.includes('正在加载') &&
                  (!window.jQuery || window.jQuery.active === 0);
            """, grid_selector))
            rows = driver.execute_script("""
                return Array.from(document.querySelectorAll(arguments[0] + ' tr[role-tr]')).map(r => ({
                  cells: Array.from(r.querySelectorAll('td')).map(c => c.innerText.trim()),
                  code: r.querySelector('[role="xk"]')?.getAttribute('role-val') || ''
                }));
            """, grid_selector)
            valid, unknown = parse_rows(rows, category)
            for key, records in (("courses", valid), ("unresolved", unknown)):
                for record in records:
                    # 分类来自实际点击的标签，不能由表格课程类别覆盖其提交参数。
                    record["lx"], record["bqmc"] = parent, tab
                    record["_分类"] = category
                    identity = (record["bjdm"], parent, tab)
                    if identity not in seen:
                        result[key].append(record)
                        seen.add(identity)
            result["categories"].append({"name": category, "count": len(rows), "status": "loaded"})
            if not rows:
                result["notes"].append(f"{category}：页面无课程行，可能无课程或学分要求已满足")
            print(f"已读取 {category}：{len(rows)} 个教学班。", flush=True)
            time.sleep(0.5)
        except TimeoutException:
            result["categories"].append({"name": category, "status": "unavailable"})
            result["notes"].append(f"{category}：分类不可见或加载超时，未采集")
            active_parent = None
    return result


def write_json_atomic(path: Path, data: dict) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".catalog-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def export_catalog(driver) -> Path:
    result = collect(driver)
    if not result["courses"] and not result["unresolved"]:
        raise ValueError("未识别到课程表，请在登录后进入课程列表页再尝试")
    folder = Path(BASE_DIR) / "exports"
    folder.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = folder / "course-list.json"
    candidate = folder / f"config-courses-{stamp}.json"
    with candidate.open("x", encoding="utf-8") as stream:
        json.dump({"courses": result["courses"]}, stream, ensure_ascii=False, indent=2)
    write_json_atomic(path, result)
    print("课程列表已更新；本地课程浏览页会自动读取新 JSON，无需重新生成 HTML。")
    print(f"课程导出：{path.name}；可核对条目 {len(result['courses'])}，分类待确认 {len(result['unresolved'])}。")
    print(f"配置候选：{candidate.name}（非完整配置，全部禁用，未覆盖 config.json）。")
    for note in result["notes"]:
        print(note)
    return path
