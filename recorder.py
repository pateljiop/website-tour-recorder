from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from playwright.async_api import async_playwright, Page, Locator, TimeoutError as PlaywrightTimeoutError

LOG = logging.getLogger("tour-recorder")


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def make_url(base: str, route: str | None = None) -> str:
    if not route:
        return base.rstrip("/") + "/"
    if route.startswith(("https://", "http://")):
        return route
    return base.rstrip("/") + "/" + route.lstrip("/")


async def ready(page: Page, cfg: dict[str, Any]) -> None:
    timing = cfg.get("timing", {})
    timeout = int(timing.get("network_idle_timeout_ms", 10000))
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=timeout)
    except PlaywrightTimeoutError:
        pass
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout)
    except PlaywrightTimeoutError:
        LOG.info("Network stayed active; continuing after timeout.")
    settle = int(timing.get("animation_settle_timeout_ms", 4000))
    try:
        await page.evaluate("""async (ms) => {
          const cap = new Promise(r => setTimeout(r, ms));
          const work = (async () => {
            if (document.fonts?.ready) await Promise.race([document.fonts.ready, new Promise(r=>setTimeout(r,2000))]);
            const a = document.getAnimations({subtree:true}).filter(x => x.playState === 'running' && x.effect && x.effect.getTiming().iterations !== Infinity);
            await Promise.race([Promise.allSettled(a.map(x=>x.finished)), new Promise(r=>setTimeout(r,ms))]);
            await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
          })();
          await Promise.race([work, cap]);
        }""", settle)
    except Exception as e:
        LOG.debug("Animation wait skipped: %s", e)


