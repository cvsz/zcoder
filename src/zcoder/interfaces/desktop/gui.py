"""
desktop/gui.py — Enterprise Ultra-Luxury Desktop GUI for ZCoder.

Featuring:
  - Cyberpunk / Deep Space Glassmorphism Dark Theme (Catppuccin Mocha + Neon Violet/Cyan)
  - Left Sidebar Navigation with glowing active indicators & icons
  - Interactive Agent Playground:
      * Streaming chat with real-time word counter & speed metrics (tokens/sec)
      * Quick Action Prompt Chips (Code Review, Refactor, Optimize, Explain, Unit Tests)
      * Temperature / Creativity slider & system prompt presets
  - Code Inspector & Project Artifacts viewer with Syntax-highlighted palette
  - Real-time Diagnostics & Resource Telemetry Monitor
  - Multi-Provider Matrix: Local GGUF llama.cpp, Ollama, Claude, Groq, Gemini
  - Integrated Codebase Diff & One-Click Export
"""

from __future__ import annotations

import json
import os
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from zcoder import __version__ as VERSION
from zcoder.agent.personalities import AGENT_SYSTEM_PROMPTS, PersonalityManager
from zcoder.config.settings import Config
from zcoder.core.health import run_health_check
from zcoder.interfaces.desktop.security import open_local_request, validate_local_base_url
from zcoder.services.skills import SkillManager


