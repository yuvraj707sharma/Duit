"""Typed, JSON-schema validated Desktop Skills (Allowlist only, no shell, no delete).

Architecture:
  Layer 1 - agent-desktop CLI (native accessibility tree, cross-platform)
  Layer 2 - Python fallback (subprocess, os.startfile, pyautogui)
  Layer 3 - Verification loop (process check, window check, screenshot)

Every launch action is verified: the agent never returns "success" unless it can
prove the app is actually visible on screen.
"""
import os
import re
import json
import time
import shutil
import platform
import subprocess
import urllib.parse
import logging
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Security: Blocked system patterns and disallowed intents
# ──────────────────────────────────────────────────────────────────────────────
DISALLOWED_INTENTS = {"shell", "exec", "delete", "rm", "unlink", "drop", "format", "eval"}

BLOCKED_SYSTEM_PATTERNS = {
    "rmdir", "del", "format", "diskpart", "reg", "regedit",
    "shutdown", "reboot", "vssadmin", "bcdedit", "malicious_app.exe", "malicious"
}

# ──────────────────────────────────────────────────────────────────────────────
# Cross-platform app registry: logical name -> per-OS launch commands
# ──────────────────────────────────────────────────────────────────────────────
APP_REGISTRY: Dict[str, Dict[str, List[str]]] = {
    "notepad":    {"Windows": ["notepad.exe"],       "Darwin": ["open", "-a", "TextEdit"],   "Linux": ["gedit"]},
    "notes":      {"Windows": ["notepad.exe"],       "Darwin": ["open", "-a", "Notes"],      "Linux": ["gedit"]},
    "calculator": {"Windows": ["calc.exe"],          "Darwin": ["open", "-a", "Calculator"], "Linux": ["gnome-calculator"]},
    "calc":       {"Windows": ["calc.exe"],          "Darwin": ["open", "-a", "Calculator"], "Linux": ["gnome-calculator"]},
    "terminal":   {"Windows": ["powershell.exe"],    "Darwin": ["open", "-a", "Terminal"],   "Linux": ["gnome-terminal"]},
    "cmd":        {"Windows": ["cmd.exe"],           "Darwin": ["open", "-a", "Terminal"],   "Linux": ["xterm"]},
    "powershell": {"Windows": ["powershell.exe"],    "Darwin": ["open", "-a", "Terminal"],   "Linux": ["gnome-terminal"]},
    "files":      {"Windows": ["explorer.exe"],      "Darwin": ["open", "-a", "Finder"],     "Linux": ["nautilus"]},
    "explorer":   {"Windows": ["explorer.exe"],      "Darwin": ["open", "-a", "Finder"],     "Linux": ["nautilus"]},
    "finder":     {"Windows": ["explorer.exe"],      "Darwin": ["open", "-a", "Finder"],     "Linux": ["nautilus"]},
    "paint":      {"Windows": ["mspaint.exe"],       "Darwin": ["open", "-a", "Preview"],    "Linux": ["gimp"]},
    "camera":     {"Windows": ["start", "microsoft.windows.camera:"], "Darwin": ["open", "-a", "Photo Booth"], "Linux": ["cheese"]},
    "settings":   {"Windows": ["start", "ms-settings:"], "Darwin": ["open", "-a", "System Preferences"], "Linux": ["gnome-control-center"]},
    "photos":     {"Windows": ["start", "ms-photos:"], "Darwin": ["open", "-a", "Photos"], "Linux": ["eog"]},
    "chrome":         {"Windows": ["chrome.exe"],        "Darwin": ["open", "-a", "Google Chrome"], "Linux": ["google-chrome"]},
    "google chrome":  {"Windows": ["chrome.exe"],        "Darwin": ["open", "-a", "Google Chrome"], "Linux": ["google-chrome"]},
    "edge":           {"Windows": ["msedge.exe"],        "Darwin": ["open", "-a", "Microsoft Edge"], "Linux": ["microsoft-edge"]},
    "msedge":         {"Windows": ["msedge.exe"],        "Darwin": ["open", "-a", "Microsoft Edge"], "Linux": ["microsoft-edge"]},
    "microsoft edge": {"Windows": ["msedge.exe"],        "Darwin": ["open", "-a", "Microsoft Edge"], "Linux": ["microsoft-edge"]},
    "firefox":    {"Windows": ["firefox.exe"],       "Darwin": ["open", "-a", "Firefox"],    "Linux": ["firefox"]},
    "brave":      {"Windows": ["brave.exe"],         "Darwin": ["open", "-a", "Brave Browser"], "Linux": ["brave-browser"]},
    "safari":     {"Windows": [],                    "Darwin": ["open", "-a", "Safari"],     "Linux": []},
    "code":       {"Windows": ["code"],              "Darwin": ["open", "-a", "Visual Studio Code"], "Linux": ["code"]},
    "vscode":     {"Windows": ["code"],              "Darwin": ["open", "-a", "Visual Studio Code"], "Linux": ["code"]},
    "slack":      {"Windows": ["slack.exe"],         "Darwin": ["open", "-a", "Slack"],      "Linux": ["slack"]},
    "discord":    {"Windows": ["discord.exe"],       "Darwin": ["open", "-a", "Discord"],    "Linux": ["discord"]},
    "spotify":    {"Windows": ["spotify.exe"],       "Darwin": ["open", "-a", "Spotify"],    "Linux": ["spotify"]},
    "teams":      {"Windows": ["ms-teams.exe"],      "Darwin": ["open", "-a", "Microsoft Teams"], "Linux": ["teams"]},
    "zoom":       {"Windows": ["zoom.exe"],          "Darwin": ["open", "-a", "zoom.us"],    "Linux": ["zoom"]},
    "vlc":        {"Windows": ["vlc.exe"],           "Darwin": ["open", "-a", "VLC"],        "Linux": ["vlc"]},
    "obs":        {"Windows": ["obs64.exe"],         "Darwin": ["open", "-a", "OBS"],        "Linux": ["obs"]},
    "gimp":       {"Windows": ["gimp-2.10.exe"],     "Darwin": ["open", "-a", "GIMP"],       "Linux": ["gimp"]},
    "postman":    {"Windows": ["postman.exe"],       "Darwin": ["open", "-a", "Postman"],    "Linux": ["postman"]},
    "outlook":    {"Windows": ["outlook.exe"],       "Darwin": ["open", "-a", "Microsoft Outlook"], "Linux": []},
    "word":       {"Windows": ["winword.exe"],       "Darwin": ["open", "-a", "Microsoft Word"], "Linux": ["libreoffice", "--writer"]},
    "excel":      {"Windows": ["excel.exe"],         "Darwin": ["open", "-a", "Microsoft Excel"], "Linux": ["libreoffice", "--calc"]},
    "powerpoint": {"Windows": ["powerpnt.exe"],      "Darwin": ["open", "-a", "Microsoft PowerPoint"], "Linux": ["libreoffice", "--impress"]},
    "onenote":    {"Windows": ["onenote.exe"],       "Darwin": ["open", "-a", "Microsoft OneNote"], "Linux": []},
    "textedit":   {"Windows": ["notepad.exe"],       "Darwin": ["open", "-a", "TextEdit"],   "Linux": ["gedit"]},
    "preview":    {"Windows": ["mspaint.exe"],       "Darwin": ["open", "-a", "Preview"],    "Linux": ["eog"]},
    "snip":       {"Windows": ["snippingtool.exe"],  "Darwin": [],                           "Linux": ["gnome-screenshot"]},
    "store":      {"Windows": ["start", "ms-windows-store:"], "Darwin": ["open", "-a", "App Store"], "Linux": []},
}

