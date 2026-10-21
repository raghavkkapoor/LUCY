import base64
import json
import os
import queue
import re
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog
from utils.constants import KEY, SYSTEM_PROMPT

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from openai import AuthenticationError, OpenAI


HISTORY_FILE = PROJECT_DIR / "lucy_latest_python" / "gpt_history.jsonl"
SCREENSHOT_DIR = PROJECT_DIR / "lucy_latest_python" / "gpt_screenshots"
GENERATED_IMAGE_DIR = PROJECT_DIR / "lucy_latest_python" / "gpt_generated_images"
SKILLS_DIR = PROJECT_DIR / "lucy_latest_python" / "skills"
MODEL = "gpt-6-luna"
MODEL_LABEL = MODEL.replace("-", " ").title().replace("Gpt", "GPT")
API_KEY_ERROR_STATUS = "API key invalid or expired · update it in utils/constants.py"
MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024
IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
IMAGE_CONVERT_TO_JPEG_EXTENSIONS = {".heic", ".heif", ".tif", ".tiff"}
FILE_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
}
MAX_VISIBLE_RESULTS = 2 # ui shit
MAX_CONTEXT_RESULTS = 2 # more means increased token usage, latency but better context awareness and accuracy.
SCRIPT_TIMEOUT = 60
VIEWING_OVERLAY_DURATION_MS = 1500
VIEWING_OVERLAY_FRAME_MS = 50
VIEWING_OVERLAY_MAX_ALPHA = 1.0
VIEWING_OVERLAY_EDGE_WIDTH = 10
VIEWING_OVERLAY_TOP_EDGE_OFFSET = 40
VIEWING_OVERLAY_OUTER_COLOR = "#07365B"
VIEWING_OVERLAY_INNER_COLOR = "#38B6FF"
VIEWING_OVERLAY_CLICK_THROUGH = True
API_TOOLS = [
    {"type": "web_search"},
    # {"type": "code_interpreter", "container": {"type": "auto", "memory_limit": "4g"}},
    {"type": "image_generation", "model": "gpt-image-2.5-sunburst"},
]

def read_history():
    records = []
    try:
        history_text = HISTORY_FILE.read_text(encoding="utf-8")
        json_text = "\n".join(
            line for line in history_text.splitlines()
            if not line.lstrip().startswith("#")
        )
        decoder = json.JSONDecoder()
        position = 0
        while position < len(json_text):
            while position < len(json_text) and json_text[position].isspace():
                position += 1
            if position >= len(json_text):
                break
            try:
                record, position = decoder.raw_decode(json_text, position)
            except json.JSONDecodeError:
                break
            if record.get("user") and "assistant" in record:
                records.append(record)
    except OSError:
        pass
    return records


def matching_conversations(query):
    terms = re.findall(r"[a-z0-9]+", query.casefold())
    if not terms:
        return []
    matches = []
    for record in reversed(read_history()):
        user_text = str(record.get("user", ""))
        assistant_text = str(record.get("assistant", ""))
        combined = f"{user_text}\n{assistant_text}"
        searchable = combined.casefold()
        matched_terms = [
            term for term in terms
            if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", searchable)
            or (len(term) >= 4 and term in searchable)
        ]
        if matched_terms:
            snippet_term = max(matched_terms, key=lambda term: len(term))
            matches.append({
                "user": user_text,
                "assistant": assistant_text,
                "snippet": make_snippet(combined, snippet_term),
                "match_count": len(set(matched_terms)),
            })
    matches.sort(key=lambda match: match["match_count"], reverse=True)
    return matches


def make_snippet(text, query, radius=48):
    index = text.casefold().find(query.casefold())
    if index < 0:
        return text[:radius * 2].strip()
    start = max(0, index - radius)
    end = min(len(text), index + len(query) + radius)
    snippet = text[start:end].replace("\n", " ").strip()
    return ("…" if start else "") + snippet + ("…" if end < len(text) else "")


def extract_script(text):
    script = text.strip()
    fenced = re.fullmatch(r"```(?:zsh|bash|sh)?\s*\n?(.*?)\n?```", script, re.DOTALL)
    if fenced:
        script = fenced.group(1).strip()
    return script