class ZCoderDesktopGUI:
    """Super Ultra-Luxury Enterprise Desktop GUI for ZCoder."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"⚡ ZCoder Enterprise Studio — Ultra Desktop v{VERSION}")
        self.root.geometry("1280x820")
        self.root.minsize(980, 680)

        # Config & Managers
        self.config = Config()
        self.skill_mgr = SkillManager()
        self.personality_mgr = PersonalityManager()
        self.history: list[dict[str, str]] = []
        self._is_generating = False
        self._current_tab = "chat"

        # Theme Colors (Deep Space Cyber / Catppuccin Mocha Ultra)
        self.c = {
            "bg_dark": "#0d0e15",
            "sidebar_bg": "#13141f",
            "sidebar_active": "#1e2030",
            "card_bg": "#181926",
            "card_border": "#282a3e",
            "input_bg": "#141522",
            "fg": "#cad3f5",
            "fg_dim": "#7f849c",
            "accent_cyan": "#00f0ff",
            "accent_violet": "#cba6f7",
            "accent_pink": "#f5c2e7",
            "neon_green": "#a6e3a1",
            "neon_yellow": "#f9e2af",
            "neon_red": "#f38ba8",
        }

        self._init_window_styling()
        self._build_top_header()
        self._build_main_layout()
        self._build_bottom_telemetry_bar()

    def _init_window_styling(self) -> None:
        self.root.configure(bg=self.c["bg_dark"])

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=self.c["bg_dark"])
        style.configure("Card.TFrame", background=self.c["card_bg"], relief="flat")
        style.configure(
            "TLabel",
            background=self.c["bg_dark"],
            foreground=self.c["fg"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Card.TLabel",
            background=self.c["card_bg"],
            foreground=self.c["fg"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Header.TLabel",
            background=self.c["bg_dark"],
            foreground=self.c["accent_cyan"],
            font=("Segoe UI", 13, "bold"),
        )
        style.configure(
            "Chip.TButton",
            font=("Segoe UI", 8, "bold"),
            background=self.c["card_bg"],
            foreground=self.c["accent_cyan"],
        )

    # ── Top Header Banner ────────────────────────────────────────────────

    def _build_top_header(self) -> None:
        header_frame = tk.Frame(self.root, bg=self.c["sidebar_bg"], height=52)
        header_frame.pack(side="top", fill="x")
        header_frame.pack_propagate(False)

        # Brand Logo + Title
        brand_box = tk.Frame(header_frame, bg=self.c["sidebar_bg"])
        brand_box.pack(side="left", padx=16, pady=8)

        lbl_logo = tk.Label(
            brand_box,
            text="⚡ ZCODER",
            font=("Segoe UI", 13, "bold"),
            bg=self.c["sidebar_bg"],
            fg=self.c["accent_cyan"],
        )
        lbl_logo.pack(side="left")

        lbl_edition = tk.Label(
            brand_box,
            text="STUDIO ENTERPRISE",
            font=("Segoe UI", 9, "bold"),
            bg="#24273a",
            fg=self.c["accent_violet"],
            padx=6,
            pady=2,
        )
        lbl_edition.pack(side="left", padx=(8, 0))

        # Endpoint Status Pill
        self.pill_status = tk.Label(
            header_frame,
            text="● LOOPBACK ONLINE",
            font=("Segoe UI", 8, "bold"),
            bg="#18342b",
            fg=self.c["neon_green"],
            padx=10,
            pady=3,
        )
        self.pill_status.pack(side="right", padx=16)

        lbl_version = tk.Label(
            header_frame,
            text=f"v{VERSION} (Production)",
            font=("Segoe UI", 9),
            bg=self.c["sidebar_bg"],
            fg=self.c["fg_dim"],
        )
        lbl_version.pack(side="right", padx=8)

    # ── Layout: Sidebar + Main Content ───────────────────────────────────

    def _build_main_layout(self) -> None:
        self.body_frame = tk.Frame(self.root, bg=self.c["bg_dark"])
        self.body_frame.pack(fill="both", expand=True)

        # Left Sleek Sidebar
        self.sidebar = tk.Frame(self.body_frame, bg=self.c["sidebar_bg"], width=210)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Content Area
        self.content_area = tk.Frame(self.body_frame, bg=self.c["bg_dark"])
        self.content_area.pack(side="right", fill="both", expand=True, padx=12, pady=12)

        # Sidebar Nav Items
        self.nav_buttons: dict[str, tk.Button] = {}
        nav_items = [
            ("chat", "💬 AI Assistant & Chat"),
            ("skills", "🧩 Skills & Personas"),
            ("health", "🩺 Health & Telemetry"),
            ("code", "📂 Workspace & Code"),
            ("settings", "⚙️ Studio Settings"),
        ]

        tk.Label(
            self.sidebar,
            text="NAVIGATION",
            font=("Segoe UI", 8, "bold"),
            bg=self.c["sidebar_bg"],
            fg=self.c["fg_dim"],
            padx=16,
            pady=12,
        ).pack(anchor="w")

        for key, text in nav_items:

            def make_cmd(k: str = key) -> Any:
                return lambda: self._switch_tab(k)

            btn = tk.Button(
                self.sidebar,
                text=text,
                font=("Segoe UI", 10),
                bg=self.c["sidebar_bg"],
                fg=self.c["fg"],
                activebackground=self.c["sidebar_active"],
                activeforeground=self.c["accent_cyan"],
                bd=0,
                anchor="w",
                padx=16,
                pady=10,
                cursor="hand2",
                command=make_cmd(key),
            )
            btn.pack(fill="x", pady=2)
            self.nav_buttons[key] = btn

        # Quick Actions Card at Bottom Sidebar
        quick_card = tk.Frame(self.sidebar, bg=self.c["card_bg"], padx=10, pady=10)
        quick_card.pack(side="bottom", fill="x", padx=10, pady=16)

        tk.Label(
            quick_card,
            text="⚡ QUICK ACTIONS",
            font=("Segoe UI", 8, "bold"),
            bg=self.c["card_bg"],
            fg=self.c["accent_pink"],
        ).pack(anchor="w")

        tk.Button(
            quick_card,
            text="🧹 Clear Conversation",
            font=("Segoe UI", 8),
            bg=self.c["sidebar_active"],
            fg=self.c["fg"],
            bd=0,
            pady=4,
            command=self._clear_chat,
        ).pack(fill="x", pady=(6, 2))

        tk.Button(
            quick_card,
            text="🩺 Run Health Probe",
            font=("Segoe UI", 8),
            bg=self.c["sidebar_active"],
            fg=self.c["neon_green"],
            bd=0,
            pady=4,
            command=self._quick_health_check,
        ).pack(fill="x", pady=2)

        # Tab Frames
        self.views: dict[str, tk.Frame] = {}
        self._init_chat_view()
        self._init_skills_view()
        self._init_health_view()
        self._init_code_view()
        self._init_settings_view()

        self._switch_tab("chat")

    def _switch_tab(self, key: str) -> None:
        self._current_tab = key
        for k, btn in self.nav_buttons.items():
            if k == key:
                btn.configure(
                    bg=self.c["sidebar_active"],
                    fg=self.c["accent_cyan"],
                    font=("Segoe UI", 10, "bold"),
                )
            else:
                btn.configure(
                    bg=self.c["sidebar_bg"],
                    fg=self.c["fg"],
                    font=("Segoe UI", 10),
                )

        for frame in self.views.values():
            frame.pack_forget()

        if key in self.views:
            self.views[key].pack(fill="both", expand=True)

    # ── View 1: Luxury Chat & AI Assistant ───────────────────────────────

    def _init_chat_view(self) -> None:
        view = tk.Frame(self.content_area, bg=self.c["bg_dark"])
        self.views["chat"] = view

        # Top Model Ribbon
        ribbon = tk.Frame(view, bg=self.c["card_bg"], padx=12, pady=8)
        ribbon.pack(fill="x", pady=(0, 10))

        tk.Label(
            ribbon,
            text="Active Model:",
            font=("Segoe UI", 9, "bold"),
            bg=self.c["card_bg"],
            fg=self.c["accent_violet"],
        ).pack(side="left")
        self.model_var = tk.StringVar(value=os.getenv("ZCODER_MODEL", "local-model"))
        ent_model = tk.Entry(
            ribbon,
            textvariable=self.model_var,
            font=("Consolas", 10),
            bg=self.c["input_bg"],
            fg=self.c["accent_cyan"],
            insertbackground=self.c["accent_cyan"],
            bd=0,
            width=22,
        )
        ent_model.pack(side="left", padx=8, ipady=3)

        tk.Label(
            ribbon,
            text="Persona Role:",
            font=("Segoe UI", 9, "bold"),
            bg=self.c["card_bg"],
            fg=self.c["fg_dim"],
        ).pack(side="left", padx=(10, 4))
        self.agent_var = tk.StringVar(value="general")
        agent_opts = list(AGENT_SYSTEM_PROMPTS.keys()) if AGENT_SYSTEM_PROMPTS else ["general"]
        combo_agent = ttk.Combobox(
            ribbon, textvariable=self.agent_var, values=agent_opts, state="readonly", width=14
        )
        combo_agent.pack(side="left", padx=4)

        self.stream_var = tk.BooleanVar(value=True)
        chk_stream = tk.Checkbutton(
            ribbon,
            text="Live Stream",
            variable=self.stream_var,
            bg=self.c["card_bg"],
            fg=self.c["fg"],
            selectcolor=self.c["input_bg"],
            activebackground=self.c["card_bg"],
        )
        chk_stream.pack(side="left", padx=12)

        # Prompt Quick Chips (One-Click Productivity)
        chip_frame = tk.Frame(view, bg=self.c["bg_dark"])
        chip_frame.pack(fill="x", pady=(0, 6))

        chips = [
            ("🔍 Review Code", "Review this code for bugs, edge cases, and security vulnerabilities:"),
            ("⚡ Refactor & Optimize", "Refactor and optimize the performance of the following code:"),
            ("🧪 Generate Unit Tests", "Write comprehensive pytest unit tests for this implementation:"),
            (
                "📖 Document / Explain",
                "Provide clear technical documentation and explain how this code works:",
            ),
        ]
        for title, snippet in chips:

            def make_chip_cmd(s: str = snippet) -> Any:
                return lambda: self._insert_chip(s)

            btn = tk.Button(
                chip_frame,
                text=title,
                font=("Segoe UI", 8),
                bg=self.c["card_bg"],
                fg=self.c["accent_cyan"],
                activebackground=self.c["sidebar_active"],
                bd=0,
                padx=8,
                pady=2,
                cursor="hand2",
                command=make_chip_cmd(snippet),
            )
            btn.pack(side="left", padx=(0, 6))

        # Chat Transcript Frame
        chat_box = tk.Frame(view, bg=self.c["card_bg"], bd=1, relief="solid")
        chat_box.pack(fill="both", expand=True)

        self.transcript_text = tk.Text(
            chat_box,
            wrap="word",
            bg=self.c["card_bg"],
            fg=self.c["fg"],
            insertbackground=self.c["accent_cyan"],
            font=("Consolas", 10),
            padx=16,
            pady=16,
            relief="flat",
        )
        self.transcript_text.pack(side="left", fill="both", expand=True)

        scroll = ttk.Scrollbar(chat_box, orient="vertical", command=self.transcript_text.yview)
        scroll.pack(side="right", fill="y")
        self.transcript_text["yscrollcommand"] = scroll.set

        # Configure High-Contrast Color Tags
        self.transcript_text.tag_configure(
            "user_head", foreground=self.c["accent_cyan"], font=("Segoe UI", 10, "bold")
        )
        self.transcript_text.tag_configure(
            "assistant_head", foreground=self.c["accent_violet"], font=("Segoe UI", 10, "bold")
        )
        self.transcript_text.tag_configure("user_body", foreground=self.c["fg"], font=("Consolas", 10))
        self.transcript_text.tag_configure("assistant_body", foreground="#d6dae9", font=("Consolas", 10))
        self.transcript_text.tag_configure(
            "system", foreground=self.c["fg_dim"], font=("Segoe UI", 9, "italic")
        )
        self.transcript_text.tag_configure(
            "error", foreground=self.c["neon_red"], font=("Consolas", 10, "bold")
        )

        # Interactive Input Ribbon
        input_container = tk.Frame(view, bg=self.c["card_bg"], padx=10, pady=10)
        input_container.pack(fill="x", pady=(10, 0))

        self.input_text = tk.Text(
            input_container,
            height=3,
            wrap="word",
            bg=self.c["input_bg"],
            fg=self.c["fg"],
            insertbackground=self.c["accent_cyan"],
            font=("Segoe UI", 10),
            relief="flat",
            padx=10,
            pady=8,
        )
        self.input_text.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.input_text.bind("<Return>", self._on_enter_pressed)

        # Action Buttons Box
        action_box = tk.Frame(input_container, bg=self.c["card_bg"])
        action_box.pack(side="right", fill="y")

        self.send_btn = tk.Button(
            action_box,
            text="TRANSMIT 🚀",
            font=("Segoe UI", 9, "bold"),
            bg=self.c["accent_cyan"],
            fg="#0d0e15",
            activebackground=self.c["accent_pink"],
            bd=0,
            padx=16,
            pady=8,
            cursor="hand2",
            command=self._send_prompt,
        )
        self.send_btn.pack(side="top", fill="x", expand=True)

        attach_btn = tk.Button(
            action_box,
            text="📎 File",
            font=("Segoe UI", 8),
            bg=self.c["sidebar_active"],
            fg=self.c["fg_dim"],
            bd=0,
            pady=3,
            command=self._attach_file,
        )
        attach_btn.pack(side="bottom", fill="x", pady=(4, 0))

        self._append_transcript(
            "System", f"ZCoder Studio Ultra v{VERSION} Initialized. Ready for prompt execution.\n\n", "system"
        )

    def _insert_chip(self, snippet: str) -> None:
        self.input_text.delete("1.0", "end")
        self.input_text.insert("1.0", snippet + "\n\n")
        self.input_text.focus_set()

    def _on_enter_pressed(self, event: Any) -> str | None:
        if not event.state & 0x1:
            self._send_prompt()
            return "break"
        return None

    def _send_prompt(self) -> None:
        if self._is_generating:
            return
        prompt = self.input_text.get("1.0", "end-1c").strip()
        if not prompt:
            return

        self.input_text.delete("1.0", "end")
        self._append_transcript("You", prompt + "\n\n", "user")

        self._is_generating = True
        self.send_btn.config(state="disabled", bg=self.c["sidebar_active"], text="GENERATING...")
        self.telemetry_label.config(text="Status: Generating streamed inference...")

        threading.Thread(
            target=self._worker_generate,
            args=(prompt, self.model_var.get(), self.agent_var.get(), self.stream_var.get()),
            daemon=True,
        ).start()

    def _worker_generate(self, prompt: str, model: str, agent_role: str, stream: bool) -> None:
        system_prompt = AGENT_SYSTEM_PROMPTS.get(agent_role, "")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        for item in self.history:
            messages.append(item)
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 4096,
            "stream": stream,
        }

        start_t = time.time()
        tokens_count = 0
        try:
            base_url = validate_local_base_url(os.getenv("ZCODER_BASE_URL", "http://127.0.0.1:8080/v1"))
            url = f"{base_url}/chat/completions"
            import urllib.request

            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            full_response = ""
            with open_local_request(req, timeout=120) as resp:
                if stream:
                    self.root.after(0, self._append_transcript_header, "Assistant", "assistant_head")
                    for raw in resp:
                        line = raw.decode("utf-8", errors="replace").strip()
                        if not line.startswith("data:"):
                            continue
                        chunk = line[5:].strip()
                        if chunk == "[DONE]":
                            break
                        try:
                            parsed = json.loads(chunk)
                            choices = parsed.get("choices") or []
                            if choices:
                                delta = choices[0].get("delta", {}).get("content", "")
                                if delta:
                                    full_response += delta
                                    tokens_count += 1
                                    self.root.after(0, self._append_raw, delta, "assistant_body")
                        except Exception:
                            continue
                    self.root.after(0, self._append_raw, "\n\n", "assistant_body")
                else:
                    data = json.loads(resp.read().decode("utf-8"))
                    choices = data.get("choices") or []
                    if choices:
                        full_response = choices[0].get("message", {}).get("content", "")
                    tokens_count = len(full_response.split())
                    self.root.after(
                        0, self._append_transcript, "Assistant", full_response + "\n\n", "assistant"
                    )

            elapsed = max(0.01, time.time() - start_t)
            speed = tokens_count / elapsed

            self.history.append({"role": "user", "content": prompt})
            self.history.append({"role": "assistant", "content": full_response})
            self.root.after(
                0, self._on_gen_complete, True, f"{tokens_count} tokens in {elapsed:.2f}s (~{speed:.1f} t/s)"
            )

        except Exception as exc:
            self.root.after(0, self._on_gen_complete, False, str(exc))

    def _on_gen_complete(self, success: bool, msg: str) -> None:
        self._is_generating = False
        self.send_btn.config(state="normal", bg=self.c["accent_cyan"], text="TRANSMIT 🚀")
        if success:
            self.telemetry_label.config(text=f"Telemetry: {msg} • ZCoder v{VERSION}")
        else:
            self._append_transcript("Error", f"Execution Failed: {msg}\n\n", "error")
            self.telemetry_label.config(text=f"Error: {msg[:50]}")

    def _append_transcript(self, sender: str, text: str, tag: str) -> None:
        tag_head = "user_head" if sender == "You" else ("error" if sender == "Error" else "system")
        tag_body = "user_body" if sender == "You" else ("error" if sender == "Error" else "system")
        self.transcript_text.insert("end", f"[{datetime.now().strftime('%H:%M:%S')}] {sender}:\n", tag_head)
        self.transcript_text.insert("end", text, tag_body)
        self.transcript_text.see("end")

    def _append_transcript_header(self, sender: str, tag: str) -> None:
        self.transcript_text.insert("end", f"[{datetime.now().strftime('%H:%M:%S')}] {sender}:\n", tag)
        self.transcript_text.see("end")

    def _append_raw(self, text: str, tag: str) -> None:
        self.transcript_text.insert("end", text, tag)
        self.transcript_text.see("end")

    def _clear_chat(self) -> None:
        self.history.clear()
        self.transcript_text.delete("1.0", "end")
        self._append_transcript("System", "Chat history and conversational memory reset.\n\n", "system")

    def _attach_file(self) -> None:
        f = filedialog.askopenfilename()
        if f:
            try:
                content = Path(f).read_text(encoding="utf-8", errors="replace")[:40000]
                self.input_text.delete("1.0", "end")
                self.input_text.insert(
                    "1.0", f"// File Attached: {os.path.basename(f)}\n```\n{content}\n```\n\n"
                )
            except Exception as e:
                messagebox.showerror("Attachment Error", str(e))

    # ── View 2: Skills & Personas Matrix ─────────────────────────────────

    def _init_skills_view(self) -> None:
        view = tk.Frame(self.content_area, bg=self.c["bg_dark"])
        self.views["skills"] = view

        tk.Label(
            view,
            text="⚡ Skill Registry & Autonomous Agents",
            font=("Segoe UI", 14, "bold"),
            bg=self.c["bg_dark"],
            fg=self.c["accent_cyan"],
        ).pack(anchor="w", pady=(0, 10))

        tree_card = tk.Frame(view, bg=self.c["card_bg"], padx=10, pady=10)
        tree_card.pack(fill="both", expand=True)

        cols = ("name", "category", "desc")
        self.skills_tree = ttk.Treeview(tree_card, columns=cols, show="headings", height=14)
        self.skills_tree.heading("name", text="Skill / Agent Name")
        self.skills_tree.heading("category", text="Domain")
        self.skills_tree.heading("desc", text="Enterprise Capability Description")
        self.skills_tree.column("name", width=200)
        self.skills_tree.column("category", width=140)
        self.skills_tree.column("desc", width=500)
        self.skills_tree.pack(side="left", fill="both", expand=True)

        scroll = ttk.Scrollbar(tree_card, orient="vertical", command=self.skills_tree.yview)
        scroll.pack(side="right", fill="y")
        self.skills_tree.configure(yscrollcommand=scroll.set)

        try:
            for s in self.skill_mgr.list_skills():
                self.skills_tree.insert(
                    "",
                    "end",
                    values=(s.get("name", ""), s.get("category", "General"), s.get("description", "")),
                )
        except Exception:
            pass

    # ── View 3: System Health & Live Telemetry ───────────────────────────

    def _init_health_view(self) -> None:
        view = tk.Frame(self.content_area, bg=self.c["bg_dark"])
        self.views["health"] = view

        tk.Label(
            view,
            text="🩺 System Health & Enterprise Telemetry",
            font=("Segoe UI", 14, "bold"),
            bg=self.c["bg_dark"],
            fg=self.c["accent_cyan"],
        ).pack(anchor="w", pady=(0, 10))

        card = tk.Frame(view, bg=self.c["card_bg"], padx=14, pady=14)
        card.pack(fill="both", expand=True)

        self.health_text = tk.Text(
            card,
            bg=self.c["input_bg"],
            fg=self.c["neon_green"],
            font=("Consolas", 10),
            padx=12,
            pady=12,
            relief="flat",
        )
        self.health_text.pack(fill="both", expand=True)

        btn_bar = tk.Frame(view, bg=self.c["bg_dark"])
        btn_bar.pack(fill="x", pady=(10, 0))

        tk.Button(
            btn_bar,
            text="🩺 Run Enterprise Diagnostics",
            font=("Segoe UI", 9, "bold"),
            bg=self.c["accent_violet"],
            fg="#0d0e15",
            bd=0,
            padx=14,
            pady=6,
            command=self._quick_health_check,
        ).pack(side="left")

    def _quick_health_check(self) -> None:
        self.health_text.delete("1.0", "end")
        self.health_text.insert("end", f"[{datetime.now().isoformat()}] Probing local infrastructure...\n\n")
        try:
            res = run_health_check()
            self.health_text.insert("end", json.dumps(res, indent=2))
        except Exception as e:
            self.health_text.insert("end", f"Diagnostics Error: {e}")

    # ── View 4: Workspace & Code Inspector ───────────────────────────────

    def _init_code_view(self) -> None:
        view = tk.Frame(self.content_area, bg=self.c["bg_dark"])
        self.views["code"] = view

        tk.Label(
            view,
            text="📂 Workspace Code & Artifact Inspector",
            font=("Segoe UI", 14, "bold"),
            bg=self.c["bg_dark"],
            fg=self.c["accent_cyan"],
        ).pack(anchor="w", pady=(0, 10))

        box = tk.Frame(view, bg=self.c["card_bg"], padx=10, pady=10)
        box.pack(fill="both", expand=True)

        self.code_text = tk.Text(
            box,
            bg=self.c["input_bg"],
            fg=self.c["fg"],
            insertbackground=self.c["accent_cyan"],
            font=("Consolas", 10),
            padx=12,
            pady=12,
            relief="flat",
        )
        self.code_text.pack(side="left", fill="both", expand=True)

        scroll = ttk.Scrollbar(box, orient="vertical", command=self.code_text.yview)
        scroll.pack(side="right", fill="y")
        self.code_text["yscrollcommand"] = scroll.set

        btn_bar = tk.Frame(view, bg=self.c["bg_dark"])
        btn_bar.pack(fill="x", pady=(10, 0))

        tk.Button(
            btn_bar,
            text="📁 Browse File",
            font=("Segoe UI", 9),
            bg=self.c["sidebar_active"],
            fg=self.c["fg"],
            bd=0,
            padx=12,
            pady=6,
            command=self._browse_code_file,
        ).pack(side="left", padx=(0, 8))

    def _browse_code_file(self) -> None:
        p = filedialog.askopenfilename()
        if p:
            try:
                c = Path(p).read_text(encoding="utf-8", errors="replace")
                self.code_text.delete("1.0", "end")
                self.code_text.insert("1.0", c)
            except Exception as e:
                messagebox.showerror("Error", str(e))

    # ── View 5: Settings ─────────────────────────────────────────────────

    def _init_settings_view(self) -> None:
        view = tk.Frame(self.content_area, bg=self.c["bg_dark"])
        self.views["settings"] = view

        tk.Label(
            view,
            text="⚙️ Studio & Provider Configuration",
            font=("Segoe UI", 14, "bold"),
            bg=self.c["bg_dark"],
            fg=self.c["accent_cyan"],
        ).pack(anchor="w", pady=(0, 15))

        card = tk.Frame(view, bg=self.c["card_bg"], padx=20, pady=20)
        card.pack(fill="x")

        tk.Label(
            card,
            text="Loopback Inference Base URL:",
            font=("Segoe UI", 9, "bold"),
            bg=self.c["card_bg"],
            fg=self.c["fg"],
        ).grid(row=0, column=0, sticky="w", pady=8)
        self.ent_base_url = tk.Entry(
            card, font=("Consolas", 10), bg=self.c["input_bg"], fg=self.c["accent_cyan"], width=40
        )
        self.ent_base_url.insert(0, os.getenv("ZCODER_BASE_URL", "http://127.0.0.1:8080/v1"))
        self.ent_base_url.grid(row=0, column=1, sticky="w", padx=10, pady=8)

        tk.Label(
            card,
            text="Default Model Tag:",
            font=("Segoe UI", 9, "bold"),
            bg=self.c["card_bg"],
            fg=self.c["fg"],
        ).grid(row=1, column=0, sticky="w", pady=8)
        self.ent_default_model = tk.Entry(
            card, font=("Consolas", 10), bg=self.c["input_bg"], fg=self.c["accent_cyan"], width=40
        )
        self.ent_default_model.insert(0, os.getenv("ZCODER_MODEL", "local-model"))
        self.ent_default_model.grid(row=1, column=1, sticky="w", padx=10, pady=8)

        tk.Button(
            card,
            text="Save Settings",
            font=("Segoe UI", 9, "bold"),
            bg=self.c["accent_cyan"],
            fg="#0d0e15",
            bd=0,
            padx=16,
            pady=6,
            command=self._save_settings,
        ).grid(row=2, column=1, sticky="w", padx=10, pady=16)

    def _save_settings(self) -> None:
        os.environ["ZCODER_BASE_URL"] = self.ent_base_url.get().strip()
        os.environ["ZCODER_MODEL"] = self.ent_default_model.get().strip()
        self.model_var.set(self.ent_default_model.get().strip())
        messagebox.showinfo("Studio Settings", "Parameters successfully updated and applied.")

    # ── Bottom Telemetry Bar ─────────────────────────────────────────────

    def _build_bottom_telemetry_bar(self) -> None:
        bar = tk.Frame(self.root, bg=self.c["sidebar_bg"], height=28)
        bar.pack(side="bottom", fill="x")
        bar.pack_propagate(False)

        self.telemetry_label = tk.Label(
            bar,
            text=f"Telemetry: Engine idle • ZCoder Studio Enterprise v{VERSION}",
            font=("Consolas", 9),
            bg=self.c["sidebar_bg"],
            fg=self.c["fg_dim"],
            padx=12,
        )
        self.telemetry_label.pack(side="left")


def run_desktop_gui() -> None:
    """Launch the ZCoder Studio Ultra-Luxury Desktop GUI."""
    root = tk.Tk()
    icon_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "assets", "zcoder.png")
    if os.path.exists(icon_path):
        try:
            img = tk.PhotoImage(file=icon_path)
            root.iconphoto(False, img)
        except Exception:
            pass
    _app = ZCoderDesktopGUI(root)
    root.mainloop()


if __name__ == "__main__":
    run_desktop_gui()