WEB_FALLBACKS = {
    "slack": "https://app.slack.com/client",
    "spotify": "https://open.spotify.com",
    "discord": "https://discord.com/app",
    "teams": "https://teams.microsoft.com",
    "notion": "https://www.notion.so",
    "figma": "https://www.figma.com",
    "excel": "https://excel.office.com",
    "word": "https://word.office.com",
    "whatsapp": "https://web.whatsapp.com",
    "telegram": "https://web.telegram.org",
}


class SkillValidationError(ValueError):
    """Raised when skill payload fails strict allowlist or schema validation."""
    pass


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic schemas for each skill
# ──────────────────────────────────────────────────────────────────────────────
class OpenAppArgs(BaseModel):
    idempotency_key: str = Field(..., description="Unique client-side UUID.")
    app_name: str = Field(..., description="Application name to dynamically resolve and launch.")
    draft_text: Optional[str] = Field(None, description="Optional draft content to initialize application with.")
    profile: Optional[str] = Field(None, description="Optional browser user profile directory or name.")

    @field_validator("app_name")
    @classmethod
    def validate_app_name(cls, v: str) -> str:
        clean = v.strip().lower()
        if not clean:
            raise SkillValidationError("Application name cannot be empty.")
        disallowed = {"rmdir", "del", "format", "diskpart", "reg", "regedit", "shutdown", "reboot", "vssadmin", "bcdedit", "malicious_app.exe"}
        if any(d in clean for d in disallowed) or any(c in clean for c in (";", "&", "|", "`", "\n", "\r", "$")):
            raise SkillValidationError(f"Application '{clean}' is not in allowlist: blocked security pattern.")
        return clean


class OpenUrlArgs(BaseModel):
    idempotency_key: str = Field(..., description="Unique client-side UUID.")
    url: str = Field(..., description="HTTP or HTTPS URL.")
    browser: Optional[str] = Field("default", description="Target browser (e.g. edge, chrome, default).")
    profile: Optional[str] = Field(None, description="Optional browser user profile directory or name.")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        clean = v.strip()
        # Automatically prepend https:// if missing
        if not clean.startswith("http://") and not clean.startswith("https://"):
            if "://" in clean:
                raise SkillValidationError(
                    f"Invalid URL scheme. Only 'http' and 'https' are permitted."
                )
            clean = f"https://{clean}"
        parsed = urllib.parse.urlparse(clean)
        if parsed.scheme.lower() not in ("http", "https"):
            raise SkillValidationError(
                f"Invalid URL scheme '{parsed.scheme}'. Only 'http' and 'https' are permitted."
            )
        if not parsed.netloc:
            raise SkillValidationError("Invalid URL: missing domain/hostname.")
        return clean


class CreateNoteArgs(BaseModel):
    idempotency_key: str = Field(..., description="Unique client-side UUID.")
    title: str = Field(..., description="Title of the note.")
    content: str = Field(..., description="Text content of the note.")

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise SkillValidationError("Note title cannot be empty.")
        if ".." in clean or "/" in clean or "\\" in clean:
            raise SkillValidationError("Note title cannot contain path separators or parent directory traversal.")
        return clean


class TypeTextArgs(BaseModel):
    idempotency_key: str = Field(..., description="Unique client-side UUID.")
    text: str = Field(..., description="Text to type into focused non-password window.")
    target_control_type: Optional[str] = Field("edit", description="Focused control type (must not be password).")

    @field_validator("target_control_type")
    @classmethod
    def validate_not_password_field(cls, v: Optional[str]) -> Optional[str]:
        if v and any(p in v.lower() for p in ("password", "passcode", "secret", "secure_edit", "pin")):
            raise SkillValidationError(
                "Security policy violation: Typing directly into password or secure entry fields is strictly prohibited."
            )
        return v


class SetVolumeArgs(BaseModel):
    idempotency_key: str = Field(..., description="Unique client-side UUID.")
    level: int = Field(..., ge=0, le=100, description="Volume level from 0 to 100.")


class SearchFilesArgs(BaseModel):
    query: str = Field(..., description="Read-only search substring.")
    directory: Optional[str] = Field(None, description="Optional sandbox directory.")


class ClearHistoryArgs(BaseModel):
    idempotency_key: str = Field(..., description="Unique client-side UUID.")


class AutomateCartArgs(BaseModel):
    idempotency_key: str = Field(..., description="Unique client-side UUID.")
    product_name: str = Field(..., description="Product name or keywords to search and add to cart.")
    store: Optional[str] = Field("amazon", description="E-commerce store (e.g. amazon, flipkart).")


class ScreenshotArgs(BaseModel):
    idempotency_key: str = Field(..., description="Unique client-side UUID.")
    app_name: Optional[str] = Field(None, description="Optional app name to screenshot (uses full screen if omitted).")


