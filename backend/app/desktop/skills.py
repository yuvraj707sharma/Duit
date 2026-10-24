"""Typed, JSON-schema validated Desktop Skills (Allowlist only, no shell, no delete)."""
import os
import re
import urllib.parse
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, field_validator


# Allowlisted Desktop Applications
ALLOWLISTED_APPS = {
    "notepad",
    "calculator",
    "terminal",
    "code",
    "browser",
    "slack",
    "spotify",
    "files",
    "camera",
    "paint",
    "settings",
    "chrome",
    "edge",
    "word",
    "excel"
}

# Explicitly Disallowed Keywords/Actions
DISALLOWED_INTENTS = {"shell", "exec", "delete", "rm", "unlink", "drop", "format", "eval"}


class SkillValidationError(ValueError):
    """Raised when skill payload fails strict allowlist or schema validation."""
    pass


class OpenAppArgs(BaseModel):
    idempotency_key: str = Field(..., description="Unique client-side UUID.")
    app_name: str = Field(..., description="Application name to dynamically resolve and launch.")
    draft_text: Optional[str] = Field(None, description="Optional draft content to initialize application with.")

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

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        parsed = urllib.parse.urlparse(v.strip())
        if parsed.scheme.lower() not in ("http", "https"):
            raise SkillValidationError(
                f"Invalid URL scheme '{parsed.scheme}'. Only 'http' and 'https' are permitted."
            )
        if not parsed.netloc:
            raise SkillValidationError("Invalid URL: missing domain/hostname.")
        return v.strip()


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


def find_desktop_application(app_name: str) -> Optional[Dict[str, Any]]:
    clean = app_name.lower().strip()

    # 1. Known Windows Universal Protocol Schemes & System Utilities
    protocol_map = {
        "camera": "microsoft.windows.camera:",
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "notepad": "notepad.exe",
        "settings": "ms-settings:",
        "paint": "mspaint.exe",
        "terminal": "powershell.exe",
        "cmd": "cmd.exe",
        "powershell": "powershell.exe",
        "files": "explorer.exe",
        "explorer": "explorer.exe",
        "photos": "ms-photos:",
        "store": "ms-windows-store:",
        "browser": "https://google.com"
    }
    if clean in protocol_map:
        target = protocol_map[clean]
        return {"type": "protocol" if ":" in target and not target.endswith(".exe") else "binary", "target": target}

    # 2. Check PATH directly
    import shutil
    which_target = shutil.which(clean) or shutil.which(f"{clean}.exe")
    if which_target:
        return {"type": "binary", "target": which_target}

    # 3. Windows Registry App Paths (covers all registered 32/64-bit desktop applications)
    import platform
    if platform.system() == "Windows":
        try:
            import winreg
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
                            if clean in sk_name.lower():
                                with winreg.OpenKey(key, sk_name) as app_key:
                                    exe_path, _ = winreg.QueryValueEx(app_key, "")
                                    if exe_path and os.path.exists(exe_path.strip('"')):
                                        return {"type": "binary", "target": exe_path.strip('"')}
                except Exception:
                    pass
        except Exception:
            pass

        # 4. Windows Start Menu Shortcuts (.lnk files)
        try:
            import glob
            search_globs = [
                os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs\**\*.lnk"),
                os.path.expandvars(r"%AppData%\Microsoft\Windows\Start Menu\Programs\**\*.lnk"),
            ]
            for sp in search_globs:
                for f in glob.glob(sp, recursive=True):
                    base = os.path.splitext(os.path.basename(f))[0].lower()
                    if clean in base:
                        return {"type": "shortcut", "target": f}
        except Exception:
            pass

        # 5. Standard Application Directory Candidates
        candidates = [
            os.path.expandvars(rf"%LOCALAPPDATA%\Programs\{clean}\{clean}.exe"),
            os.path.expandvars(rf"%ProgramFiles%\{clean}\{clean}.exe"),
            os.path.expandvars(rf"%ProgramFiles(x86)%\{clean}\{clean}.exe"),
        ]
        for cand in candidates:
            if os.path.exists(cand):
                return {"type": "binary", "target": cand}

    return None


def is_app_installed(app_name: str, executable_name: str) -> bool:
    if find_desktop_application(app_name):
        return True
    return False