def run_script_in_background(script, timeout=SCRIPT_TIMEOUT):
    executable_script = (
        f"export PATH={shlex.quote(str(SKILLS_DIR))}:$PATH\n"
        f"{script}"
    )
    try:
        completed = subprocess.run(
            ["/bin/zsh", "-lc", executable_script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        if completed.returncode:
            output += f"\nCommand exited with status {completed.returncode}."
        return output.strip() or "Command finished with no output."
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        output = str(stdout) + str(stderr)
        return (output + f"\nCommand timed out after {timeout} seconds.").strip()


def capture_screenshot():
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"screen_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
    subprocess.run(["screencapture", "-x", str(path)], check=True, timeout=30)
    return path


def save_generated_images(response, task_id, cycle_number):
    saved_paths = []
    for index, item in enumerate(getattr(response, "output", []), start=1):
        if getattr(item, "type", None) != "image_generation_call":
            continue
        image_result = getattr(item, "result", None)
        if not image_result:
            continue
        GENERATED_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        path = GENERATED_IMAGE_DIR / f"lucy_{task_id[:8]}_cycle_{cycle_number}_{index}.png"
        path.write_bytes(base64.b64decode(image_result))
        saved_paths.append(path)
    return saved_paths


def create_quicklook_preview(path):
    try:
        with tempfile.TemporaryDirectory(prefix="lucy-file-preview-") as preview_dir:
            subprocess.run(
                ["/usr/bin/qlmanage", "-t", "-s", "180", "-o", preview_dir, str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=12,
                check=False,
            )
            previews = sorted(Path(preview_dir).glob("*.png"))
            return previews[0].read_bytes() if previews else None
    except (OSError, subprocess.SubprocessError):
        return None


def make_attachment_content(path):
    extension = path.suffix.casefold()
    mime_type = IMAGE_MIME_TYPES.get(extension)
    if extension in IMAGE_CONVERT_TO_JPEG_EXTENSIONS:
        with tempfile.TemporaryDirectory(prefix="lucy-image-input-") as conversion_dir:
            converted_path = Path(conversion_dir) / f"{path.stem}.jpg"
            subprocess.run(
                ["sips", "-s", "format", "jpeg", str(path), "--out", str(converted_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
                check=True,
            )
            encoded_file = base64.b64encode(converted_path.read_bytes()).decode("ascii")
        mime_type = "image/jpeg"
    elif mime_type:
        encoded_file = base64.b64encode(path.read_bytes()).decode("ascii")
    if mime_type:
        return {
            "type": "input_image",
            "image_url": f"data:{mime_type};base64,{encoded_file}",
            "detail": "auto",
        }

    mime_type = FILE_MIME_TYPES.get(extension)
    if mime_type:
        encoded_file = base64.b64encode(path.read_bytes()).decode("ascii")
        content = {
            "type": "input_file",
            "filename": path.name,
            "file_data": f"data:{mime_type};base64,{encoded_file}",
        }
        if extension == ".pdf":
            content["detail"] = "auto"
        return content

    raise ValueError(f"Unsupported attachment type: {path.suffix or path.name}")


def create_standalone_skill(client, task_id, original_prompt, context=None):
    task_cycles = [
        record for record in read_history()
        if record.get("task_id") == task_id and record.get("cycle") is not None
    ]
    final_cycle = task_cycles[-1] if task_cycles else None
    last_command = next(
        (
            record for record in reversed(task_cycles)
            if record.get("status") == "command_finished" and record.get("assistant")
        ),
        None,
    )
    if final_cycle is None or final_cycle.get("lucy_message") != "lucy_done_3030":
        raise RuntimeError("The task was not marked complete and verified.")
    if last_command is None:
        raise RuntimeError("No successful command cycle was available to turn into a script.")

    context_text = "\n".join(
        f"user: {item.get('user', '')}\nassistant: {item.get('assistant', '')}"
        for item in (context or [])
    ) or "(no matched conversational context)"
    internal_prompt = (
        "Create a standalone, fully self-contained macOS zsh script that captures the "
        "repeatable task described by the user's request and any supplied conversational "
        "context. The goal is to save a task that is likely to come up again so Lucy can "
        "call this script by name with suitable arguments instead of regenerating it. "
        "Use the verified command and its output below as evidence for the working steps. "
        "Do not make the script depend on a screenshot or visual state unless the task "
        "itself inherently requires it. Consolidate the task into a direct script; do not add an "
        "agent loop, API calls, retries, or explanatory text. Include clear checks and "
        "success or failure output. Return only the complete script, beginning with "
        "#!/bin/zsh and set -euo pipefail.\n\n"
        "User request and task context:\n"
        f"{original_prompt}\n"
        f"Matched conversation context (if relevant):\n{context_text}\n\n"
        "Most recent command cycle only (use this as execution evidence):\n"
        f"user: {last_command.get('user', original_prompt)}\n"
        f"assistant: {last_command['assistant']}\n"
        f"command output: {last_command.get('execution_output', '(not recorded)')}"
    )
    response = client.responses.create(
        model=MODEL,
        instructions="Return one standalone macOS zsh script only. No Markdown fences or prose.",
        input=internal_prompt,
        tools=[],
        store=False,
    )
    script = extract_script(response.output_text or "")
    if not script:
        raise RuntimeError("The model returned an empty standalone script.")
    if not script.startswith("#!"):
        script = "#!/bin/zsh\nset -euo pipefail\n\n" + script
    else:
        first_line, _, body = script.partition("\n")
        if "set -euo pipefail" not in body.splitlines()[:5]:
            script = f"{first_line}\nset -euo pipefail\n{body}"

    slug = re.sub(r"[^a-z0-9]+", "-", original_prompt.casefold()).strip("-")[:48].strip("-")
    filename = f"lucy-{slug or 'task'}-{task_id[:8]}.zsh"
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    script_path = SKILLS_DIR / filename
    script_path.write_text(script.rstrip() + "\n", encoding="utf-8")
    script_path.chmod(0o755)
    append_history({
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "model": MODEL,
        "task_id": task_id,
        "kind": "standalone_script",
        "user": original_prompt,
        "assistant": script,
        "skill_path": str(script_path),
        "status": "saved",
        "prompt_context": {
            "model": MODEL,
            "instructions": "Return one standalone macOS zsh script only. No Markdown fences or prose.",
            "user_input_with_context": internal_prompt,
            "tools": [],
            "store": False,
        },
    })
    return script_path


def reused_skill_for_task(task_id):
    if not SKILLS_DIR.is_dir():
        return None
    command_text = "\n".join(
        str(record.get("assistant", ""))
        for record in read_history()
        if record.get("task_id") == task_id
        and record.get("status") == "command_finished"
    )
    for script_path in SKILLS_DIR.iterdir():
        if not script_path.is_file() or not os.access(script_path, os.X_OK):
            continue
        if re.search(rf"(?<![\w.-]){re.escape(script_path.name)}(?=\s|$)", command_text):
            return script_path
    return None


class SiriOverlayApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.WIDTH_PERCENTAGE = 0.25
        self.MIN_WIDTH_PX = 500
        self.MAX_WIDTH_PX = 900
        self.MIN_HEIGHT_PX = 100
        self.RESULT_ROW_HEIGHT = 40
        self.MAX_VISIBLE_RESULTS = MAX_VISIBLE_RESULTS
        self.FIELD_COLOR = "#18202c"
        self.FIELD_TEXT_COLOR = "#ffffff"
        self.PLACEHOLDER_COLOR = "#8b96a5"
        self.PLACEHOLDER_TEXT = "Do anything on this computer!"
        self.events = queue.Queue()
        self.request_running = False
        self.task_id = None
        self.task_cycles = 0
        self._manual_size = False
        self._geometry_update = False
        self._last_size = None
        self.current_results = []
        self.result_labels = []
        self.attachments = []
        self.attachment_cards = {}
        self.result_window = None
        self.viewing_overlay = None

        self.title("Lucy [test]")
        self.attributes("-topmost", True)
        width = max(self.MIN_WIDTH_PX, min(int(self.winfo_screenwidth() * self.WIDTH_PERCENTAGE), self.MAX_WIDTH_PX))
        self.app_width = width
        self.geometry(f"{width}x{self.MIN_HEIGHT_PX}+{(self.winfo_screenwidth()-width)//2}+{int(self.winfo_screenheight()*0.70)}")
        self.bind("<Configure>", self._track_manual_resize, add="+")
        self.configure(background=self.FIELD_COLOR)
        self.grid_columnconfigure(0, weight=1)
        for row in range(5):
            self.grid_rowconfigure(row, weight=0)

        self.attachments_region = tk.Frame(self, background=self.FIELD_COLOR)
        self.attachments_region.grid(row=0, column=0, sticky="ew")
        attachment_toolbar = tk.Frame(self.attachments_region, background=self.FIELD_COLOR)
        attachment_toolbar.pack(fill="x", padx=8, pady=(2, 0))
        self.add_files_button = tk.Button(
            attachment_toolbar, text="＋ Add files", command=self.add_files,
            background="#253447", foreground=self.FIELD_TEXT_COLOR,
            activebackground="#344b63", activeforeground=self.FIELD_TEXT_COLOR,
            relief="flat", borderwidth=0, padx=10, pady=4,
            font=("Helvetica", 12),
        )
        self.add_files_button.pack(side="left")
        self.attachment_count_label = tk.Label(
            attachment_toolbar, text="", anchor="w", background=self.FIELD_COLOR,
            foreground="#aab6c5", font=("Helvetica", 11), padx=8,
        )
        self.attachment_count_label.pack(side="left")
        self.preview_canvas = tk.Canvas(
            self.attachments_region, height=88, background=self.FIELD_COLOR,
            borderwidth=0, highlightthickness=0,
        )
        self.preview_scrollbar = tk.Scrollbar(
            self.attachments_region, orient="horizontal", command=self.preview_canvas.xview,
        )
        self.preview_canvas.configure(xscrollcommand=self.preview_scrollbar.set)
        self.preview_cards_frame = tk.Frame(self.preview_canvas, background=self.FIELD_COLOR)
        self.preview_canvas_window = self.preview_canvas.create_window(
            (0, 0), window=self.preview_cards_frame, anchor="nw",
        )
        self.preview_cards_frame.bind("<Configure>", self.update_preview_scrollregion)

        self.text_box = tk.Text(
            self, background=self.FIELD_COLOR, foreground=self.FIELD_TEXT_COLOR,
            insertbackground=self.FIELD_TEXT_COLOR, selectbackground="#39506b",
            font=("Helvetica", 20), wrap="word", borderwidth=0,
            highlightthickness=0, padx=14, pady=16, insertwidth=3,
            height=1, undo=True, autoseparators=True, maxundo=-1,
        )
        self.text_box.grid(row=1, column=0, sticky="ew")
        self.placeholder_active = False
        self.status = tk.Label(self, text="", anchor="w", background=self.FIELD_COLOR,
                               foreground="#35c46a", font=("Helvetica", 16), padx=14)
        self.status.grid(row=2, column=0, sticky="ew")
        self.lucy_message = tk.Label(
            self, text="", anchor="w", justify="left", background=self.FIELD_COLOR,
            foreground=self.FIELD_TEXT_COLOR, font=("Helvetica", 16), padx=14,
            wraplength=self.app_width - 28,
        )
        self.lucy_message.grid(row=3, column=0, sticky="ew")
        self.set_status(self.ready_status_text(), "ready")

        self.results_frame = tk.Frame(self, background=self.FIELD_COLOR)
        self.results_frame.grid(row=4, column=0, sticky="ew")
        self.results_frame.grid_columnconfigure(0, weight=1)

        self.text_box.bind("<FocusIn>", self.on_focus_in)
        self.text_box.bind("<FocusOut>", self.on_focus_out)
        self.text_box.bind("<KeyPress>", self.clear_placeholder_on_keypress, add="+")
        self.text_box.bind("<<Modified>>", self.on_text_change)
        self.text_box.bind("<Return>", self.submit_prompt)
        self.text_box.bind("<Shift-Return>", self.insert_newline)
        self.text_box.bind("<Control-z>", self._undo)
        self.text_box.bind("<Control-y>", self._redo)
        self.text_box.bind("<Control-Shift-Z>", self._redo)
        self.text_box.bind("<Command-z>", self._undo)
        self.text_box.bind("<Command-Shift-Z>", self._redo)
        self.text_box.bind("<Command-y>", self._redo)
        self.text_box.edit_modified(False)
        self.show_placeholder()
        self.after(100, self.text_box.focus_force)
        self.after(100, self.process_events)
        self.after(120, self.fit_content_height)

    def fit_content_height(self):
        self.update_idletasks()
        content_height = sum(widget.winfo_reqheight() for widget in (
            self.attachments_region, self.text_box, self.status, self.lucy_message,
            self.results_frame,
        ))
        self.set_window_height(max(self.MIN_HEIGHT_PX, content_height), force=True)

    def update_preview_scrollregion(self, event=None):
        self.preview_canvas.configure(scrollregion=self.preview_canvas.bbox("all"))

    def update_attachment_preview_layout(self):
        count = len(self.attachments)
        self.attachment_count_label.configure(
            text=f"{count} attached" if count else ""
        )
        if count:
            if not self.preview_canvas.winfo_manager():
                self.preview_canvas.pack(fill="x", expand=True, padx=8, pady=(5, 0))
                self.preview_scrollbar.pack(fill="x", padx=8, pady=(0, 2))
        else:
            self.preview_canvas.pack_forget()
            self.preview_scrollbar.pack_forget()
        self.update_idletasks()
        self.fit_content_height()

    def add_files(self):
        selected = filedialog.askopenfilenames(
            parent=self,
            title="Attach files to Lucy",
            filetypes=[
                ("PDF, Word, and image files", ("*.pdf", "*.docx", "*.doc", "*.png", "*.jpg", "*.jpeg", "*.webp", "*.gif", "*.heic", "*.heif", "*.tif", "*.tiff")),
                ("All files", "*"),
            ],
        )
        if not selected:
            return

        supported_extensions = (
            set(IMAGE_MIME_TYPES) | IMAGE_CONVERT_TO_JPEG_EXTENSIONS | set(FILE_MIME_TYPES)
        )
        paths = [Path(item) for item in selected]
        unsupported = [path for path in paths if path.suffix.casefold() not in supported_extensions]
        if unsupported:
            self.set_status("Choose a PDF, Word, or supported image file", "error")
            return

        new_paths = [path for path in paths if path not in self.attachments]
        try:
            total_bytes = sum(path.stat().st_size for path in (*self.attachments, *new_paths))
        except OSError:
            self.set_status("Could not read one of the selected files", "error")
            return
        if total_bytes > MAX_ATTACHMENT_BYTES:
            self.set_status("Attachments must total less than 50 MB", "error")
            return

        for path in new_paths:
            self.add_attachment_card(path)
        self.attachments.extend(new_paths)
        self.update_attachment_preview_layout()

    def add_attachment_card(self, path):
        card = tk.Frame(
            self.preview_cards_frame, width=136, height=82,
            background="#253447", highlightbackground="#40546a", highlightthickness=1,
        )
        card.pack(side="left", padx=(0, 7), pady=2)
        card.pack_propagate(False)
        preview_label = tk.Label(
            card, text=path.suffix.lstrip(".").upper() or "FILE",
            background="#1d2937", foreground="#d4deea",
            font=("Helvetica", 10, "bold"),
        )
        preview_label.place(x=3, y=3, width=128, height=54)
        display_name = path.name if len(path.name) <= 21 else path.name[:18] + "…"
        tk.Label(
            card, text=display_name, anchor="w", background="#253447",
            foreground=self.FIELD_TEXT_COLOR, font=("Helvetica", 9),
        ).place(x=4, y=59, width=126, height=18)
        remove_button = tk.Button(
            card, text="×", command=lambda item=path: self.remove_attachment(item),
            background="#253447", foreground=self.FIELD_TEXT_COLOR,
            activebackground="#344b63", activeforeground=self.FIELD_TEXT_COLOR,
            relief="flat", borderwidth=0, padx=2, pady=0,
            font=("Helvetica", 11, "bold"),
        )
        remove_button.place(relx=1.0, x=-1, y=0, anchor="ne")
        self.attachment_cards[path] = {
            "frame": card,
            "preview": preview_label,
            "remove": remove_button,
        }

        threading.Thread(
            target=self.load_attachment_preview,
            args=(path,),
            daemon=True,
        ).start()

    def load_attachment_preview(self, path):
        preview_data = create_quicklook_preview(path)
        self.events.put(("attachment_preview", (path, preview_data)))

    def remove_attachment(self, path):
        if self.request_running:
            return
        self.attachments = [item for item in self.attachments if item != path]
        card = self.attachment_cards.pop(path, None)
        if card:
            card["frame"].destroy()
        self.update_attachment_preview_layout()

    def clear_attachments(self):
        for card in self.attachment_cards.values():
            card["frame"].destroy()
        self.attachment_cards.clear()
        self.attachments.clear()
        self.update_attachment_preview_layout()

    def set_attachment_controls_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        self.add_files_button.configure(state=state)
        for card in self.attachment_cards.values():
            card["remove"].configure(state=state)

    def on_focus_in(self, event=None):
        pass

    def on_focus_out(self, event=None):
        if not self.request_running:
            self.show_placeholder()

    def clear_placeholder_on_keypress(self, event=None):
        if self.placeholder_active:
            if event is not None and event.keysym in {"BackSpace", "Delete"}:
                return "break"
            if event is not None and not event.char:
                return
            self.clear_placeholder()

    def clear_placeholder(self):
        if not self.placeholder_active:
            return
        self.text_box.delete("1.0", "end")
        self.text_box.configure(foreground=self.FIELD_TEXT_COLOR)
        self.text_box.mark_set("insert", "1.0")
        self.placeholder_active = False
        self.text_box.edit_reset()
        self.text_box.edit_modified(False)

    def show_placeholder(self):
        if self.request_running or self.text_box.get("1.0", "end-1c").strip():
            return
        self.text_box.delete("1.0", "end")
        self.text_box.insert("1.0", self.PLACEHOLDER_TEXT)
        self.text_box.configure(foreground=self.PLACEHOLDER_COLOR)
        self.text_box.mark_set("insert", "1.0")
        self.placeholder_active = True
        self.text_box.edit_reset()
        self.text_box.edit_modified(False)

    def on_text_change(self, event=None):
        if not self.text_box.edit_modified():
            return
        self.text_box.edit_modified(False)
        if self.request_running:
            return
        query = self.text_box.get("1.0", "end-1c").strip()
        if not query or query == "":
            self.show_placeholder()
        self.show_matches(query)
        self.fit_content_height()

    def show_matches(self, query):
        self.current_results = matching_conversations(query)
        visible = self.current_results[:self.MAX_VISIBLE_RESULTS]
        while len(self.result_labels) < len(visible):
            label = tk.Label(self.results_frame, anchor="w", background=self.FIELD_COLOR,
                             foreground=self.FIELD_TEXT_COLOR, font=("Helvetica", 16),
                             padx=14, pady=7, wraplength=self.app_width - 28, justify="left")
            label.pack(fill="x")
            self.result_labels.append(label)
        for i, label in enumerate(self.result_labels):
            if i < len(visible):
                label.configure(text=visible[i]["snippet"])
                label.pack(fill="x")
            else:
                label.pack_forget()

    def set_window_height(self, height, force=False):
        if self._manual_size and not force:
            return
        x, y = self.winfo_x(), self.winfo_y()
        width = max(1, self.winfo_width())
        geometry = f"{width}x{height}+{x}+{y}"
        if self.geometry() != geometry:
            self._geometry_update = True
            self.geometry(geometry)
            self.after_idle(lambda: setattr(self, "_geometry_update", False))

    def _track_manual_resize(self, event):
        if event.widget is not self:
            return
        size = (event.width, event.height)
        if self._last_size is not None and size != self._last_size and not self._geometry_update:
            self._manual_size = True
        self._last_size = size

    def set_status(self, text, state):
        foreground = {
            "ready": "#35c46a",
            "waiting": "#f2c94c",
            "success": "#35c46a",
            "error": "#eb5757",
        }[state]
        self.status.configure(text=text, foreground=foreground)

    def ready_status_text(self):
        records = read_history()
        last_task_id = next(
            (record.get("task_id") for record in reversed(records) if record.get("task_id")),
            None,
        )
        if last_task_id:
            last_count = sum(
                record.get("task_id") == last_task_id and record.get("cycle") is not None
                for record in records
            )
        else:
            last_count = 1 if records else 0
        return f"Ready · {MODEL_LABEL} · Last task took {last_count} cycle{'s' if last_count != 1 else ''}"

    def insert_newline(self, event=None):
        if self.request_running:
            return "break"
        self.text_box.insert("insert", "\n")
        return "break"

    def submit_prompt(self, event=None):
        if self.request_running:
            return "break"
        prompt = self.text_box.get("1.0", "end-1c").strip()
        if self.placeholder_active:
            prompt = ""
        attachment_paths = tuple(self.attachments)
        if not prompt and not attachment_paths:
            self.show_placeholder()
            return "break"
        if not prompt:
            prompt = "Please inspect the attached file(s) and help me with them."
        context = self.current_results[:MAX_CONTEXT_RESULTS]
        self.request_running = True
        self.task_id = uuid.uuid4().hex
        self.task_cycles = 0
        self.text_box.configure(state="disabled")
        self.set_attachment_controls_enabled(False)
        self.lucy_message.configure(text="")
        self.set_status(f"Waiting · {MODEL_LABEL} · 0 cycles", "waiting")
        self.show_matches("")
        self.fit_content_height()

        threading.Thread(
            target=self.request_and_run,
            args=(prompt, context, attachment_paths),
            daemon=True,
        ).start()
        return "break"

    def request_and_run(self, prompt, context, attachment_paths=()):
        try:
            if not KEY:
                raise RuntimeError("OpenAI API key is not configured.")
            client = OpenAI(api_key=KEY, timeout=300, max_retries=0)
            attachment_content = [
                make_attachment_content(Path(path)) for path in attachment_paths
            ]
            traced_context = "\n".join(
                f"user: {item['user']}\nassistant: {item['assistant']}"
                for item in context
            )
            current_prompt = prompt
            if traced_context:
                current_prompt = (
                    "traced conversational context (may be inaccurate/irrelevant) { "
                    + traced_context + " }\n\n" + prompt
                )

            screenshot_data_url = None
            screenshot_attachment_path = None
            while True:
                cycle_number = self.task_cycles + 1
                self.events.put(("cycle", cycle_number))
                self.events.put(("waiting", f"Waiting · {MODEL_LABEL} · Cycle {cycle_number}"))
                input_content = list(attachment_content)
                input_content.append({"type": "input_text", "text": current_prompt})
                attached_image_paths = []
                if screenshot_data_url:
                    input_content.append({
                        "type": "input_image",
                        "image_url": screenshot_data_url,
                    })
                    if screenshot_attachment_path:
                        attached_image_paths.append(str(screenshot_attachment_path))
                    screenshot_data_url = None
                    screenshot_attachment_path = None

                system_instructions = (
                    f"{SYSTEM_PROMPT}\n\n"
                    f"Reusable executable scripts directory: {SKILLS_DIR}"
                )
                response_format = {
                    "type": "json_schema",
                    "name": "lucy_agent_action",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "response_type": {
                                "type": "string",
                                "enum": ["command", "speech", "done", "screenshot"],
                            },
                            "main_response": {"type": "string"},
                            "lucy_message": {
                                "type": "string",
                                "enum": ["", "lucy_done_3030", "lucy_wants_ss_3030"],
                            },
                        },
                        "required": ["response_type", "main_response", "lucy_message"],
                        "additionalProperties": False,
                    },
                }
                response = client.responses.create(
                    model=MODEL,
                    instructions=system_instructions,
                    input=[{"role": "user", "content": input_content}],
                    text={"format": response_format},
                    tools=API_TOOLS,
                    store=False,
                )
                generated_images = save_generated_images(response, self.task_id, cycle_number)
                result = json.loads(response.output_text or "{}")
                response_type = str(result.get("response_type", "")).strip()
                main_response = str(result.get("main_response", "")).strip()
                if response_type == "command":
                    main_response = extract_script(main_response)
                lucy_message = str(result.get("lucy_message", "")).strip()
                record = {
                    "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "model": MODEL,
                    "task_id": self.task_id,
                    "cycle": cycle_number,
                    "user": prompt,
                    "assistant": main_response,
                    "lucy_message": lucy_message,
                    "response_type": response_type,
                    "status": "success",
                    "response_id": response.id,
                    "prompt_context": {
                        "model": MODEL,
                        "user_input_with_context": current_prompt,
                        "attached_images": attached_image_paths,
                        "attached_files": [Path(path).name for path in attachment_paths],
                        "tools": API_TOOLS,
                        "response_format": response_format,
                        "store": False,
                    },
                }
                if generated_images:
                    record["generated_images"] = [str(path) for path in generated_images]
                self.task_cycles = cycle_number

                if response_type == "speech":
                    if lucy_message != "lucy_done_3030" or not main_response:
                        raise ValueError("Speech responses need text and lucy_done_3030.")
                    append_history(record)
                    subprocess.Popen(["say", main_response])
                    display_message = main_response
                    if generated_images:
                        display_message += "\nSaved image: " + ", ".join(
                            str(path) for path in generated_images
                        )
                    self.events.put(("complete", {
                        "message": display_message, "status": "Response complete · Lucy"
                    }))
                    return

                if response_type == "done":
                    if lucy_message != "lucy_done_3030":
                        raise ValueError("Done responses need lucy_done_3030.")
                    append_history(record)
                    if main_response:
                        subprocess.Popen(["say", main_response])
                    display_message = main_response
                    if generated_images:
                        display_message += "\nSaved image: " + ", ".join(
                            str(path) for path in generated_images
                        )
                    has_command_cycle = any(
                        item.get("task_id") == self.task_id
                        and item.get("cycle") is not None
                        and item.get("status") == "command_finished"
                        for item in read_history()
                    )
                    if not has_command_cycle:
                        self.events.put(("complete", {
                            "message": display_message or "Done.",
                            "status": "Response complete · Lucy",
                        }))
                        return
                    reused_skill = reused_skill_for_task(self.task_id)
                    if reused_skill:
                        self.events.put(("complete", {
                            "message": main_response or f"Reused {reused_skill.name}.",
                            "status": (
                                f"Task complete · {MODEL_LABEL} · {self.task_cycles} cycles · "
                                f"reused {reused_skill.name}"
                            ),
                        }))
                        return
                    self.events.put((
                        "generating",
                        f"Task verified · preparing standalone script · {MODEL_LABEL} · {self.task_cycles} cycles",
                    ))
                    try:
                        script_path = create_standalone_skill(client, self.task_id, prompt, context)
                        completion_message = (
                            f"Task complete · {MODEL_LABEL} · {self.task_cycles} cycles · "
                            f"saved {script_path.name}"
                        )
                    except Exception as exc:
                        completion_message = (
                            f"Task complete · {MODEL_LABEL} · {self.task_cycles} cycles · "
                            f"standalone script generation failed: {exc}"
                        )
                    self.events.put(("complete", {
                        "message": display_message or completion_message,
                        "status": completion_message,
                    }))
                    return

                if response_type == "screenshot":
                    if main_response:
                        raise ValueError("Screenshot requests must have an empty main_response.")
                    if lucy_message != "lucy_wants_ss_3030":
                        raise ValueError("Screenshot responses need lucy_wants_ss_3030.")
                    overlay_ready = threading.Event()
                    self.events.put(("screenshot", ("Viewing screen…", overlay_ready)))
                    if overlay_ready.wait(timeout=1.0):
                        time.sleep(0.25)
                    screenshot_path = capture_screenshot()
                    screenshot_bytes = screenshot_path.read_bytes()
                    screenshot_data_url = "data:image/png;base64," + base64.b64encode(screenshot_bytes).decode("ascii")
                    screenshot_attachment_path = screenshot_path
                    record["screenshot"] = str(screenshot_path)
                    record["status"] = "screenshot_captured"
                    append_history(record)
                    last_execution = next(
                        (
                            item for item in reversed(read_history())
                            if item.get("task_id") == self.task_id
                            and item.get("execution_output")
                        ),
                        None,
                    )
                    execution_context = ""
                    if last_execution:
                        execution_context = (
                            f"\nMost recent command:\n{last_execution.get('assistant', '')}"
                            f"\nObserved output:\n{last_execution['execution_output']}\n"
                        )
                    current_prompt = (
                        f"Original task: {prompt}{execution_context}\n"
                        "A screenshot was captured and attached. Inspect only what is "
                        "visible in it, combine that evidence with the observed command "
                        "output above, then return the next JSON action using the required schema."
                    )
                    continue

                if response_type != "command":
                    raise ValueError(f"Unsupported response_type: {response_type}")
                if lucy_message or not main_response:
                    raise ValueError("The model returned neither a command nor a completion marker.")

                self.events.put(("running", main_response))
                try:
                    execution = run_script_in_background(main_response)
                except (OSError, subprocess.SubprocessError) as exc:
                    execution = f"Could not run command: {exc}"
                record["execution_output"] = execution
                record["status"] = "command_finished"
                append_history(record)
                self.events.put(("step_done", execution))
                time.sleep(0.7)
                current_prompt = (
                    f"Original task: {prompt}\n\n"
                    f"Command just executed:\n{main_response}\n\n"
                    f"Command output and exit information:\n{execution}\n\n"
                    "Continue from this result. Return the next JSON action using the required schema."
                )
        except AuthenticationError:
            self.events.put(("error", API_KEY_ERROR_STATUS))
        except Exception as exc:
            self.events.put(("error", f"{type(exc).__name__}: {exc}"))

    def process_events(self):
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "attachment_preview":
                    path, preview_data = payload
                    card = self.attachment_cards.get(path)
                    if card and preview_data:
                        try:
                            image_data = base64.b64encode(preview_data).decode("ascii")
                            preview_image = tk.PhotoImage(data=image_data)
                            factor = max(
                                1,
                                (preview_image.width() + 119) // 120,
                                (preview_image.height() + 47) // 48,
                            )
                            if factor > 1:
                                preview_image = preview_image.subsample(factor, factor)
                            card["preview"].configure(image=preview_image, text="")
                            card["preview"].image = preview_image
                        except tk.TclError:
                            pass
                elif event == "running":
                    self.show_running_window(payload)
                    self.set_status("Running command…", "waiting")
                elif event == "waiting":
                    self.set_status(payload, "waiting")
                elif event == "cycle":
                    self.task_cycles = payload
                elif event == "screenshot":
                    status_text, overlay_ready = payload
                    self.set_status(status_text, "waiting")
                    try:
                        self.show_viewing_overlay()
                    finally:
                        overlay_ready.set()
                elif event == "generating":
                    self.set_status(payload, "waiting")
                elif event == "step_done":
                    self.close_running_window()
                    failed = any(marker in payload.casefold() for marker in (
                        "could not open terminal", "could not run command",
                        "exited with status", "timed out",
                    ))
                    self.set_status(
                        f"Command failed · {MODEL_LABEL} · Cycle {self.task_cycles}" if failed else f"Command executed · {MODEL_LABEL} · Cycle {self.task_cycles}",
                        "error" if failed else "success",
                    )
                elif event in ("complete", "error"):
                    self.close_running_window()
                    self.request_running = False
                    self.text_box.configure(state="normal")
                    self.set_attachment_controls_enabled(True)
                    if event == "complete":
                        self.clear_attachments()
                    self.text_box.delete("1.0", "end")
                    self.text_box.edit_modified(False)
                    self.show_placeholder()
                    self.text_box.focus_force()
                    if isinstance(payload, dict):
                        self.lucy_message.configure(text=f"Lucy: {payload['message']}")
                        message_lines = max(1, (len(payload["message"]) + 64) // 65)
                        self.set_window_height(self.MIN_HEIGHT_PX + min(message_lines, 5) * 22)
                        status_text = payload.get("status", "Response complete · Lucy")
                        artifact_failed = False
                    else:
                        status_text = payload
                        artifact_failed = "standalone script generation failed" in payload.casefold()
                    self.set_status(
                        status_text,
                        "error" if event == "error" or artifact_failed else "success",
                    )
                    self.fit_content_height()
                    if status_text != API_KEY_ERROR_STATUS:
                        self.after(
                            3000,
                            lambda: self.set_status(self.ready_status_text(), "ready")
                            if not self.request_running else None,
                        )
        except queue.Empty:
            pass
        self.after(100, self.process_events)

    def show_running_window(self, script):
        self.close_running_window()
        self.update_idletasks()
        width = max(1, self.winfo_width())
        group_width = (width * 2) + 12
        left_x = max(0, (self.winfo_screenwidth() - group_width) // 2)
        x = left_x
        y = self.winfo_y()
        height = self.winfo_height()
        self.geometry(f"{width}x{height}+{left_x + width + 12}+{y}")
        window = tk.Toplevel(self)
        self.result_window = window
        window.title("Running command")
        window.attributes("-topmost", True)
        window.configure(background=self.FIELD_COLOR)
        window.geometry(f"{width}x{height}+{x}+{y}")
        tk.Label(window, text="Running command…", anchor="w", background=self.FIELD_COLOR,
                 foreground=self.FIELD_TEXT_COLOR, font=("Helvetica", 18), padx=14, pady=10).pack(fill="x")
        code_box = tk.Text(window, height=5, wrap="word", background=self.FIELD_COLOR,
                           foreground="#cbd5e1", font=("Menlo", 12), borderwidth=0,
                           padx=14, pady=8)
        code_box.pack(fill="both", expand=True)
        code_box.insert("1.0", script[:1200])
        code_box.configure(state="disabled")
        window.deiconify()
        window.lift()
        self.lift()

    def show_viewing_overlay(self):
        if self.viewing_overlay is not None:
            try:
                self.viewing_overlay.destroy()
            except tk.TclError:
                pass

        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        overlay = tk.Toplevel(self)
        self.viewing_overlay = overlay
        overlay.title("Lucy screen indicator")
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.attributes("-alpha", 0.0)
        overlay.geometry(f"{screen_width}x{screen_height}+0+0")

        if sys.platform == "darwin":
            overlay.configure(background="systemTransparent")
            overlay.attributes("-transparent", True)
            canvas_background = "systemTransparent"
        else:
            overlay.configure(background="#06182b")
            canvas_background = "#06182b"

        canvas = tk.Canvas(
            overlay, background=canvas_background, borderwidth=0,
            highlightthickness=0,
        )
        canvas.pack(fill="both", expand=True)
        canvas.update_idletasks()
        outer_rgb = tuple(int(VIEWING_OVERLAY_OUTER_COLOR[i:i + 2], 16) for i in (1, 3, 5))
        inner_rgb = tuple(int(VIEWING_OVERLAY_INNER_COLOR[i:i + 2], 16) for i in (1, 3, 5))
        band_width = max(1, VIEWING_OVERLAY_EDGE_WIDTH)
        for index in range(band_width):
            ratio = index / max(1, band_width - 1)
            color = "#" + "".join(
                f"{round(start + (end - start) * ratio):02x}"
                for start, end in zip(outer_rgb, inner_rgb)
            )
            inset = index
            canvas.create_rectangle(
                inset, inset, screen_width - inset - 1, screen_height - inset - 1,
                outline=color, width=1,
            )
            # The macOS menu bar can cover the canvas's topmost pixels, so draw
            # the top edge just below it as a separate gradient band.
            top_y = VIEWING_OVERLAY_TOP_EDGE_OFFSET + index
            canvas.create_line(0, top_y, screen_width, top_y, fill=color, width=1)

        if VIEWING_OVERLAY_CLICK_THROUGH:
            try:
                import AppKit

                for native_window in AppKit.NSApplication.sharedApplication().windows():
                    if native_window.title() == "Lucy screen indicator":
                        native_window.setIgnoresMouseEvents_(True)
                        break
            except Exception:
                pass

        def animate(frame=0):
            if self.viewing_overlay is not overlay:
                return
            frame_count = max(2, VIEWING_OVERLAY_DURATION_MS // VIEWING_OVERLAY_FRAME_MS)
            progress = frame / frame_count
            alpha = VIEWING_OVERLAY_MAX_ALPHA * (1 - abs(2 * progress - 1))
            try:
                overlay.attributes("-alpha", alpha)
            except tk.TclError:
                self.viewing_overlay = None
                return
            if frame >= frame_count:
                overlay.destroy()
                self.viewing_overlay = None
            else:
                self.after(VIEWING_OVERLAY_FRAME_MS, lambda: animate(frame + 1))

        self.after(10, animate)

    def close_running_window(self):
        if self.result_window is not None:
            try:
                self.result_window.destroy()
            except tk.TclError:
                pass
            self.result_window = None

    def _undo(self, event=None):
        if not self.request_running:
            try:
                self.text_box.edit_undo()
            except tk.TclError:
                pass
        return "break"

    def _redo(self, event=None):
        if not self.request_running:
            try:
                self.text_box.edit_redo()
            except tk.TclError:
                pass
        return "break"


def append_history(record):
    with HISTORY_FILE.open("a", encoding="utf-8") as history:
        cycle = record.get("cycle")
        if cycle is not None:
            moment = datetime.fromisoformat(record["timestamp"]).astimezone()
            readable = moment.strftime("%b %d, %Y %I:%M:%S %p %Z")
            history.write(
                f"\n# cycle {cycle} [{readable}] · {record.get('model', MODEL)} "
                f"· task={record.get('task_id', 'unknown')}:\n"
            )
        history.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n\n")
        history.flush()
        os.fsync(history.fileno())


if __name__ == "__main__":
    SiriOverlayApp().mainloop()