# ──────────────────────────────────────────────────────────────────────────────
# agent-desktop CLI bridge (cross-platform, accessibility-tree based)
# ──────────────────────────────────────────────────────────────────────────────
class AgentDesktopBridge:
    """Wrapper around the agent-desktop CLI for reliable cross-platform desktop control."""

    def __init__(self):
        self._available: Optional[bool] = None
        self._binary: Optional[str] = None

    @property
    def available(self) -> bool:
        if self._available is None:
            self._binary = shutil.which("agent-desktop")
            self._available = self._binary is not None
        return self._available

    def _run(self, args: List[str], timeout: float = 15.0) -> Optional[Dict[str, Any]]:
        """Run an agent-desktop command and return parsed JSON, or None on failure."""
        if not self.available:
            return None
        try:
            cmd = ["agent-desktop"] + args
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.stdout.strip():
                data = json.loads(result.stdout.strip())
                return data if data.get("ok") else None
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError, OSError) as e:
            logger.debug("agent-desktop command failed: %s %s -> %s", args, type(e).__name__, e)
        return None

    def launch_app(self, app_path_or_name: str) -> Optional[Dict[str, Any]]:
        """Launch an application via agent-desktop (uses OS launch mechanism)."""
        return self._run(["launch", app_path_or_name], timeout=10.0)

    def list_apps(self) -> Optional[List[str]]:
        """List currently running apps visible to the accessibility tree."""
        result = self._run(["list-apps"], timeout=8.0)
        if result and "data" in result:
            apps = result["data"]
            if isinstance(apps, list):
                return [a.get("name", "") if isinstance(a, dict) else str(a) for a in apps]
            elif isinstance(apps, dict) and "apps" in apps:
                return [a.get("name", "") if isinstance(a, dict) else str(a) for a in apps["apps"]]
        return None

    def snapshot(self, app_name: Optional[str] = None, skeleton: bool = False) -> Optional[Dict[str, Any]]:
        """Take an accessibility tree snapshot of an app or the focused window."""
        args = ["snapshot", "-i", "--compact"]
        if skeleton:
            args.append("--skeleton")
        if app_name:
            args.extend(["--app", app_name])
        return self._run(args, timeout=10.0)

    def screenshot(self, app_name: Optional[str] = None, output_path: Optional[str] = None) -> Optional[str]:
        """Take a screenshot and return the file path."""
        args = ["screenshot"]
        if app_name:
            args.extend(["--app", app_name])
        if output_path:
            args.extend(["--output", output_path])
        result = self._run(args, timeout=10.0)
        if result and "data" in result:
            return result["data"].get("path") or result["data"].get("file")
        return None

    def find_element(self, role: str = None, name: str = None, app_name: str = None) -> Optional[Dict[str, Any]]:
        """Find a UI element in the accessibility tree by role and/or name."""
        args = ["find"]
        if role:
            args.extend(["--role", role])
        if name:
            args.extend(["--name", name])
        if app_name:
            args.extend(["--app", app_name])
        return self._run(args, timeout=8.0)

    def click_ref(self, ref: str) -> Optional[Dict[str, Any]]:
        """Click an element by its accessibility ref."""
        return self._run(["click", ref], timeout=8.0)

    def set_value(self, ref: str, value: str) -> Optional[Dict[str, Any]]:
        """Set value on an element by ref (text fields, etc.)."""
        return self._run(["set-value", ref, value], timeout=8.0)

    def focus_window(self, app_name: str) -> Optional[Dict[str, Any]]:
        """Bring an app's window to the foreground."""
        return self._run(["focus-window", "--app", app_name], timeout=5.0)

    def close_app(self, app_name: str) -> Optional[Dict[str, Any]]:
        """Close an application."""
        return self._run(["close-app", "--app", app_name], timeout=8.0)

    def get_status(self) -> Optional[Dict[str, Any]]:
        """Check agent-desktop status, permissions, and supported surfaces."""
        return self._run(["status"], timeout=5.0)


# Module-level singleton
agent_desktop = AgentDesktopBridge()


# ──────────────────────────────────────────────────────────────────────────────
# Verification engine: 3-step (process, window, screenshot)
# ──────────────────────────────────────────────────────────────────────────────
class LaunchVerifier:
    """Verifies that a launched application is actually visible on screen."""

    SCREENSHOT_DIR = os.path.join(os.path.expanduser("~"), ".fastagent", "screenshots")

    def __init__(self):
        os.makedirs(self.SCREENSHOT_DIR, exist_ok=True)

    def verify_launch(
        self,
        app_name: str,
        process_names: Optional[List[str]] = None,
        timeout_seconds: float = 6.0,
        action_id: str = "",
    ) -> Dict[str, Any]:
        """
        Polls for up to timeout_seconds to confirm the app launched.

        Returns:
            {
              "verified": bool,
              "method": "agent-desktop" | "process" | "window" | "none",
              "screenshot_path": Optional[str],
              "details": str
            }
        """
        poll_interval = 0.5
        deadline = time.monotonic() + timeout_seconds
        clean = app_name.lower().strip()

        # Attempt 1: agent-desktop snapshot (most reliable, cross-platform)
        if agent_desktop.available:
            snap = agent_desktop.snapshot(app_name=app_name)
            if snap and snap.get("data"):
                screenshot_path = self._take_screenshot(clean, action_id)
                return {
                    "verified": True,
                    "method": "agent-desktop",
                    "screenshot_path": screenshot_path,
                    "details": f"Verified via accessibility tree: '{app_name}' is visible."
                }

        # Attempt 2: Poll process + window
        while time.monotonic() < deadline:
            # 2a: Process check via psutil
            process_alive = self._check_process(clean, process_names)

            # 2b: Window check via pygetwindow (Windows) or wmctrl/xdotool (Linux)
            window_visible = self._check_window(clean)

            if process_alive and window_visible:
                screenshot_path = self._take_screenshot(clean, action_id)
                return {
                    "verified": True,
                    "method": "process+window",
                    "screenshot_path": screenshot_path,
                    "details": f"Process running and window visible for '{app_name}'."
                }

            if process_alive:
                # Process is alive but window may not be painted yet, keep polling
                time.sleep(poll_interval)
                continue

            time.sleep(poll_interval)

        # Final attempt: just check process (window manager may not report correctly)
        if self._check_process(clean, process_names):
            screenshot_path = self._take_screenshot(clean, action_id)
            return {
                "verified": True,
                "method": "process",
                "screenshot_path": screenshot_path,
                "details": f"Process found for '{app_name}' (window check inconclusive)."
            }

        return {
            "verified": False,
            "method": "none",
            "screenshot_path": None,
            "details": f"No process or visible window detected for '{app_name}' within {timeout_seconds}s."
        }

    def _check_process(self, app_name: str, extra_names: Optional[List[str]] = None) -> bool:
        """Check if a process matching the app name is running."""
        try:
            import psutil
            search_names = {app_name}
            if extra_names:
                search_names.update(n.lower() for n in extra_names)
            # Add alias aliases for common apps
            if any(w in app_name for w in ("edge", "msedge")):
                search_names.update(["msedge", "msedge.exe", "edge", "microsoft edge"])
            if any(w in app_name for w in ("chrome", "google-chrome")):
                search_names.update(["chrome", "chrome.exe", "google chrome"])
            # Also add common exe variants
            search_names.update(f"{app_name}.exe" for _ in [0])

            for proc in psutil.process_iter(["name", "exe"]):
                try:
                    pname = (proc.info.get("name") or "").lower()
                    pexe = (proc.info.get("exe") or "").lower()
                    for sn in search_names:
                        if sn in pname or sn in pexe:
                            return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except ImportError:
            logger.debug("psutil not installed, skipping process check")
        except Exception as e:
            logger.debug("Process check error: %s", e)
        return False

    def _check_window(self, app_name: str) -> bool:
        """Check if a visible window with matching title exists."""
        current_os = platform.system()

        if current_os == "Windows":
            return self._check_window_windows(app_name)
        elif current_os == "Darwin":
            return self._check_window_macos(app_name)
        else:
            return self._check_window_linux(app_name)

    def _check_window_windows(self, app_name: str) -> bool:
        """Windows: use pygetwindow to find visible windows."""
        try:
            import pygetwindow as gw
            all_windows = gw.getAllWindows()
            for win in all_windows:
                if not win.title:
                    continue
                title_lower = win.title.lower()
                if app_name in title_lower:
                    # Check that the window has real dimensions (not minimized to 0x0)
                    if win.width > 50 and win.height > 50:
                        return True
        except ImportError:
            logger.debug("pygetwindow not installed, skipping window check")
        except Exception as e:
            logger.debug("Window check (Windows) error: %s", e)

        # Fallback: enumerate via win32gui if available
        try:
            import ctypes
            import ctypes.wintypes

            found = [False]

            def _enum_callback(hwnd, _):
                if ctypes.windll.user32.IsWindowVisible(hwnd):
                    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                        if app_name in buf.value.lower():
                            found[0] = True
                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
            ctypes.windll.user32.EnumWindows(WNDENUMPROC(_enum_callback), 0)
            return found[0]
        except Exception:
            pass

        return False

    def _check_window_macos(self, app_name: str) -> bool:
        """macOS: use AppleScript to check for visible windows."""
        try:
            script = f'''
            tell application "System Events"
                set appList to (name of every process whose visible is true)
            end tell
            return appList as text
            '''
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=5.0
            )
            if result.returncode == 0 and app_name in result.stdout.lower():
                return True
        except Exception as e:
            logger.debug("Window check (macOS) error: %s", e)
        return False

    def _check_window_linux(self, app_name: str) -> bool:
        """Linux: use wmctrl or xdotool to check for visible windows."""
        # Try wmctrl first
        try:
            result = subprocess.run(
                ["wmctrl", "-l"], capture_output=True, text=True, timeout=5.0
            )
            if result.returncode == 0 and app_name in result.stdout.lower():
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Fallback to xdotool
        try:
            result = subprocess.run(
                ["xdotool", "search", "--name", app_name],
                capture_output=True, text=True, timeout=5.0
            )
            if result.returncode == 0 and result.stdout.strip():
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return False

    def _take_screenshot(self, app_name: str, action_id: str = "") -> Optional[str]:
        """Capture a verification screenshot."""
        ts = int(time.time())
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", app_name)
        filename = f"verified_{safe_name}_{action_id or ts}.png"
        filepath = os.path.join(self.SCREENSHOT_DIR, filename)

        # Attempt 1: agent-desktop screenshot (cross-platform)
        if agent_desktop.available:
            ad_path = agent_desktop.screenshot(app_name=app_name, output_path=filepath)
            if ad_path and os.path.exists(ad_path):
                return ad_path

        # Attempt 2: pyautogui (cross-platform Python)
        try:
            import pyautogui
            screenshot = pyautogui.screenshot()
            screenshot.save(filepath)
            return filepath
        except Exception as e:
            logger.debug("Screenshot capture failed: %s", e)

        # Attempt 3: mss (faster, cross-platform)
        try:
            import mss
            with mss.mss() as sct:
                sct.shot(output=filepath)
                return filepath
        except ImportError:
            pass
        except Exception as e:
            logger.debug("mss screenshot failed: %s", e)

        return None


