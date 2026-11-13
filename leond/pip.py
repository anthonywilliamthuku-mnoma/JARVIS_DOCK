"""Optional picture-in-picture preview for the dock.

LEON cannot move a browser's or media player's own video into the island;
Windows does not expose that. This module gives the island a small live
preview instead: it captures the front window (browser or player) at a low
frame rate and returns one JPEG frame at a time. It is a preview, not true
operating-system PiP, and it stops the moment the tile is closed.
"""

from __future__ import annotations

import base64
import subprocess
from typing import Any

MAX_WIDTH = 480
HINT = (
    "The preview captures the front window with Windows PowerShell. "
    "It works best while the video window is in front."
)

_SCRIPT = r"""
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @"
using System; using System.Runtime.InteropServices;
public class LeonWin {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
}
"@
$h = [LeonWin]::GetForegroundWindow()
if ($h -eq [IntPtr]::Zero) { exit 1 }
$r = New-Object LeonWin+RECT
[LeonWin]::GetWindowRect($h, [ref]$r) | Out-Null
$w = $r.Right - $r.Left
$hh = $r.Bottom - $r.Top
if ($w -le 0 -or $hh -le 0) { exit 1 }
$scale = [Math]::Min(1, 480 / $w)
$nw = [Math]::Max(1, [int]($w * $scale))
$nh = [Math]::Max(1, [int]($hh * $scale))
$bmp = New-Object System.Drawing.Bitmap($nw, $nh)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($r.Left, $r.Top, 0, 0, $bmp.Size)
$ms = New-Object System.IO.MemoryStream
$bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Jpeg)
[Convert]::ToBase64String($ms.ToArray())
"""


def frame() -> dict[str, Any]:
    """One small JPEG frame of the front window, as a data URL."""
    try:
        completed = subprocess.run(  # noqa: S603 - fixed script, no model text
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _SCRIPT],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": f"preview did not run: {type(exc).__name__}"}
    data = "".join(completed.stdout.split())
    if completed.returncode != 0 or not data:
        return {"ok": False, "error": "no front window could be previewed"}
    try:
        decoded = base64.b64decode(data, validate=True)
    except Exception:  # noqa: BLE001 - the script should only print base64
        return {"ok": False, "error": "the preview frame was unreadable"}
    if not decoded:
        return {"ok": False, "error": "the preview frame was empty"}
    return {"ok": True, "data_url": f"data:image/jpeg;base64,{data}"}


__all__ = ["HINT", "MAX_WIDTH", "frame"]