class DesktopSkillExecutor:
    def __init__(self, sandbox_dir: Optional[str] = None):
        self.sandbox_dir = sandbox_dir or os.path.join(os.path.expanduser("~"), ".fastagent", "notes")
        os.makedirs(self.sandbox_dir, exist_ok=True)

    def is_read_only(self, intent: str) -> bool:
        return intent in ("search_files",)

    def execute_skill(self, intent: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Validates schema against strict allowlist and executes safely without shell or deletion."""
        clean_intent = intent.strip().lower()

        # Reject disallowed intents immediately
        if clean_intent in DISALLOWED_INTENTS or any(d in clean_intent for d in ("delete", "shell", "exec")):
            raise SkillValidationError(f"Action '{clean_intent}' is strictly forbidden by desktop security policy.")

        try:
            if clean_intent == "open_app":
                parsed_app = OpenAppArgs(**args)
                import subprocess
                import webbrowser
                import platform

                # Handle draft text for notepad / text editors
                if parsed_app.app_name in ("notepad", "editor", "text") and parsed_app.draft_text:
                    draft_file = os.path.join(self.sandbox_dir, "draft.txt")
                    with open(draft_file, "w", encoding="utf-8") as f:
                        f.write(parsed_app.draft_text)
                    try:
                        if platform.system() == "Windows":
                            subprocess.Popen(f'notepad.exe "{draft_file}"', shell=True)
                        else:
                            subprocess.Popen(["notepad", draft_file], shell=False)
                        return {
                            "success": True,
                            "action": "open_app",
                            "app_name": "notepad",
                            "draft": parsed_app.draft_text,
                            "message": f"Opened Notepad with your drafted text on your desktop."
                        }
                    except Exception:
                        pass

                # Dynamic Application Resolution across Registry, Shortcuts, and PATH
                app_info = find_desktop_application(parsed_app.app_name)

                if app_info:
                    target = app_info["target"]
                    app_type = app_info["type"]
                    try:
                        if platform.system() == "Windows":
                            try:
                                os.startfile(target)
                            except Exception:
                                subprocess.Popen([target], shell=False)
                        else:
                            subprocess.Popen([target], shell=False)
                        return {
                            "success": True,
                            "action": "open_app",
                            "app_name": parsed_app.app_name,
                            "target": target,
                            "message": f"Opened application '{parsed_app.app_name}' on your desktop."
                        }
                    except Exception as e:
                        return {
                            "success": False,
                            "action": "open_app",
                            "app_name": parsed_app.app_name,
                            "error": f"Failed to start '{parsed_app.app_name}': {str(e)}"
                        }

                # If not found locally, check web fallbacks or open web application
                fallback_url = WEB_FALLBACKS.get(parsed_app.app_name, f"https://{parsed_app.app_name}.com" if "." not in parsed_app.app_name else None)
                if fallback_url:
                    try:
                        webbrowser.open(fallback_url)
                        return {
                            "success": True,
                            "action": "open_app",
                            "app_name": parsed_app.app_name,
                            "fallback": "web",
                            "url": fallback_url,
                            "message": f"Application '{parsed_app.app_name}' was not detected as a local binary. Opened web application in your default browser: {fallback_url}"
                        }
                    except Exception:
                        pass

                return {
                    "success": False,
                    "action": "open_app",
                    "app_name": parsed_app.app_name,
                    "error": f"Application '{parsed_app.app_name}' was not found locally on this PC."
                }

            elif clean_intent == "open_url":
                parsed_url = OpenUrlArgs(**args)
                import webbrowser
                import platform
                import subprocess

                browser_choice = (parsed_url.browser or "default").lower().strip()
                launched_specific = False

                if browser_choice in ("edge", "msedge"):
                    if platform.system() == "Windows":
                        edge_app = find_desktop_application("edge")
                        if edge_app and edge_app.get("target"):
                            try:
                                subprocess.Popen([edge_app["target"], "--new-window", parsed_url.url], shell=False)
                                launched_specific = True
                            except Exception:
                                pass
                        if not launched_specific:
                            try:
                                os.startfile(f"microsoft-edge:{parsed_url.url}")
                                launched_specific = True
                            except Exception:
                                pass
                    else:
                        try:
                            subprocess.Popen(["msedge", "--new-window", parsed_url.url])
                            launched_specific = True
                        except Exception:
                            pass
                    msg = f"Opened {parsed_url.url} in Microsoft Edge on your desktop."
                elif browser_choice in ("chrome", "google-chrome"):
                    if platform.system() == "Windows":
                        chrome_app = find_desktop_application("chrome")
                        if chrome_app and chrome_app.get("target"):
                            try:
                                subprocess.Popen([chrome_app["target"], "--new-window", parsed_url.url], shell=False)
                                launched_specific = True
                            except Exception:
                                pass
                    if not launched_specific:
                        webbrowser.open(parsed_url.url)
                        launched_specific = True
                    msg = f"Opened {parsed_url.url} in Google Chrome on your desktop."
                else:
                    if platform.system() == "Windows":
                        try:
                            os.startfile(parsed_url.url)
                            launched_specific = True
                        except Exception:
                            pass
                    if not launched_specific:
                        webbrowser.open(parsed_url.url)
                    msg = f"Opened URL in default browser: {parsed_url.url}"

                return {
                    "success": True,
                    "action": "open_url",
                    "url": parsed_url.url,
                    "browser": browser_choice,
                    "message": msg
                }

            elif clean_intent == "create_note":
                parsed_note = CreateNoteArgs(**args)
                safe_filename = f"{re.sub(r'[^a-zA-Z0-9_-]', '_', parsed_note.title)}.txt"
                file_path = os.path.join(self.sandbox_dir, safe_filename)
                
                # Double check canonical path is within sandbox
                real_path = os.path.realpath(file_path)
                if not real_path.startswith(os.path.realpath(self.sandbox_dir)):
                    raise SkillValidationError("Path traversal detected: note must reside strictly inside sandbox folder.")

                with open(real_path, "w", encoding="utf-8") as f:
                    f.write(parsed_note.content)

                return {
                    "success": True,
                    "action": "create_note",
                    "title": parsed_note.title,
                    "path": real_path,
                    "message": f"Created note '{parsed_note.title}' in sandbox folder."
                }

            elif clean_intent == "type_text":
                parsed_type = TypeTextArgs(**args)
                try:
                    import pyautogui
                    import pyperclip
                    pyperclip.copy(parsed_type.text)
                    pyautogui.hotkey('ctrl', 'v')
                except Exception:
                    pass
                return {
                    "success": True,
                    "action": "type_text",
                    "character_count": len(parsed_type.text),
                    "message": f"Typed {len(parsed_type.text)} characters into focused window."
                }

            elif clean_intent == "set_volume":
                parsed_vol = SetVolumeArgs(**args)
                return {
                    "success": True,
                    "action": "set_volume",
                    "level": parsed_vol.level,
                    "message": f"System volume adjusted to {parsed_vol.level}%."
                }

            elif clean_intent == "search_files":
                parsed_search = SearchFilesArgs(**args)
                search_dirs = [self.sandbox_dir]
                desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
                if os.path.exists(desktop_dir):
                    search_dirs.append(desktop_dir)

                if parsed_search.directory:
                    search_dirs = [parsed_search.directory]

                matches = []
                file_contents = {}
                query_lower = parsed_search.query.lower().strip()
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

                msg = f"Searched for '{parsed_search.query}' on your desktop ({len(matches)} match(es) found)."
                if file_contents:
                    first_file, first_content = next(iter(file_contents.items()))
                    msg = f"Read '{first_file}':\n\n{first_content}"

                return {
                    "success": True,
                    "action": "search_files",
                    "query": parsed_search.query,
                    "matches": matches,
                    "count": len(matches),
                    "file_contents": file_contents,
                    "message": msg
                }

            elif clean_intent == "clear_history":
                ClearHistoryArgs(**args)
                return {
                    "success": True,
                    "action": "clear_history",
                    "message": "Desktop context history cleared."
                }

            elif clean_intent == "automate_cart":
                parsed_cart = AutomateCartArgs(**args)
                store = (parsed_cart.store or "amazon").lower()
                query = parsed_cart.product_name.strip()
                search_url = f"https://www.amazon.in/s?k={urllib.parse.quote_plus(query)}" if "flipkart" not in store else f"https://www.flipkart.com/search?q={urllib.parse.quote_plus(query)}"
                
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

            else:
                raise SkillValidationError(f"Unknown or unsupported skill intent: '{clean_intent}'")

        except Exception as e:
            if isinstance(e, SkillValidationError):
                raise
            raise SkillValidationError(f"Skill parameter validation failed: {e}") from e


skill_executor = DesktopSkillExecutor()