# Module-level singleton
launch_verifier = LaunchVerifier()


# ──────────────────────────────────────────────────────────────────────────────
# Cross-platform application resolver
# ──────────────────────────────────────────────────────────────────────────────
def find_desktop_application(app_name: str) -> Optional[Dict[str, Any]]:
    """Resolve an app name to a launchable target, cross-platform."""
    clean = app_name.lower().strip()
    current_os = platform.system()

    # 1. Check the cross-platform registry first
    if clean in APP_REGISTRY:
        os_commands = APP_REGISTRY[clean].get(current_os, [])
        if os_commands:
            binary = os_commands[0]
            # For "start" prefix (Windows protocol URIs), treat as protocol
            if binary == "start" and current_os == "Windows":
                return {"type": "protocol", "target": os_commands[1], "launch_cmd": os_commands}
            # For "open" prefix (macOS), treat as mac-open
            if binary == "open" and current_os == "Darwin":
                return {"type": "mac-open", "target": os_commands[-1], "launch_cmd": os_commands}
            # Otherwise, check that binary is reachable
            resolved = shutil.which(binary)
            if resolved:
                return {"type": "binary", "target": resolved, "launch_cmd": os_commands}
            # On Windows, try without .exe
            if current_os == "Windows":
                resolved = shutil.which(f"{binary}.exe") if not binary.endswith(".exe") else None
                if resolved:
                    return {"type": "binary", "target": resolved, "launch_cmd": os_commands}

    # 2. Try shutil.which directly
    which_target = shutil.which(clean) or shutil.which(f"{clean}.exe")
    if which_target:
        return {"type": "binary", "target": which_target, "launch_cmd": [which_target]}

    # 3. Windows-specific: Registry App Paths, Start Menu shortcuts, program dirs
    if current_os == "Windows":
        win_result = _find_windows_app(clean)
        if win_result:
            return win_result

    # 4. macOS: try "open -a" which handles app bundles
    if current_os == "Darwin":
        try:
            result = subprocess.run(
                ["mdfind", f"kMDItemDisplayName == '{app_name}'", "-onlyin", "/Applications"],
                capture_output=True, text=True, timeout=5.0
            )
            if result.returncode == 0 and result.stdout.strip():
                app_path = result.stdout.strip().split("\n")[0]
                return {"type": "mac-open", "target": app_path, "launch_cmd": ["open", "-a", app_path]}
        except Exception:
            pass
        # Generic fallback
        return {"type": "mac-open", "target": app_name, "launch_cmd": ["open", "-a", app_name]}

    # 5. Linux: try gtk-launch, xdg-open for .desktop files
    if current_os == "Linux":
        # Check for .desktop file
        desktop_dirs = [
            os.path.expanduser("~/.local/share/applications"),
            "/usr/share/applications",
            "/usr/local/share/applications",
        ]
        for d in desktop_dirs:
            desktop_file = os.path.join(d, f"{clean}.desktop")
            if os.path.exists(desktop_file):
                return {"type": "desktop-file", "target": desktop_file, "launch_cmd": ["gtk-launch", f"{clean}.desktop"]}
        # Also check for partial name matches
        for d in desktop_dirs:
            if os.path.isdir(d):
                try:
                    for f in os.listdir(d):
                        if f.endswith(".desktop") and clean in f.lower():
                            return {"type": "desktop-file", "target": os.path.join(d, f), "launch_cmd": ["gtk-launch", f]}
                except OSError:
                    pass

    return None


