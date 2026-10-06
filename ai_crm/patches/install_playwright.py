import os
import subprocess
import frappe


def execute():
    bench_path = frappe.utils.get_bench_path()
    browsers_path = os.path.join(bench_path, "env", "playwright-browsers")
    playwright_bin = os.path.join(bench_path, "env", "bin", "python")

    env = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": browsers_path}

    result = subprocess.run(
        [playwright_bin, "-m", "playwright", "install", "chromium-headless-shell"],
        env=env,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        frappe.throw(f"Playwright browser install failed:\n{result.stderr}")

    frappe.logger().info(f"Playwright browsers installed at {browsers_path}")
