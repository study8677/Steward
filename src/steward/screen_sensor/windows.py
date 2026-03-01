"""Windows 屏幕传感器实现。"""

from __future__ import annotations

import shutil
import subprocess

from steward.screen_sensor.base import BaseScreenSensor, FrontmostWindow

WINDOW_INFO_SCRIPT = r"""
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class User32 {
  [DllImport("user32.dll")]
  public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll", CharSet = CharSet.Unicode)]
  public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
  [DllImport("user32.dll")]
  public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
}
"@

$handle = [User32]::GetForegroundWindow()
if ($handle -eq [IntPtr]::Zero) {
  Write-Output "||"
  exit 0
}

$builder = New-Object System.Text.StringBuilder 1024
[void][User32]::GetWindowText($handle, $builder, $builder.Capacity)

$pid = 0
[void][User32]::GetWindowThreadProcessId($handle, [ref]$pid)

$procName = ""
if ($pid -gt 0) {
  try {
    $procName = (Get-Process -Id $pid -ErrorAction Stop).ProcessName
  } catch {
    $procName = ""
  }
}

Write-Output "$procName||$($builder.ToString())"
"""


class WindowsScreenSensor(BaseScreenSensor):
    """通过 PowerShell 读取前台窗口并回传 Steward Webhook。"""

    def __init__(
        self,
        *,
        base_url: str,
        interval_seconds: float,
        http_timeout_seconds: float,
        webhook_token: str,
        actor: str,
    ) -> None:
        super().__init__(
            base_url=base_url,
            interval_seconds=interval_seconds,
            http_timeout_seconds=http_timeout_seconds,
            webhook_token=webhook_token,
            actor=actor,
            platform_tag="windows",
        )

    def _read_frontmost_window(self) -> FrontmostWindow:
        """读取当前前台应用与窗口标题。"""
        executable = self._resolve_powershell()
        result = subprocess.run(
            [
                executable,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                WINDOW_INFO_SCRIPT,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or "powershell_failed"
            raise RuntimeError(message)

        raw = result.stdout.strip()
        if "||" in raw:
            app_name, window_title = raw.split("||", maxsplit=1)
        else:
            app_name, window_title = raw, ""
        return FrontmostWindow(app_name=app_name.strip(), window_title=window_title.strip())

    def _resolve_powershell(self) -> str:
        """解析可用的 PowerShell 可执行文件。"""
        for candidate in ("pwsh", "powershell", "powershell.exe"):
            if shutil.which(candidate):
                return candidate
        raise RuntimeError("powershell_not_found")