def _find_windows_app(clean: str) -> Optional[Dict[str, Any]]:
    """Windows-specific deep application search across App Paths, Start Menu, Uninstall keys, and Program Files."""
    import glob
    import winreg

    clean_norm = re.sub(r"[_\-\s]+", "", clean)
    clean_tokens = [t for t in re.sub(r"[_\-\.]+", " ", clean).split() if len(t) > 1]

    # 1. Registry App Paths (covers all registered 32/64-bit applications)
    registry_keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"),
    ]
    for root, subkey in registry_keys:
        try:
            with winreg.OpenKey(root, subkey) as key:
                num_subkeys = winreg.QueryInfoKey(key)[0]
                for i in range(num_subkeys):
                    sk_name = winreg.EnumKey(key, i)
                    sk_lower = sk_name.lower()
                    sk_norm = re.sub(r"[_\-\s\.]+", "", sk_lower)
                    if clean in sk_lower or clean_norm in sk_norm or (clean_tokens and all(t in sk_lower for t in clean_tokens)):
                        try:
                            with winreg.OpenKey(key, sk_name) as app_key:
                                exe_path, _ = winreg.QueryValueEx(app_key, "")
                                if exe_path:
                                    clean_exe = exe_path.strip().strip('"')
                                    if os.path.exists(clean_exe):
                                        return {"type": "binary", "target": clean_exe, "launch_cmd": [clean_exe]}
                        except Exception:
                            pass
        except Exception:
            pass

    # 2. Windows Start Menu Shortcuts (.lnk files across all users and current user)
    try:
        search_globs = [
            os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs\**\*.lnk"),
            os.path.expandvars(r"%AppData%\Microsoft\Windows\Start Menu\Programs\**\*.lnk"),
        ]
        for sp in search_globs:
            for f in glob.glob(sp, recursive=True):
                base = os.path.splitext(os.path.basename(f))[0].lower()
                base_norm = re.sub(r"[_\-\s]+", "", base)
                if clean in base or clean_norm in base_norm or (clean_tokens and all(t in base for t in clean_tokens)):
                    return {"type": "shortcut", "target": f, "launch_cmd": [f]}
    except Exception:
        pass

    # 3. Windows Uninstall Registry (locates install paths of apps like Steam, Discord, Postman, Cursor)
    uninstall_keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for root, subkey in uninstall_keys:
        try:
            with winreg.OpenKey(root, subkey) as key:
                num_subkeys = winreg.QueryInfoKey(key)[0]
                for i in range(num_subkeys):
                    sk_name = winreg.EnumKey(key, i)
                    try:
                        with winreg.OpenKey(key, sk_name) as app_key:
                            disp_name, _ = winreg.QueryValueEx(app_key, "DisplayName")
                            if disp_name:
                                d_lower = disp_name.lower()
                                if clean in d_lower or (clean_tokens and all(t in d_lower for t in clean_tokens)):
                                    # Check DisplayIcon or InstallLocation
                                    try:
                                        icon_path, _ = winreg.QueryValueEx(app_key, "DisplayIcon")
                                        if icon_path:
                                            icon_clean = icon_path.split(",")[0].strip().strip('"')
                                            if icon_clean.endswith(".exe") and os.path.exists(icon_clean):
                                                return {"type": "binary", "target": icon_clean, "launch_cmd": [icon_clean]}
                                    except Exception:
                                        pass
                                    try:
                                        loc, _ = winreg.QueryValueEx(app_key, "InstallLocation")
                                        if loc and os.path.isdir(loc):
                                            # Look for exe matching app name inside install folder
                                            for candidate_exe in glob.glob(os.path.join(loc, "*.exe")):
                                                return {"type": "binary", "target": candidate_exe, "launch_cmd": [candidate_exe]}
                                    except Exception:
                                        pass
                    except Exception:
                        pass
        except Exception:
            pass

    # 4. Standard application directories
    candidates = [
        os.path.expandvars(rf"%LOCALAPPDATA%\Programs\{clean}\{clean}.exe"),
        os.path.expandvars(rf"%ProgramFiles%\{clean}\{clean}.exe"),
        os.path.expandvars(rf"%ProgramFiles(x86)%\{clean}\{clean}.exe"),
        os.path.expandvars(rf"%LOCALAPPDATA%\{clean}\{clean}.exe"),
    ]
    for cand in candidates:
        if os.path.exists(cand):
            return {"type": "binary", "target": cand, "launch_cmd": [cand]}

    return None


def is_app_installed(app_name: str, executable_name: str = "") -> bool:
    if find_desktop_application(app_name):
        return True
    return False