async def smooth_mouse(page: Page, x: float, y: float, duration_ms: int = 450) -> None:
    start = await page.evaluate("() => window.__tourMouse || {x: innerWidth/2, y: innerHeight/2}")
    steps = 24
    for i in range(1, steps + 1):
        t = i / steps
        eased = t*t*(3-2*t)
        await page.mouse.move(start["x"] + (x-start["x"])*eased, start["y"] + (y-start["y"])*eased)
        await page.wait_for_timeout(max(1, duration_ms // steps))
    await page.evaluate("(p) => window.__tourMouse = p", {"x":x,"y":y})


async def move_to(page: Page, locator: Locator) -> None:
    await locator.wait_for(state="visible", timeout=15000)
    await locator.scroll_into_view_if_needed()
    await page.wait_for_timeout(250)
    b = await locator.bounding_box()
    if not b:
        raise RuntimeError("Target has no visible bounding box.")
    await smooth_mouse(page, b["x"]+b["width"]/2, b["y"]+b["height"]/2)


async def click(page: Page, locator: Locator) -> None:
    await move_to(page, locator)
    await page.wait_for_timeout(200)
    await locator.click()


async def smooth_scroll(page: Page, distance: int, cfg: dict[str, Any]) -> None:
    start = await page.evaluate("scrollY")
    max_y = await page.evaluate("Math.max(0, document.documentElement.scrollHeight-innerHeight)")
    target = max(0, min(max_y, start + distance))
    steps = max(12, min(100, abs(target-start)//max(1,int(cfg.get("pixels_per_step",40)))))
    for i in range(1, steps+1):
        t = i/steps
        eased = t*t*(3-2*t)
        await page.evaluate("(y)=>scrollTo(0,y)", start+(target-start)*eased)
        await page.wait_for_timeout(int(cfg.get("step_duration_ms",16)))
    await page.wait_for_timeout(250)


async def scroll_bottom(page: Page, cfg: dict[str, Any]) -> None:
    for _ in range(30):
        before = await page.evaluate("scrollY")
        await smooth_scroll(page, int((await page.evaluate("innerHeight"))*.72), cfg)
        after = await page.evaluate("scrollY")
        max_y = await page.evaluate("Math.max(0,document.documentElement.scrollHeight-innerHeight)")
        if after >= max_y or after <= before:
            break


async def tour_landing(page: Page, cfg: dict[str, Any]) -> None:
    landing = cfg.get("landing_scroll", {})
    if not landing.get("enabled", True):
        return
    scfg = cfg.get("scroll", {})
    for step in landing.get("steps", []):
        if step.get("type") == "scroll_to_bottom":
            await scroll_bottom(page, scfg)
        elif step.get("type", "scroll_by") == "scroll_by":
            await smooth_scroll(page, int(step.get("pixels",700)), scfg)
        elif step.get("type") == "selector":
            await move_to(page, page.locator(step["selector"]).first)
        await ready(page, cfg)
        await page.wait_for_timeout(int(float(scfg.get("section_pause_seconds",1.5))*1000))


async def interact(page: Page, action: dict[str, Any], cfg: dict[str, Any]) -> None:
    field_sel = action.get("input_selector")
    if field_sel:
        field = page.locator(field_sel).first
        await click(page, field)
        await field.fill("")
        await field.type(str(action.get("sample_text","")), delay=int(action.get("typing_delay_ms",45)))
    submit_sel = action.get("submit_selector")
    if submit_sel:
        await click(page, page.locator(submit_sel).first)
    result_sel = action.get("result_selector")
    if result_sel:
        try:
            await page.locator(result_sel).first.wait_for(state="visible", timeout=int(action.get("wait_for_result_timeout_ms",30000)))
        except PlaywrightTimeoutError:
            LOG.warning("Result selector did not appear: %s", result_sel)
    await ready(page, cfg)
    await page.wait_for_timeout(int(float(cfg.get("timing",{}).get("after_action_seconds",3))*1000))


def export_mp4(webm: Path, mp4: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(f"FFmpeg missing. Install FFmpeg; WebM recording remains at {webm}")
    subprocess.run([
        ffmpeg, "-y", "-i", str(webm),
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=60",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", "-an", str(mp4)
    ], check=True)


async def run(cfg: dict[str, Any], config_path: Path) -> Path:
    root = config_path.parent
    out_dir = root / cfg.get("output_dir","recordings")
    temp_dir = root / cfg.get("temp_dir","temp")
    out_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    video_dir = temp_dir / f"run_{stamp}"
    video_dir.mkdir(parents=True, exist_ok=True)
    browser_cfg = cfg.get("browser", {})
    viewport = browser_cfg.get("viewport", {"width":1920,"height":1080})

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=bool(browser_cfg.get("headless",False)), slow_mo=int(browser_cfg.get("slow_mo_ms",0)))
        context = await browser.new_context(
            viewport=viewport, screen=viewport,
            device_scale_factor=float(browser_cfg.get("device_scale_factor",1)),
            record_video_dir=str(video_dir),
            record_video_size=browser_cfg.get("record_video_size",{"width":1920,"height":1080}),
            reduced_motion="no-preference"
        )
        page = await context.new_page()
        await page.goto(make_url(cfg["base_url"]), wait_until="domcontentloaded")
        await ready(page,cfg)
        await page.wait_for_timeout(int(float(cfg.get("timing",{}).get("hero_pause_seconds",3))*1000))
        await tour_landing(page,cfg)
        for route in cfg.get("routes",[]):
            url = make_url(cfg["base_url"], route.get("path","/"))
            LOG.info("Touring %s", route.get("name",url))
            await page.goto(url, wait_until="domcontentloaded")
            await ready(page,cfg)
            await page.wait_for_timeout(int(float(route.get("pause_seconds",cfg.get("timing",{}).get("after_navigation_seconds",2)))*1000))
            if route.get("interaction"):
                await interact(page, route["interaction"], cfg)
            else:
                await page.wait_for_timeout(int(float(cfg.get("timing",{}).get("after_action_seconds",3))*1000))
        await context.close()
        await browser.close()

    videos = list(video_dir.glob("*.webm"))
    if not videos:
        raise RuntimeError(f"No WebM recording found in {video_dir}")
    mp4 = out_dir / f"website_tour_{stamp}.mp4"
    export_mp4(max(videos, key=lambda x:x.stat().st_size), mp4)
    LOG.info("Saved %s", mp4)
    return mp4


async def main() -> None:
    parser = argparse.ArgumentParser(description="Record a website tour and export MP4.")
    parser.add_argument("--config", default="config.json")
    args = parser.parse_args()
    path = Path(args.config).resolve()
    output = await run(load_config(path),path)
    print(f"Video created: {output}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(main())