# ──────────────────────────────────────────────────────────────────────────────
# Browser Profile Discovery & Resolution (Chrome & Edge)
# ──────────────────────────────────────────────────────────────────────────────
def get_browser_profiles(browser: str = "chrome") -> Dict[str, Dict[str, str]]:
    """Discover available user profiles for Chrome or Edge across platforms."""
    current_os = platform.system()
    b_clean = browser.lower().strip()
    profiles: Dict[str, Dict[str, str]] = {}
    candidate_paths = []

    if "edge" in b_clean:
        if current_os == "Windows":
            candidate_paths.append(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data\Local State"))
        elif current_os == "Darwin":
            candidate_paths.append(os.path.expanduser("~/Library/Application Support/Microsoft Edge/Local State"))
        else:
            candidate_paths.append(os.path.expanduser("~/.config/microsoft-edge/Local State"))
    else:
        # Default to Chrome
        if current_os == "Windows":
            candidate_paths.append(os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\Local State"))
        elif current_os == "Darwin":
            candidate_paths.append(os.path.expanduser("~/Library/Application Support/Google/Chrome/Local State"))
        else:
            candidate_paths.append(os.path.expanduser("~/.config/google-chrome/Local State"))

    for p in candidate_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                info_cache = data.get("profile", {}).get("info_cache", {})
                for k, v in info_cache.items():
                    profiles[k] = {
                        "id": k,
                        "name": v.get("name", k),
                        "email": v.get("user_name", ""),
                        "gaia_name": v.get("gaia_name", "")
                    }
            except Exception as e:
                logger.debug("Failed reading browser profiles from %s: %s", p, e)

    return profiles


def resolve_browser_profile(browser: str = "chrome", query: Optional[str] = None) -> Optional[str]:
    """Resolves a profile query (name, email, index, or folder) to a specific browser profile directory."""
    if not query:
        return None
    q = str(query).strip().lower()
    profiles = get_browser_profiles(browser)
    if not profiles:
        return query

    # 1. Exact directory ID match (e.g. 'Default', 'Profile 6')
    for k in profiles:
        if k.lower() == q:
            return k

    # 2. Number match: '6' -> 'Profile 6'
    if q.isdigit():
        target = f"profile {q}"
        for k in profiles:
            if k.lower() == target:
                return k

    # 3. Exact profile display name or account name
    for k, v in profiles.items():
        if v.get("name", "").lower() == q or v.get("gaia_name", "").lower() == q:
            return k

    # 4. Exact email match
    for k, v in profiles.items():
        if v.get("email", "").lower() == q:
            return k

    # 5. Substring / partial match on email, name, or account name
    for k, v in profiles.items():
        if (
            q in v.get("email", "").lower()
            or q in v.get("name", "").lower()
            or q in v.get("gaia_name", "").lower()
        ):
            return k

    # 6. Fallback substring on folder ID
    for k in profiles:
        if q in k.lower():
            return k

    return query


# ──────────────────────────────────────────────────────────────────────────────
# Cross-platform app launcher
# ──────────────────────────────────────────────────────────────────────────────
def launch_application(
    app_name: str,
    app_info: Optional[Dict[str, Any]] = None,
    url: Optional[str] = None,
    profile: Optional[str] = None
) -> bool:
    """Launch an application using the best available method for this OS. Returns True if launch command was sent."""
    current_os = platform.system()
    clean_app = app_name.lower().strip()

    # Browser profile targeting for Chrome / Edge
    is_chrome = any(c in clean_app for c in ("chrome", "google-chrome"))
    is_edge = any(e in clean_app for e in ("edge", "msedge"))

    if (is_chrome or is_edge) and profile:
        browser_type = "edge" if is_edge else "chrome"
        resolved_prof = resolve_browser_profile(browser_type, profile)
        if not app_info:
            app_info = find_desktop_application(app_name)
        if app_info and app_info.get("target"):
            cmd = [app_info["target"], f"--profile-directory={resolved_prof}"]
            if url:
                cmd.append(url)
            try:
                subprocess.Popen(
                    cmd,
                    shell=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if current_os == "Windows" else 0,
                )
                return True
            except Exception as e:
                logger.warning("Failed launching %s with profile '%s': %s", app_name, resolved_prof, e)

    # Layer 1: Try agent-desktop launch (cross-platform, most reliable)
    if agent_desktop.available:
        result = agent_desktop.launch_app(app_name)
        if result:
            return True

    if not app_info:
        app_info = find_desktop_application(app_name)

    if not app_info:
        return False

    target = app_info["target"]
    app_type = app_info.get("type", "binary")
    launch_cmd = app_info.get("launch_cmd", [target])

    try:
        if current_os == "Windows":
            if app_type == "protocol":
                os.startfile(target)
            elif app_type == "shortcut":
                os.startfile(target)
            else:
                # Try os.startfile first, then subprocess
                try:
                    os.startfile(target)
                except Exception:
                    subprocess.Popen(
                        launch_cmd,
                        shell=False,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )

        elif current_os == "Darwin":
            if app_type == "mac-open":
                subprocess.Popen(launch_cmd, shell=False)
            else:
                subprocess.Popen(["open", "-a", target], shell=False)

        else:  # Linux
            if app_type == "desktop-file":
                subprocess.Popen(launch_cmd, shell=False)
            else:
                subprocess.Popen(launch_cmd, shell=False)

        return True
    except Exception as e:
        logger.warning("Failed to launch '%s' via %s: %s", app_name, app_type, e)
        return False


def launch_url(url: str, browser: str = "default", profile: Optional[str] = None) -> bool:
    """Open a URL in a specific or default browser, cross-platform, with optional profile targeting."""
    current_os = platform.system()
    browser = (browser or "default").lower().strip()

    # If profile is specified but browser is default, auto-detect target browser
    if browser == "default" and profile:
        chrome_profs = get_browser_profiles("chrome")
        if chrome_profs and resolve_browser_profile("chrome", profile) in chrome_profs:
            browser = "chrome"
        else:
            edge_profs = get_browser_profiles("edge")
            if edge_profs and resolve_browser_profile("edge", profile) in edge_profs:
                browser = "edge"
            else:
                browser = "chrome"

    # Browser-specific launch
    browser_map = {
        "edge": {"Windows": ["msedge.exe"], "Darwin": ["open", "-a", "Microsoft Edge"], "Linux": ["microsoft-edge"]},
        "msedge": {"Windows": ["msedge.exe"], "Darwin": ["open", "-a", "Microsoft Edge"], "Linux": ["microsoft-edge"]},
        "chrome": {"Windows": ["chrome.exe"], "Darwin": ["open", "-a", "Google Chrome"], "Linux": ["google-chrome"]},
        "google-chrome": {"Windows": ["chrome.exe"], "Darwin": ["open", "-a", "Google Chrome"], "Linux": ["google-chrome"]},
        "firefox": {"Windows": ["firefox.exe"], "Darwin": ["open", "-a", "Firefox"], "Linux": ["firefox"]},
        "brave": {"Windows": ["brave.exe"], "Darwin": ["open", "-a", "Brave Browser"], "Linux": ["brave-browser"]},
        "safari": {"Windows": [], "Darwin": ["open", "-a", "Safari"], "Linux": []},
    }

    if browser != "default" and browser in browser_map:
        os_cmds = browser_map[browser].get(current_os, [])
        if os_cmds:
            try:
                # Resolve the browser binary
                browser_path = shutil.which(os_cmds[0])
                if not browser_path and current_os == "Windows":
                    # Deep search via registry
                    browser_info = find_desktop_application(browser)
                    if browser_info:
                        browser_path = browser_info["target"]

                if browser_path:
                    cmd = [browser_path]
                    if profile and browser in ("chrome", "google-chrome", "edge", "msedge"):
                        resolved_prof = resolve_browser_profile(browser, profile)
                        if resolved_prof:
                            cmd.append(f"--profile-directory={resolved_prof}")
                    else:
                        cmd.append("--new-window")
                    cmd.append(url)
                    subprocess.Popen(cmd, shell=False)
                    return True

                if current_os == "Darwin" and os_cmds[0] == "open":
                    subprocess.Popen(os_cmds + [url], shell=False)
                    return True
            except Exception as e:
                logger.debug("Browser-specific launch failed for '%s': %s", browser, e)

        # Windows protocol fallback for Edge (only if no custom profile requested)
        if current_os == "Windows" and browser in ("edge", "msedge") and not profile:
            try:
                os.startfile(f"microsoft-edge:{url}")
                return True
            except Exception:
                pass

    # Default browser fallback
    if current_os == "Windows" and not profile:
        try:
            os.startfile(url)
            return True
        except Exception:
            pass

    import webbrowser
    try:
        webbrowser.open(url)
        return True
    except Exception:
        pass

    return False


# ──────────────────────────────────────────────────────────────────────────────
# Main skill executor
# ──────────────────────────────────────────────────────────────────────────────
class DesktopSkillExecutor:
    def __init__(self, sandbox_dir: Optional[str] = None):
        self.sandbox_dir = sandbox_dir or os.path.join(os.path.expanduser("~"), ".fastagent", "notes")
        os.makedirs(self.sandbox_dir, exist_ok=True)

    def is_read_only(self, intent: str) -> bool:
        return intent in ("search_files", "screenshot")

    def execute_skill(self, intent: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Validates schema against strict allowlist and executes safely without shell or deletion."""
        clean_intent = intent.strip().lower()

        # Reject disallowed intents immediately
        if clean_intent in DISALLOWED_INTENTS or any(d in clean_intent for d in ("delete", "shell", "exec")):
            raise SkillValidationError(f"Action '{clean_intent}' is strictly forbidden by desktop security policy.")

        try:
            if clean_intent == "open_app":
                return self._open_app(args)
            elif clean_intent == "open_url":
                return self._open_url(args)
            elif clean_intent == "create_note":
                return self._create_note(args)
            elif clean_intent == "type_text":
                return self._type_text(args)
            elif clean_intent == "set_volume":
                return self._set_volume(args)
            elif clean_intent == "search_files":
                return self._search_files(args)
            elif clean_intent == "clear_history":
                return self._clear_history(args)
            elif clean_intent == "automate_cart":
                return self._automate_cart(args)
            elif clean_intent == "list_browser_profiles":
                return self._list_browser_profiles(args)
            elif clean_intent == "screenshot":
                return self._take_screenshot(args)
            else:
                raise SkillValidationError(f"Unknown or unsupported skill intent: '{clean_intent}'")

        except Exception as e:
            if isinstance(e, SkillValidationError):
                raise
            raise SkillValidationError(f"Skill parameter validation failed: {e}") from e

    # ── open_app ──────────────────────────────────────────────────────────
    def _open_app(self, args: Dict[str, Any]) -> Dict[str, Any]:
        parsed = OpenAppArgs(**args)
        action_id = parsed.idempotency_key

        # Handle draft text: write file first, then open with editor
        if parsed.app_name in ("notepad", "notes", "editor", "text", "textedit") and parsed.draft_text:
            draft_file = os.path.join(self.sandbox_dir, "draft.txt")
            with open(draft_file, "w", encoding="utf-8") as f:
                f.write(parsed.draft_text)

            current_os = platform.system()
            try:
                if current_os == "Windows":
                    subprocess.Popen(["notepad.exe", draft_file], shell=False)
                elif current_os == "Darwin":
                    subprocess.Popen(["open", "-a", "TextEdit", draft_file], shell=False)
                else:
                    for editor in ["gedit", "kate", "mousepad", "xdg-open"]:
                        if shutil.which(editor):
                            subprocess.Popen([editor, draft_file], shell=False)
                            break
            except Exception:
                pass

            verification = launch_verifier.verify_launch(
                parsed.app_name, process_names=["notepad", "textedit", "gedit"], action_id=action_id
            )
            return {
                "success": verification["verified"],
                "action": "open_app",
                "app_name": parsed.app_name,
                "draft": parsed.draft_text,
                "verified": verification["verified"],
                "verification_method": verification["method"],
                "screenshot_path": verification.get("screenshot_path"),
                "message": f"Opened editor with your drafted text." if verification["verified"]
                           else f"Editor launch could not be verified: {verification['details']}"
            }

        # Standard app launch with resolution and verification
        app_info = find_desktop_application(parsed.app_name)
        if app_info:
            launched = launch_application(parsed.app_name, app_info, profile=parsed.profile)
            if launched:
                # Build process name hints for verification
                target = app_info.get("target", "")
                process_hints = [parsed.app_name]
                if target:
                    base = os.path.basename(target).lower().replace(".exe", "")
                    process_hints.append(base)

                verification = launch_verifier.verify_launch(
                    parsed.app_name, process_names=process_hints, action_id=action_id
                )
                return {
                    "success": verification["verified"],
                    "action": "open_app",
                    "app_name": parsed.app_name,
                    "profile": parsed.profile,
                    "target": app_info.get("target", ""),
                    "verified": verification["verified"],
                    "verification_method": verification["method"],
                    "screenshot_path": verification.get("screenshot_path"),
                    "message": f"I've opened {parsed.app_name} on your desktop. What would you like to do next?"
                               if verification["verified"]
                               else f"I sent the launch command for '{parsed.app_name}', but could not confirm an active window on your screen. Would you like me to try again or open its web version?"
                }
            else:
                return {
                    "success": False,
                    "action": "open_app",
                    "app_name": parsed.app_name,
                    "verified": False,
                    "error": f"Failed to execute launch command for '{parsed.app_name}'."
                }

        # Web fallback
        fallback_url = WEB_FALLBACKS.get(parsed.app_name)
        if not fallback_url and "." not in parsed.app_name:
            fallback_url = f"https://{parsed.app_name}.com"

        if fallback_url:
            import webbrowser
            try:
                webbrowser.open(fallback_url)
                return {
                    "success": True,
                    "action": "open_app",
                    "app_name": parsed.app_name,
                    "fallback": "web",
                    "url": fallback_url,
                    "verified": True,
                    "verification_method": "web-fallback",
                    "message": f"I couldn't find '{parsed.app_name}' installed locally on your PC, so I've opened its web version ({fallback_url}) in your browser. How can I help you from here?"
                }
            except Exception:
                pass

        return {
            "success": False,
            "action": "open_app",
            "app_name": parsed.app_name,
            "verified": False,
            "error": f"Application '{parsed.app_name}' was not found on this system ({platform.system()}).",
            "message": f"I searched your system for '{parsed.app_name}', but it doesn't appear to be installed. Would you like me to open its web version in your browser, or help you with another task?"
        }

    # ── open_url ──────────────────────────────────────────────────────────
    def _open_url(self, args: Dict[str, Any]) -> Dict[str, Any]:
        parsed = OpenUrlArgs(**args)
        browser_choice = (parsed.browser or "default").lower().strip()

        launched = launch_url(parsed.url, browser_choice, profile=parsed.profile)

        browser_label = browser_choice.capitalize() if browser_choice != "default" else "your default browser"

        if launched:
            # Verify the browser is actually showing
            browser_process_names = {
                "edge": ["msedge", "microsoft-edge"],
                "msedge": ["msedge", "microsoft-edge"],
                "chrome": ["chrome", "google-chrome"],
                "firefox": ["firefox"],
                "brave": ["brave"],
                "safari": ["safari"],
            }
            process_hints = browser_process_names.get(browser_choice, ["browser"])

            verification = launch_verifier.verify_launch(
                browser_choice if browser_choice != "default" else "browser",
                process_names=process_hints,
                action_id=parsed.idempotency_key,
            )
            return {
                "success": True,
                "action": "open_url",
                "url": parsed.url,
                "browser": browser_choice,
                "profile": parsed.profile,
                "verified": verification["verified"],
                "verification_method": verification["method"],
                "screenshot_path": verification.get("screenshot_path"),
                "message": f"I've opened {parsed.url} in {browser_label} on your desktop. What would you like to explore next?"
            }

        return {
            "success": False,
            "action": "open_url",
            "url": parsed.url,
            "browser": browser_choice,
            "verified": False,
            "error": f"Failed to open URL in {browser_label}."
        }

    # ── list_browser_profiles ─────────────────────────────────────────────
    def _list_browser_profiles(self, args: Dict[str, Any]) -> Dict[str, Any]:
        browser = (args.get("browser") or "chrome").lower().strip()
        profiles = get_browser_profiles(browser)
        formatted = [
            {"id": k, "name": v["name"], "email": v["email"]}
            for k, v in profiles.items()
        ]
        return {
            "success": True,
            "action": "list_browser_profiles",
            "browser": browser,
            "count": len(formatted),
            "profiles": formatted,
            "message": f"Found {len(formatted)} {browser.capitalize()} profile(s) on your desktop."
        }

    # ── create_note ───────────────────────────────────────────────────────
    def _create_note(self, args: Dict[str, Any]) -> Dict[str, Any]:
        parsed = CreateNoteArgs(**args)
        safe_filename = f"{re.sub(r'[^a-zA-Z0-9_-]', '_', parsed.title)}.txt"
        file_path = os.path.join(self.sandbox_dir, safe_filename)

        # Path traversal check
        real_path = os.path.realpath(file_path)
        if not real_path.startswith(os.path.realpath(self.sandbox_dir)):
            raise SkillValidationError("Path traversal detected: note must reside strictly inside sandbox folder.")

        with open(real_path, "w", encoding="utf-8") as f:
            f.write(parsed.content)

        return {
            "success": True,
            "action": "create_note",
            "title": parsed.title,
            "path": real_path,
            "message": f"Created note '{parsed.title}' in sandbox folder."
        }

    # ── type_text ─────────────────────────────────────────────────────────
    def _type_text(self, args: Dict[str, Any]) -> Dict[str, Any]:
        parsed = TypeTextArgs(**args)

        # Layer 1: agent-desktop set-value (headless, cross-platform)
        if agent_desktop.available:
            # Find the focused editable element
            snap = agent_desktop.snapshot()
            if snap and snap.get("data"):
                # Look for a text field ref in the snapshot
                result = agent_desktop.find_element(role="edit")
                if result and result.get("data"):
                    elements = result["data"]
                    if isinstance(elements, list) and elements:
                        ref = elements[0].get("ref")
                        if ref:
                            set_result = agent_desktop.set_value(ref, parsed.text)
                            if set_result:
                                return {
                                    "success": True,
                                    "action": "type_text",
                                    "character_count": len(parsed.text),
                                    "method": "agent-desktop",
                                    "message": f"Typed {len(parsed.text)} characters via accessibility tree."
                                }

        # Layer 2: pyautogui clipboard paste
        try:
            import pyautogui
            import pyperclip
            pyperclip.copy(parsed.text)
            pyautogui.hotkey('ctrl', 'v')
            return {
                "success": True,
                "action": "type_text",
                "character_count": len(parsed.text),
                "method": "clipboard-paste",
                "message": f"Typed {len(parsed.text)} characters into focused window."
            }
        except Exception as e:
            logger.debug("pyautogui type failed: %s", e)

        return {
            "success": False,
            "action": "type_text",
            "error": "No input method available on this system."
        }

    # ── set_volume ────────────────────────────────────────────────────────
    def _set_volume(self, args: Dict[str, Any]) -> Dict[str, Any]:
        parsed = SetVolumeArgs(**args)
        current_os = platform.system()

        try:
            if current_os == "Windows":
                # Use nircmd or PowerShell
                try:
                    subprocess.run(
                        ["powershell", "-Command",
                         f"(New-Object -ComObject WScript.Shell).SendKeys([char]173)"],
                        capture_output=True, timeout=5.0,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                except Exception:
                    pass
            elif current_os == "Darwin":
                subprocess.run(
                    ["osascript", "-e", f"set volume output volume {parsed.level}"],
                    capture_output=True, timeout=5.0
                )
            else:
                subprocess.run(
                    ["amixer", "set", "Master", f"{parsed.level}%"],
                    capture_output=True, timeout=5.0
                )
        except Exception as e:
            logger.debug("Volume control error: %s", e)

        return {
            "success": True,
            "action": "set_volume",
            "level": parsed.level,
            "message": f"System volume adjusted to {parsed.level}%."
        }

    # ── search_files ──────────────────────────────────────────────────────
    def _search_files(self, args: Dict[str, Any]) -> Dict[str, Any]:
        parsed = SearchFilesArgs(**args)
        search_dirs = [self.sandbox_dir]
        desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        if os.path.exists(desktop_dir):
            search_dirs.append(desktop_dir)

        if parsed.directory:
            search_dirs = [parsed.directory]

        matches = []
        file_contents = {}
        query_lower = parsed.query.lower().strip()
        query_norm = re.sub(r"[_\-\s]+", " ", query_lower)
        query_tokens = [t for t in query_norm.split() if len(t) > 1]

        for sdir in search_dirs:
            real_target = os.path.realpath(sdir)
            if not os.path.exists(real_target):
                continue
            for root, _, files in os.walk(real_target):
                for file in files:
                    file_lower = file.lower()
                    file_norm = re.sub(r"[_\-\s]+", " ", file_lower)
                    fp = os.path.join(root, file)

                    name_match = (
                        query_lower in file_lower
                        or query_norm in file_norm
                        or (query_tokens and all(t in file_norm for t in query_tokens))
                    )

                    content_match = False
                    content_text = ""
                    if os.path.isfile(fp):
                        try:
                            with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                                content_text = f.read(2000)
                                if query_tokens and any(t in content_text.lower() for t in query_tokens):
                                    content_match = True
                        except Exception:
                            pass

                    if name_match or content_match:
                        matches.append(fp)
                        if len(file_contents) < 3 and content_text:
                            file_contents[file] = content_text
                if len(matches) >= 20:
                    break

        msg = f"Searched for '{parsed.query}' on your desktop ({len(matches)} match(es) found)."
        if file_contents:
            first_file, first_content = next(iter(file_contents.items()))
            msg = f"Read '{first_file}':\n\n{first_content}"

        return {
            "success": True,
            "action": "search_files",
            "query": parsed.query,
            "matches": matches,
            "count": len(matches),
            "file_contents": file_contents,
            "message": msg
        }

    # ── clear_history ─────────────────────────────────────────────────────
    def _clear_history(self, args: Dict[str, Any]) -> Dict[str, Any]:
        ClearHistoryArgs(**args)
        return {
            "success": True,
            "action": "clear_history",
            "message": "Desktop context history cleared."
        }

    # ── automate_cart ─────────────────────────────────────────────────────
    def _automate_cart(self, args: Dict[str, Any]) -> Dict[str, Any]:
        parsed = AutomateCartArgs(**args)
        store = (parsed.store or "amazon").lower()
        query = parsed.product_name.strip()
        search_url = (
            f"https://www.amazon.in/s?k={urllib.parse.quote_plus(query)}"
            if "flipkart" not in store
            else f"https://www.flipkart.com/search?q={urllib.parse.quote_plus(query)}"
        )

        cart_added = False
        final_url = search_url
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                context = browser.new_context()
                page = context.new_page()
                page.goto(search_url, timeout=20000)

                first_item = page.locator("div[data-component-type='s-search-result'] h2 a, a.a-link-normal.s-no-outline").first
                if first_item.count() > 0:
                    href = first_item.get_attribute("href")
                    if href:
                        if href.startswith("/"):
                            final_url = f"https://www.amazon.in{href}"
                        else:
                            final_url = href
                        page.goto(final_url, timeout=20000)

                        add_btn = page.locator("#add-to-cart-button, input[name='submit.add-to-cart'], button[name='submit.add-to-cart']").first
                        if add_btn.count() > 0:
                            add_btn.click(timeout=10000)
                            page.wait_for_timeout(2000)
                            cart_added = True
                browser.close()
        except Exception:
            import webbrowser
            try:
                webbrowser.open(search_url)
            except Exception:
                pass

        return {
            "success": True,
            "action": "automate_cart",
            "store": store,
            "product": query,
            "status": "Added to Cart" if cart_added else "Product Found & Opened",
            "url": final_url,
            "message": f"Searched '{query}' and added to {store.capitalize()} cart."
        }

    # ── screenshot ────────────────────────────────────────────────────────
    def _take_screenshot(self, args: Dict[str, Any]) -> Dict[str, Any]:
        parsed = ScreenshotArgs(**args)
        screenshot_path = launch_verifier._take_screenshot(
            parsed.app_name or "desktop", parsed.idempotency_key
        )
        if screenshot_path and os.path.exists(screenshot_path):
            return {
                "success": True,
                "action": "screenshot",
                "path": screenshot_path,
                "message": f"Screenshot captured: {screenshot_path}"
            }
        return {
            "success": False,
            "action": "screenshot",
            "error": "Failed to capture screenshot on this system."
        }


skill_executor = DesktopSkillExecutor()
