from __future__ import annotations

import functools
import logging
import sys
import time
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, font as tkfont, messagebox, ttk
from typing import Callable, Dict, List, Optional, Tuple

from database import MOCK_OWNER_PASSWORD, MOCK_TECH_PASSWORD
from repair_system import (
    DB_PATH, IDLE_TIMEOUT_SECONDS, REFRESH_INTERVAL_MS, AppError, Owner,
    RepairService, ServiceTicket, Technician, User, ValidationError,
    setup_logging,
)

log = logging.getLogger("repair_system")


# 1. THEME
class C:
  """Colour palette."""
  BG = "#F1F5F9"
  CARD = "#FFFFFF"
  BORDER = "#E2E8F0"
  TEXT = "#0F172A"
  MUTED = "#64748B"
  PRIMARY = "#2563EB"
  PRIMARY_HOVER = "#1D4ED8"
  PRIMARY_SOFT = "#DBEAFE"
  SIDEBAR = "#0F172A"
  SIDEBAR_SOFT = "#1E293B"
  SIDEBAR_LINE = "#334155"
  SIDEBAR_TEXT = "#94A3B8"
  DANGER = "#DC2626"
  DANGER_HOVER = "#B91C1C"
  SUCCESS = "#16A34A"
  WARN = "#D97706"
  SELECT = "#DBEAFE"
  DISABLED = "#CBD5E1"


STATUS_STYLE: Dict[str, Tuple[str, str]] = {
    "Pending": ("#B45309", "#FEF3C7"),
    "Diagnosing": ("#1D4ED8", "#DBEAFE"),
    "In Repair": ("#6D28D9", "#EDE9FE"),
    "Ready for Pickup": ("#15803D", "#DCFCE7"),
    "Closed": ("#475569", "#E2E8F0"),
    "Cancelled": ("#B91C1C", "#FEE2E2"),
}

FONT_FAMILY = "Helvetica"
F: Dict[str, tuple] = {}


def init_fonts(root) -> None:
  global FONT_FAMILY
  families = set(tkfont.families(root))
  for name in ("Segoe UI", "SF Pro Text", "Helvetica Neue", "Ubuntu",
               "Noto Sans", "DejaVu Sans", "Arial"):
    if name in families:
      FONT_FAMILY = name
      break
  mono = next((n for n in ("Consolas", "Menlo", "DejaVu Sans Mono", "Courier New")
               if n in families), "Courier")
  fam = FONT_FAMILY
  F.update(
      body=(fam, 10), bold=(fam, 10, "bold"), small=(fam, 9),
      small_bold=(fam, 9, "bold"), tiny=(fam, 8, "bold"),
      h1=(fam, 22, "bold"), h2=(fam, 13, "bold"), big=(fam, 24, "bold"),
      mono=(mono, 10),
  )


def enable_dpi_awareness() -> None:
  if sys.platform.startswith("win"):
    try:
      import ctypes
      try:
        ctypes.windll.shcore.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
      except Exception:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:  # pragma: no cover
      pass


def apply_theme(root) -> None:
  init_fonts(root)
  style = ttk.Style(root)
  style.theme_use("clam")
  root.configure(bg=C.BG)
  root.option_add("*Font", F["body"])
  root.option_add("*TCombobox*Listbox.font", F["body"])
  root.option_add("*TCombobox*Listbox.background", "white")
  root.option_add("*TCombobox*Listbox.foreground", C.TEXT)
  root.option_add("*TCombobox*Listbox.selectBackground", C.PRIMARY)
  root.option_add("*TCombobox*Listbox.selectForeground", "white")

  style.configure(".", font=F["body"], background=C.BG, foreground=C.TEXT)
  style.configure("TFrame", background=C.BG)
  style.configure("TLabel", background=C.BG, foreground=C.TEXT)

  def button_style(name, bg, fg, border, hover, pressed, disabled, bold=False):
    style.configure(
        name, padding=(14, 8), background=bg, foreground=fg, bordercolor=border,
        lightcolor=bg, darkcolor=bg, focuscolor=bg, borderwidth=1, relief="flat",
        font=F["bold"] if bold else F["body"])
    style.map(
        name,
        background=[("disabled", disabled), ("pressed", pressed), ("active", hover)],
        bordercolor=[("disabled", disabled), ("pressed", pressed), ("active", hover)],
        lightcolor=[("pressed", pressed), ("active", hover)],
        darkcolor=[("pressed", pressed), ("active", hover)],
        foreground=[("disabled", "#94A3B8")])

  button_style("TButton", "white", C.TEXT, C.BORDER, "#F8FAFC", "#F1F5F9", "#F8FAFC")
  button_style("Primary.TButton", C.PRIMARY, "white", C.PRIMARY, C.PRIMARY_HOVER,
               "#1E40AF", "#93C5FD", bold=True)
  button_style("Danger.TButton", "white", C.DANGER, "#FCA5A5", "#FEF2F2", "#FEE2E2", "#F8FAFC")
  button_style("Ghost.TButton", C.SIDEBAR_SOFT, "white", C.SIDEBAR_LINE, C.SIDEBAR_LINE,
               "#475569", C.SIDEBAR_SOFT)

  focus_border = [("focus", C.PRIMARY)]
  style.configure("TEntry", fieldbackground="white", foreground=C.TEXT, padding=7,
                  bordercolor=C.BORDER, lightcolor=C.BORDER, darkcolor=C.BORDER)
  style.map("TEntry", bordercolor=focus_border, lightcolor=focus_border, darkcolor=focus_border)
  style.configure("TCombobox", fieldbackground="white", background="white", padding=6,
                  foreground=C.TEXT, bordercolor=C.BORDER, lightcolor=C.BORDER,
                  darkcolor=C.BORDER, arrowcolor=C.MUTED)
  style.map("TCombobox", fieldbackground=[("readonly", "white")],
            selectbackground=[("readonly", "white")], selectforeground=[("readonly", C.TEXT)],
            bordercolor=focus_border, lightcolor=focus_border, darkcolor=focus_border)

  style.configure("TCheckbutton", background=C.BG, foreground=C.TEXT, focuscolor=C.BG)
  style.configure("Card.TCheckbutton", background=C.CARD, foreground=C.MUTED, focuscolor=C.CARD)
  style.map("TCheckbutton", background=[("active", C.BG)])
  style.map("Card.TCheckbutton", background=[("active", C.CARD)])

  style.configure("TNotebook", background=C.BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
  style.configure("TNotebook.Tab", padding=(20, 10), background="#E2E8F0", foreground=C.MUTED,
                  font=F["bold"], borderwidth=0)
  style.map("TNotebook.Tab",
            background=[("selected", C.CARD), ("active", "#F8FAFC")],
            foreground=[("selected", C.PRIMARY)])

  style.configure("Treeview", rowheight=32, font=F["body"], background=C.CARD,
                  fieldbackground=C.CARD, foreground=C.TEXT, borderwidth=0)
  style.configure("Treeview.Heading", font=F["small_bold"], background="#F8FAFC",
                  foreground=C.MUTED, relief="flat", padding=(8, 9), borderwidth=0)
  style.map("Treeview.Heading", background=[("active", "#F1F5F9")])
  style.map("Treeview", background=[("selected", C.SELECT)], foreground=[("selected", C.TEXT)])

  style.configure("TScrollbar", background="#CBD5E1", troughcolor=C.CARD, borderwidth=0,
                  arrowsize=14, relief="flat")
  style.map("TScrollbar", background=[("active", "#94A3B8")])
  style.configure("TSeparator", background=C.BORDER)


# 2. SMALL WIDGET HELPERS & SCROLLABLE FRAME
LABEL_KINDS = {
    "body": ("body", C.TEXT), "bold": ("bold", C.TEXT), "muted": ("body", C.MUTED),
    "small": ("small", C.MUTED), "section": ("tiny", C.MUTED), "h1": ("h1", C.TEXT),
    "h2": ("h2", C.TEXT), "big": ("big", C.TEXT), "error": ("small", C.DANGER),
    "ok": ("small_bold", C.SUCCESS), "primary_big": ("big", C.PRIMARY),
    "hdr": ("h2", "white"), "hdr_big": ("h1", "white"), "hdr_sub": ("small", C.SIDEBAR_TEXT),
}


def _bg_of(widget) -> str:
  try:
    return widget.cget("bg")
  except tk.TclError:
    return C.BG


def label(parent, text: str = "", kind: str = "body", bg: Optional[str] = None, **kw) -> tk.Label:
  font_key, fg = LABEL_KINDS[kind]
  opts = dict(text=text, font=F[font_key], fg=fg, bg=bg or _bg_of(parent),
              anchor="w", justify="left")
  opts.update(kw)
  return tk.Label(parent, **opts)


def button(parent, text: str, command: Callable, kind: str = "secondary", **kw) -> ttk.Button:
  style = {"primary": "Primary.TButton", "danger": "Danger.TButton",
           "ghost": "Ghost.TButton"}.get(kind, "TButton")
  return ttk.Button(parent, text=text, command=command, style=style, cursor="hand2", **kw)


def text_box(parent, height: int = 4) -> tk.Text:
  return tk.Text(parent, height=height, wrap="word", font=F["body"], relief="flat",
                 bg="white", fg=C.TEXT, insertbackground=C.TEXT, padx=9, pady=7,
                 highlightthickness=1, highlightbackground=C.BORDER, highlightcolor=C.PRIMARY)


def set_readonly_text(widget: tk.Text, text: str) -> None:
  widget.configure(state="normal")
  widget.delete("1.0", tk.END)
  widget.insert(tk.END, text)
  widget.configure(state="disabled")


def bind_tree(widget, sequence: str, func: Callable, skip: tuple = ()) -> None:
  """Bind to a widget and all descendants (except instances of `skip`)."""
  if not (skip and isinstance(widget, skip)):
    widget.bind(sequence, func, add="+")
  for child in widget.winfo_children():
    bind_tree(child, sequence, func, skip)


def center_on(win, parent=None) -> None:
  win.update_idletasks()
  w, h = win.winfo_reqwidth(), win.winfo_reqheight()
  if parent is not None and parent.winfo_viewable():
    x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - h) // 3
  else:
    x = (win.winfo_screenwidth() - w) // 2
    y = (win.winfo_screenheight() - h) // 3
  win.geometry(f"+{max(x, 0)}+{max(y, 0)}")


class ScrollableFrame(ttk.Frame):
  """A responsive scrollable container widget using a canvas and scrollbar."""

  def __init__(self, container, *args, **kwargs):
    super().__init__(container, *args, **kwargs)
    self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0, bg=C.BG)
    self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
    self.scrollable_frame = ttk.Frame(self.canvas, style="TFrame")

    self.scrollable_frame.bind(
        "<Configure>",
        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    )

    self._window_id = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
    self.canvas.configure(yscrollcommand=self.scrollbar.set)

    self.canvas.pack(side="left", fill="both", expand=True)
    self.scrollbar.pack(side="right", fill="y")

    self.canvas.bind("<Configure>", self._on_canvas_configure)
    self.bind("<Enter>", self._bind_mousewheel)
    self.bind("<Leave>", self._unbind_mousewheel)

  def _on_canvas_configure(self, event):
    self.canvas.itemconfig(self._window_id, width=event.width)

  def _on_mousewheel(self, event):
    if sys.platform == "darwin":
      delta = -1 * event.delta
    elif event.num == 4:
      delta = -1
    elif event.num == 5:
      delta = 1
    else:
      delta = int(-1 * (event.delta / 120))
    try:
      self.canvas.yview_scroll(delta, "units")
    except Exception:
      pass

  def _bind_mousewheel(self, event):
    self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
    self.canvas.bind_all("<Button-4>", self._on_mousewheel)
    self.canvas.bind_all("<Button-5>", self._on_mousewheel)

  def _unbind_mousewheel(self, event):
    try:
      self.canvas.unbind_all("<MouseWheel>")
      self.canvas.unbind_all("<Button-4>")
      self.canvas.unbind_all("<Button-5>")
    except Exception:
      pass


class Card(tk.Frame):
  """White panel with a thin border. Put content into `.body`."""

  def __init__(self, parent, padding: int = 16):
    super().__init__(parent, bg=C.BORDER)
    surface = tk.Frame(self, bg=C.CARD)
    surface.pack(fill="both", expand=True, padx=1, pady=1)
    self.body = tk.Frame(surface, bg=C.CARD)
    self.body.pack(fill="both", expand=True, padx=padding, pady=padding)


class Badge(tk.Label):
  """Coloured pill showing a ticket status."""

  def __init__(self, parent):
    super().__init__(parent, font=F["small_bold"], padx=10, pady=3, bd=0)

  def set(self, status: str) -> None:
    fg, bg = STATUS_STYLE.get(status, (C.MUTED, C.BORDER))
    self.configure(text=status.upper(), fg=fg, bg=bg)


class Avatar(tk.Canvas):
  def __init__(self, parent, letter: str, color: str, size: int = 44, bg: str = C.SIDEBAR):
    super().__init__(parent, width=size, height=size, bg=bg, highlightthickness=0)
    self.create_oval(2, 2, size - 2, size - 2, fill=color, outline=color)
    self.create_text(size / 2, size / 2, text=letter.upper()[:1], fill="white",
                     font=(FONT_FAMILY, int(size * 0.4), "bold"))


class StatCard(tk.Frame):
  """Number + caption with a coloured accent bar. Optionally clickable."""

  def __init__(self, parent, caption: str, color: str, on_click: Optional[Callable] = None):
    super().__init__(parent, bg=C.BORDER)
    surface = tk.Frame(self, bg=C.CARD)
    surface.pack(fill="both", expand=True, padx=1, pady=1)
    tk.Frame(surface, bg=color, width=5).pack(side="left", fill="y")
    inner = tk.Frame(surface, bg=C.CARD)
    inner.pack(side="left", fill="both", expand=True, padx=14, pady=8)
    self.value = tk.Label(inner, text="0", font=F["big"], fg=C.TEXT, bg=C.CARD, anchor="w")
    self.value.pack(anchor="w")
    tk.Label(inner, text=caption, font=F["small"], fg=C.MUTED, bg=C.CARD, anchor="w").pack(anchor="w")
    if on_click:
      bind_tree(self, "<Button-1>", lambda _e: on_click())
      self._set_cursor(self, "hand2")

  def _set_cursor(self, widget, cursor):
    widget.configure(cursor=cursor)
    for child in widget.winfo_children():
      self._set_cursor(child, cursor)

  def set(self, number) -> None:
    self.value.configure(text=str(number))


class TicketTable(tk.Frame):
  """Colour-coded ticket list with scrollbar and an empty-state message."""

  COLUMNS = (
      ("id", "Ticket", 78, False), ("customer", "Customer", 130, True),
      ("device", "Device", 150, True), ("status", "Status", 125, False),
      ("tech", "Technician", 120, False), ("opened", "Opened", 88, False),
  )

  def __init__(self, parent, on_select: Callable, height: int = 14,
               empty_text: str = "No tickets to show."):
    super().__init__(parent, bg=C.BORDER)
    inner = tk.Frame(self, bg=C.CARD)
    inner.pack(fill="both", expand=True, padx=1, pady=1)
    self.tree = ttk.Treeview(inner, columns=[c[0] for c in self.COLUMNS], show="headings",
                             selectmode="browse", height=height)
    for key, title, width, stretch in self.COLUMNS:
      self.tree.heading(key, text=title, anchor="w")
      self.tree.column(key, width=width, minwidth=60, anchor="w", stretch=stretch)
    scroll = ttk.Scrollbar(inner, orient="vertical", command=self.tree.yview)
    self.tree.configure(yscrollcommand=scroll.set)
    self.tree.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    for status, (fg, _bg) in STATUS_STYLE.items():
      self.tree.tag_configure(status, foreground=fg)
    self.empty = tk.Label(inner, text=empty_text, font=F["body"], fg=C.MUTED, bg=C.CARD)
    self.tree.bind("<<TreeviewSelect>>", lambda _e: on_select())

  def load(self, tickets: List[ServiceTicket]) -> None:
    selected = self.selected_pk()
    self.tree.delete(*self.tree.get_children())
    for t in tickets:
      tech = t.assigned_technician.name if t.assigned_technician else "-"
      self.tree.insert("", "end", iid=str(t.pk), tags=(t.status,), values=(
          t.ticket_id, t.customer.name, f"{t.equipment.brand} {t.equipment.model}",
          f"\u25CF {t.status}", tech, t.created_at[:10]))
    if selected is not None and self.tree.exists(str(selected)):
      self.tree.selection_set(str(selected))
    if tickets:
      self.empty.place_forget()
    else:
      self.empty.place(relx=0.5, rely=0.4, anchor="center")
      self.empty.lift()

  def selected_pk(self) -> Optional[int]:
    sel = self.tree.selection()
    return int(sel[0]) if sel else None


class TicketDetail(Card):
  """Readable ticket summary."""

  def __init__(self, parent, show_email: bool = True, wrap: int = 380):
    super().__init__(parent, padding=16)
    self._show_email = show_email
    self.placeholder = label(self.body, "Select a ticket to see its details.", "muted",
                             pady=30, anchor="center", justify="center")
    self.placeholder.pack(fill="both", expand=True)
    self.content = tk.Frame(self.body, bg=C.CARD)

    head = tk.Frame(self.content, bg=C.CARD)
    head.pack(fill="x")
    self.heading = label(head, "", "h2")
    self.heading.pack(side="left")
    self.badge = Badge(head)
    self.badge.pack(side="right")

    grid = tk.Frame(self.content, bg=C.CARD)
    grid.pack(fill="x", pady=(12, 6))
    grid.columnconfigure(1, weight=1)
    self._rows: Dict[str, tk.Label] = {}
    for r, (key, caption) in enumerate((("customer", "Customer"), ("device", "Device"),
                                        ("tech", "Technician"), ("dates", "Timeline"))):
      label(grid, caption, "small").grid(row=r, column=0, sticky="nw", pady=3, padx=(0, 14))
      value = label(grid, "", "body", wraplength=wrap)
      value.grid(row=r, column=1, sticky="nw", pady=3)
      self._rows[key] = value

    ttk.Separator(self.content, orient="horizontal").pack(fill="x", pady=8)
    label(self.content, "PROBLEM REPORTED", "section").pack(anchor="w")
    self.problem = label(self.content, "", "body", wraplength=wrap)
    self.problem.pack(anchor="w", pady=(2, 10))
    label(self.content, "DIAGNOSIS", "section").pack(anchor="w")
    self.diagnosis = label(self.content, "", "body", wraplength=wrap)
    self.diagnosis.pack(anchor="w", pady=(2, 0))

  def clear(self) -> None:
    self.content.pack_forget()
    self.placeholder.pack(fill="both", expand=True)

  def show(self, ticket: ServiceTicket) -> None:
    self.placeholder.pack_forget()
    self.content.pack(fill="both", expand=True)
    self.heading.configure(text=ticket.ticket_id)
    self.badge.set(ticket.status)
    cust = ticket.customer
    who = f"{cust.name}  \u00B7  {cust.phone_number}"
    if self._show_email and cust.email:
      who += f"  \u00B7  {cust.email}"
    self._rows["customer"].configure(text=who)
    self._rows["device"].configure(text=ticket.equipment.get_equipment_info())
    tech = ticket.assigned_technician
    self._rows["tech"].configure(
        text=f"{tech.name}  ({tech.specialization})" if tech else "Not assigned yet")
    self._rows["dates"].configure(
        text=f"Opened {ticket.created_at.replace('T', ' ')}\nUpdated {ticket.updated_at.replace('T', ' ')}")
    self.problem.configure(text=ticket.issue)
    self.diagnosis.configure(text=ticket.diagnosis)


class StatusButtons(tk.Frame):
  """One button per status the current user may move the ticket to."""

  def __init__(self, parent):
    super().__init__(parent, bg=C.CARD)

  def clear(self) -> None:
    for child in self.winfo_children():
      child.destroy()
    label(self, "Select a ticket to update its status.", "small").pack(anchor="w")

  def set(self, statuses: List[str], callback: Callable[[str], None]) -> None:
    for child in self.winfo_children():
      child.destroy()
    if not statuses:
      label(self, "No further status changes available for this ticket.", "small").pack(anchor="w")
      return
    for status in statuses:
      kind = "danger" if status == "Cancelled" else ("primary" if status in ("Closed", "Ready for Pickup") else "secondary")
      button(self, f"Move to {status}", lambda s=status: callback(s), kind).pack(
          side="left", padx=(0, 8), pady=2)


class ProgressTracker(tk.Canvas):
  """Customer-facing repair progress: Received -> ... -> Picked up."""

  STEPS = (("Received", "Pending"), ("Diagnosing", "Diagnosing"), ("In repair", "In Repair"),
           ("Ready", "Ready for Pickup"), ("Picked up", "Closed"))

  def __init__(self, parent):
    super().__init__(parent, height=88, bg=C.CARD, highlightthickness=0)
    self._status: Optional[str] = None
    self.bind("<Configure>", lambda _e: self.draw(self._status))

  def draw(self, status: Optional[str]) -> None:
    self._status = status
    self.delete("all")
    if status is None:
      return
    width = max(self.winfo_width(), 320)
    if status == "Cancelled":
      self.create_text(width / 2, 44, text="This repair request was cancelled.",
                       fill=C.DANGER, font=F["bold"])
      return
    order = [s for _, s in self.STEPS]
    idx = order.index(status)
    n = len(self.STEPS)
    left, right, y, r = 56, width - 56, 30, 13
    step = (right - left) / (n - 1)
    for i in range(n - 1):
      color = C.SUCCESS if i < idx else "#CBD5E1"
      self.create_line(left + i * step + r, y, left + (i + 1) * step - r, y, fill=color, width=3)
    for i, (caption, _s) in enumerate(self.STEPS):
      x = left + i * step
      done = i < idx or (idx == n - 1 and i == idx)
      current = i == idx and not done
      if done:
        self.create_oval(x - r, y - r, x + r, y + r, fill=C.SUCCESS, outline=C.SUCCESS)
        self.create_text(x, y, text="\u2713", fill="white", font=(FONT_FAMILY, 12, "bold"))
      elif current:
        self.create_oval(x - r - 3, y - r - 3, x + r + 3, y + r + 3, fill=C.PRIMARY_SOFT, outline=C.PRIMARY_SOFT)
        self.create_oval(x - r, y - r, x + r, y + r, fill=C.PRIMARY, outline=C.PRIMARY)
        self.create_oval(x - 4, y - 4, x + 4, y + 4, fill="white", outline="white")
      else:
        self.create_oval(x - r, y - r, x + r, y + r, fill="white", outline="#CBD5E1", width=2)
      self.create_text(x, y + r + 20, text=caption,
                       font=F["small_bold"] if current else F["small"],
                       fill=C.TEXT if (done or current) else C.MUTED)


# 3. DIALOGS
class FormDialog(tk.Toplevel):
  """Modal form with inline error messages."""

  def __init__(self, parent, title: str, fields: List[dict], submit_text: str,
               on_submit: Callable[[dict], object], subtitle: str = "", width: int = 360):
    super().__init__(parent)
    self.withdraw()
    self.title(title)
    self.configure(bg=C.CARD)
    self.resizable(False, False)
    self.transient(parent.winfo_toplevel())
    self.result = None
    self._ok = False
    self._on_submit = on_submit
    self._fields: List[Tuple[dict, tk.Widget]] = []
    self._secret: List[ttk.Entry] = []

    body = tk.Frame(self, bg=C.CARD)
    body.pack(fill="both", expand=True, padx=28, pady=24)
    label(body, title, "h2").pack(anchor="w")
    if subtitle:
      label(body, subtitle, "muted", wraplength=width).pack(anchor="w", pady=(4, 4))
    for spec in fields:
      label(body, spec["label"], "bold").pack(anchor="w", pady=(12, 4))
      kind = spec.get("kind", "text")
      if kind == "choice":
        widget = ttk.Combobox(body, values=[o[0] for o in spec["options"]],
                              state="readonly", width=40)
        widget.current(0)
      else:
        widget = ttk.Entry(body, width=42, show="\u2022" if kind == "password" else "")
        if kind == "password":
          self._secret.append(widget)
      widget.pack(fill="x")
      self._fields.append((spec, widget))
    if self._secret:
      self._show_var = tk.BooleanVar(value=False)
      ttk.Checkbutton(body, text="Show password", variable=self._show_var,
                      style="Card.TCheckbutton", command=self._toggle_secret).pack(anchor="w", pady=(10, 0))
    self.error = label(body, "", "error", wraplength=width)
    self.error.pack(anchor="w", pady=(10, 0))
    row = tk.Frame(body, bg=C.CARD)
    row.pack(fill="x", pady=(14, 0))
    self.submit_btn = button(row, submit_text, self._submit, "primary")
    self.submit_btn.pack(side="right")
    button(row, "Cancel", self.destroy).pack(side="right", padx=(0, 8))
    self._submit_text = submit_text
    self.bind("<Return>", lambda _e: self._submit())
    self.bind("<Escape>", lambda _e: self.destroy())
    self.protocol("WM_DELETE_WINDOW", self.destroy)

  def _toggle_secret(self) -> None:
    for entry in self._secret:
      entry.configure(show="" if self._show_var.get() else "\u2022")

  def _values(self) -> dict:
    values = {}
    for spec, widget in self._fields:
      if spec.get("kind") == "choice":
        idx = widget.current()
        values[spec["key"]] = spec["options"][idx][1] if idx >= 0 else None
      else:
        values[spec["key"]] = widget.get()
    return values

  def _submit(self) -> None:
    self.error.configure(text="")
    self.submit_btn.configure(state="disabled", text="Please wait...")
    self.update_idletasks()
    try:
      result = self._on_submit(self._values())
    except AppError as exc:
      self.error.configure(text=str(exc))
    except Exception:
      log.exception("Dialog action failed")
      self.error.configure(text="Something went wrong. Details were saved to repair_system.log.")
    else:
      self.result, self._ok = result, True
      self.destroy()
      return
    self.submit_btn.configure(state="normal", text=self._submit_text)

  def run(self):
    center_on(self, self.master)
    self.deiconify()
    try:
      self.update_idletasks()
      self.wait_visibility()
      self.grab_set()
    except tk.TclError:  # pragma: no cover
      pass
    if self._fields:
      self._fields[0][1].focus_set()
    self.wait_window(self)
    return self.result if self._ok else None


class InfoDialog(tk.Toplevel):
  """Simple modal with a heading, key/value rows and a footer note."""

  def __init__(self, parent, title: str, heading: str, rows: List[Tuple[str, str]],
               footer: str = "", button_text: str = "Got it"):
    super().__init__(parent)
    self.withdraw()
    self.title(title)
    self.configure(bg=C.CARD)
    self.resizable(False, False)
    self.transient(parent.winfo_toplevel())
    body = tk.Frame(self, bg=C.CARD)
    body.pack(fill="both", expand=True, padx=28, pady=24)
    label(body, heading, "h2").pack(anchor="w")
    grid = tk.Frame(body, bg=C.CARD)
    grid.pack(fill="x", pady=(14, 6))
    for r, (key, value) in enumerate(rows):
      label(grid, key, "small").grid(row=r, column=0, sticky="nw", padx=(0, 18), pady=5)
      label(grid, value, "bold", wraplength=300).grid(row=r, column=1, sticky="nw", pady=5)
    if footer:
      label(body, footer, "muted", wraplength=420).pack(anchor="w", pady=(8, 0))
    row = tk.Frame(body, bg=C.CARD)
    row.pack(fill="x", pady=(16, 0))
    self.close_btn = button(row, button_text, self.destroy, "primary")
    self.close_btn.pack(side="right")
    self.bind("<Return>", lambda _e: self.destroy())
    self.bind("<Escape>", lambda _e: self.destroy())

  def run(self) -> None:
    center_on(self, self.master)
    self.deiconify()
    try:
      self.update_idletasks()
      self.wait_visibility()
      self.grab_set()
    except tk.TclError:  # pragma: no cover
      pass
    self.close_btn.focus_set()
    self.wait_window(self)


def show_ticket_created(parent, code: str) -> None:
  dlg = tk.Toplevel(parent)
  dlg.withdraw()
  dlg.title("Request received")
  dlg.configure(bg=C.CARD)
  dlg.resizable(False, False)
  dlg.transient(parent.winfo_toplevel())
  body = tk.Frame(dlg, bg=C.CARD)
  body.pack(fill="both", expand=True, padx=34, pady=26)
  label(body, "Your repair request was submitted", "h2", anchor="center").pack(fill="x")
  label(body, "Your ticket ID", "small", anchor="center").pack(fill="x", pady=(14, 0))
  label(body, code, "primary_big", anchor="center").pack(fill="x")
  label(body, "Keep this ID. You need it, together with your phone number,\nto track your repair.",
        "muted", anchor="center", justify="center").pack(fill="x", pady=(6, 14))
  row = tk.Frame(body, bg=C.CARD)
  row.pack()

  def copy():
    dlg.clipboard_clear()
    dlg.clipboard_append(code)
    copy_btn.configure(text="Copied \u2713")

  copy_btn = button(row, "Copy ID", copy)
  copy_btn.pack(side="left", padx=(0, 8))
  button(row, "Track my repair", dlg.destroy, "primary").pack(side="left")
  dlg.bind("<Return>", lambda _e: dlg.destroy())
  dlg.bind("<Escape>", lambda _e: dlg.destroy())
  center_on(dlg, parent)
  dlg.deiconify()
  try:
    dlg.update_idletasks()
    dlg.wait_visibility()
    dlg.grab_set()
  except tk.TclError:  # pragma: no cover
    pass
  dlg.wait_window(dlg)


def change_password_dialog(parent, service: RepairService, actor: User) -> bool:
  def submit(v):
    if v["new"] != v["confirm"]:
      raise ValidationError("The two new passwords do not match.")
    service.change_password(actor, v["old"], v["new"])
    return True

  dlg = FormDialog(
      parent, "Change password",
      [dict(label="Current password", key="old", kind="password"),
       dict(label="New password", key="new", kind="password"),
       dict(label="Repeat new password", key="confirm", kind="password")],
      "Change password", submit,
      subtitle="Use at least 8 characters, with letters and numbers.")
  return bool(dlg.run())


# 4. PORTAL BASE CLASS
def guarded(method):
  """Turn exceptions into friendly messages; nothing crashes the app."""

  @functools.wraps(method)
  def wrapper(self, *args, **kwargs):
    try:
      return method(self, *args, **kwargs)
    except AppError as exc:
      handler = getattr(self, "on_app_error", None)
      if handler:
        handler(str(exc))
      else:
        messagebox.showerror("Cannot complete action", str(exc), parent=self.window)
    except Exception:
      log.exception("Unexpected error in %s", method.__name__)
      messagebox.showerror(
          "Unexpected error",
          "Something went wrong. Your data is safe (the action was rolled back) "
          "and details were written to repair_system.log.", parent=self.window)
    return None

  return wrapper


class Portal:
  """Window with header bar, status bar, refresh loop and idle logout."""

  USES_IDLE_TIMEOUT = False

  def __init__(self, app: "RoleSelectorApp", title: str, size: str, min_size=(900, 600)):
    self.app = app
    self.service = app.service
    self.window = tk.Toplevel(app.root)
    self.window.title(title)
    self.window.geometry(size)
    self.window.minsize(*min_size)
    self.window.configure(bg=C.BG)
    self.window.protocol("WM_DELETE_WINDOW", self.close)
    self._after_id = None
    self._status_job = None
    self.status_label = None
    self.stamp_label = None
    self._last_activity = time.monotonic()
    for sequence in ("<Key>", "<Button>", "<Motion>"):
      self.window.bind(sequence, self._touch, add="+")
    self.window.bind("<F5>", lambda _e: self.refresh())
    self.window.bind("<Control-r>", lambda _e: self.refresh())

  def build_header(self, title: str, subtitle: str, letter: str, color: str,
                   buttons: List[Tuple[str, Callable]]) -> None:
    bar = tk.Frame(self.window, bg=C.SIDEBAR)
    bar.pack(fill="x", side="top")
    inner = tk.Frame(bar, bg=C.SIDEBAR)
    inner.pack(fill="x", padx=20, pady=12)
    Avatar(inner, letter, color).pack(side="left")
    text = tk.Frame(inner, bg=C.SIDEBAR)
    text.pack(side="left", padx=12)
    label(text, title, "hdr").pack(anchor="w")
    self.subtitle = label(text, subtitle, "hdr_sub")
    self.subtitle.pack(anchor="w")
    for text_, command in reversed(buttons):
      button(inner, text_, command, "ghost").pack(side="right", padx=(8, 0))

  def build_statusbar(self) -> None:
    bar = tk.Frame(self.window, bg="#E2E8F0")
    bar.pack(fill="x", side="bottom")
    self.status_label = tk.Label(bar, text="Ready", font=F["small"], fg=C.MUTED, bg="#E2E8F0", anchor="w")
    self.status_label.pack(side="left", padx=14, pady=5)
    self.stamp_label = tk.Label(bar, text="", font=F["small"], fg=C.MUTED, bg="#E2E8F0")
    self.stamp_label.pack(side="right", padx=14)

  def set_status(self, message: str, kind: str = "ok") -> None:
    if self.status_label is None or not self.window.winfo_exists():
      return
    color = {"ok": C.SUCCESS, "warn": C.WARN, "error": C.DANGER}.get(kind, C.MUTED)
    self.status_label.configure(text=message, fg=color)
    if self._status_job is not None:
      self.window.after_cancel(self._status_job)
    self._status_job = self.window.after(6000, self._reset_status)

  def _reset_status(self) -> None:
    self._status_job = None
    if self.status_label and self.window.winfo_exists():
      self.status_label.configure(text="Ready", fg=C.MUTED)

  def mark_refreshed(self) -> None:
    if self.stamp_label is not None and self.window.winfo_exists():
      self.stamp_label.configure(text=f"Updated {datetime.now():%H:%M:%S}")

  def _touch(self, _event=None) -> None:
    self._last_activity = time.monotonic()

  def start_refresh_loop(self) -> None:
    self._after_id = self.window.after(REFRESH_INTERVAL_MS, self._tick)

  def _tick(self) -> None:
    if not self.window.winfo_exists():
      return
    if self.USES_IDLE_TIMEOUT and time.monotonic() - self._last_activity > IDLE_TIMEOUT_SECONDS:
      messagebox.showinfo("Session expired", "You were logged out due to inactivity.")
      self.close()
      return
    try:
      self._do_refresh()
    except Exception:
      log.exception("Auto-refresh failed")
    if self.window.winfo_exists():
      self._after_id = self.window.after(REFRESH_INTERVAL_MS, self._tick)

  @guarded
  def refresh(self, *_args):
    self._do_refresh()
    self.set_status("Refreshed", "info")

  def _do_refresh(self) -> None:  
    pass

  def close(self) -> None:
    for job in (self._after_id, self._status_job):
      if job is not None:
        try:
          self.window.after_cancel(job)
        except Exception:
          pass
    if getattr(self, "_search_job", None) is not None:
      try:
        self.window.after_cancel(self._search_job)
      except Exception:
        pass
    try:
      self.window.destroy()
    except tk.TclError:
      pass
    self.app.portal_closed(self)


# 5. CUSTOMER PORTAL
class CustomerPortalWindow(Portal):

  def _clear_form(self) -> None:
    for key, ent in self.entries.items():
      if key != "device_type":
        try:
          ent.delete(0, tk.END)
        except Exception:
          pass
    if hasattr(self, "device_type_combo"):
      self.device_type_combo.current(0)
    if hasattr(self, "issue_text"):
      self.issue_text.delete("1.0", tk.END)

  def __init__(self, app):
    super().__init__(app, "Customer Portal", "820x740", min_size=(700, 620))
    self.build_header("Customer Portal", "Submit a repair request or track an existing one",
                      "C", C.PRIMARY, [("Close", self.close)])
    self.notebook = ttk.Notebook(self.window)
    self.notebook.pack(fill="both", expand=True, padx=20, pady=18)
    self._build_submit_tab()
    self._build_track_tab()

  def on_app_error(self, message: str) -> None:
    label_ = self.submit_error if self.notebook.index("current") == 0 else self.track_error
    label_.configure(text=message)

  def _field(self, parent, caption: str, row: int, col: int, hint: str = "") -> ttk.Entry:
    cell = tk.Frame(parent, bg=C.CARD)
    cell.grid(row=row, column=col, sticky="ew", padx=(0, 14) if col == 0 else (0, 0), pady=(0, 12))
    label(cell, caption, "bold").pack(anchor="w", pady=(0, 3))
    entry = ttk.Entry(cell)
    entry.pack(fill="x")
    if hint:
      label(cell, hint, "small").pack(anchor="w", pady=(2, 0))
    return entry

  def _build_submit_tab(self) -> None:
    tab = ttk.Frame(self.notebook)
    self.notebook.add(tab, text="  Submit a repair request  ")
    
    scroll = ScrollableFrame(tab)
    scroll.pack(fill="both", expand=True)
    
    card = Card(scroll.scrollable_frame, padding=22)
    card.pack(fill="both", expand=True, padx=4, pady=4)
    form = card.body
    label(form, "Tell us about your device", "h2").pack(anchor="w")
    label(form, "Fields marked * are required.", "small").pack(anchor="w", pady=(0, 14))
    grid = tk.Frame(form, bg=C.CARD)
    grid.pack(fill="x")
    grid.columnconfigure(0, weight=1)
    grid.columnconfigure(1, weight=1)
    
    self.entries = {
        "name": self._field(grid, "Full name *", 0, 0),
        "email": self._field(grid, "Email", 0, 1, "Optional"),
        "phone": self._field(grid, "Phone number *", 1, 0, "Used to look up your ticket"),
    }
    
    dt_cell = tk.Frame(grid, bg=C.CARD)
    dt_cell.grid(row=1, column=1, sticky="ew", pady=(0, 12))
    label(dt_cell, "Device type *", "bold").pack(anchor="w", pady=(0, 3))
    self.device_type_combo = ttk.Combobox(dt_cell, values=["Laptop", "Desktop PC"], state="readonly")
    self.device_type_combo.pack(fill="x")
    self.device_type_combo.current(0)

    self.brand_entry = self._field(grid, "Brand / Manufacturer *", 2, 0, "e.g. ASUS, Lenovo, Custom")
    self.model_entry = self._field(grid, "Model / Series *", 2, 1, "e.g. TUF Gaming F15, Mid-Tower")
    self.sn_entry = self._field(grid, "Serial number", 3, 0, "Optional")

    self.entries.update({
        "brand": self.brand_entry,
        "model": self.model_entry,
        "sn": self.sn_entry,
    })

    label(form, "Describe the problem *", "bold").pack(anchor="w", pady=(2, 3))
    self.issue_text = text_box(form, height=5)
    self.issue_text.pack(fill="x")
    self.submit_error = label(form, "", "error", wraplength=640)
    self.submit_error.pack(anchor="w", pady=(10, 0))
    row = tk.Frame(form, bg=C.CARD)
    row.pack(fill="x", pady=(10, 0))
    button(row, "Submit repair request", self.submit_ticket, "primary").pack(side="right")
    button(row, "Clear", self._clear_form).pack(side="right", padx=(0, 8))
    self.entries["name"].focus_set()

  @guarded
  def submit_ticket(self):
    self.submit_error.configure(text="")
    e = self.entries
    phone = e["phone"].get()
    dtype = self.device_type_combo.get()
    
    try:
      code = self.service.submit_ticket(
          e["name"].get(), e["email"].get(), phone, dtype,
          e["brand"].get(), e["model"].get(),
          e["sn"].get(), self.issue_text.get("1.0", tk.END))
    except AppError as exc:
      self.submit_error.configure(text=str(exc))
      return

    self._clear_form()
    self.track_id.delete(0, tk.END)
    self.track_id.insert(0, code)
    self.track_phone.delete(0, tk.END)
    self.track_phone.insert(0, phone)
    show_ticket_created(self.window, code)
    self.notebook.select(1)
    self.track()

  # ---- track tab ----
  def _build_track_tab(self) -> None:
    tab = ttk.Frame(self.notebook)
    self.notebook.add(tab, text="  Track my repair  ")
    
    scroll = ScrollableFrame(tab)
    scroll.pack(fill="both", expand=True)
    
    container = ttk.Frame(scroll.scrollable_frame, padding=4)
    container.pack(fill="both", expand=True)

    lookup = Card(container, padding=20)
    lookup.pack(fill="x")
    body = lookup.body
    label(body, "Check your repair status", "h2").pack(anchor="w")
    label(body, "Enter the ticket ID you received and the phone number used on the request.",
          "small").pack(anchor="w", pady=(0, 12))
    row = tk.Frame(body, bg=C.CARD)
    row.pack(fill="x")
    row.columnconfigure(0, weight=1)
    row.columnconfigure(1, weight=1)
    left = tk.Frame(row, bg=C.CARD)
    left.grid(row=0, column=0, sticky="ew", padx=(0, 12))
    label(left, "Ticket ID", "bold").pack(anchor="w", pady=(0, 3))
    self.track_id = ttk.Entry(left)
    self.track_id.pack(fill="x")
    right = tk.Frame(row, bg=C.CARD)
    right.grid(row=0, column=1, sticky="ew", padx=(0, 12))
    label(right, "Phone number", "bold").pack(anchor="w", pady=(0, 3))
    self.track_phone = ttk.Entry(right)
    self.track_phone.pack(fill="x")
    action = tk.Frame(row, bg=C.CARD)
    action.grid(row=0, column=2, sticky="s")
    button(action, "Check status", self.track, "primary").pack()
    self.track_error = label(body, "", "error", wraplength=640)
    self.track_error.pack(anchor="w", pady=(8, 0))
    for entry in (self.track_id, self.track_phone):
      entry.bind("<Return>", lambda _e: self.track())

    self.result = tk.Frame(container, bg=C.BG)
    progress_card = Card(self.result, padding=10)
    progress_card.pack(fill="x", pady=(14, 0))
    self.tracker = ProgressTracker(progress_card.body)
    self.tracker.pack(fill="x")
    self.detail = TicketDetail(self.result, show_email=False, wrap=560)
    self.detail.pack(fill="x", pady=(14, 0))

  @guarded
  def track(self):
    self.track_error.configure(text="")
    try:
      ticket = self.service.lookup_ticket(self.track_id.get(), self.track_phone.get())
    except AppError:
      self.result.pack_forget()
      raise
    self.result.pack(fill="x")
    self.tracker.draw(ticket.status)
    self.detail.show(ticket)


# 6. EMPLOYEE (TECHNICIAN) PORTAL
class EmployeePortalWindow(Portal):
  USES_IDLE_TIMEOUT = True

  def __init__(self, app, technician: Technician):
    super().__init__(app, f"Technician Portal - {technician.name}", "1180x740", min_size=(1020, 640))
    self.tech = technician
    self._current_pk: Optional[int] = None
    self.build_header(
        "Technician Portal", f"{technician.name}  \u00B7  {technician.specialization}",
        technician.name.replace("Engr. ", "")[:1], "#7C3AED",
        [("Refresh", self.refresh), ("Change password", self.change_password),
         ("Log out", self.close)])
    self.build_statusbar()

    scroll = ScrollableFrame(self.window)
    scroll.pack(fill="both", expand=True)

    content = tk.Frame(scroll.scrollable_frame, bg=C.BG)
    content.pack(fill="both", expand=True, padx=20, pady=16)
    content.columnconfigure(0, weight=3)
    content.columnconfigure(1, weight=2, minsize=430)
    content.rowconfigure(1, weight=1)

    toolbar = tk.Frame(content, bg=C.BG)
    toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    label(toolbar, "My assigned repairs", "h2").pack(side="left")
    self.hide_done = tk.BooleanVar(value=True)
    ttk.Checkbutton(toolbar, text="Hide closed / cancelled", variable=self.hide_done,
                    command=self._do_refresh).pack(side="right")
    self.table = TicketTable(content, self.on_select, empty_text="No repairs assigned to you right now.")
    self.table.grid(row=1, column=0, sticky="nsew", padx=(0, 16))

    side = tk.Frame(content, bg=C.BG)
    side.grid(row=0, column=1, rowspan=2, sticky="nsew")
    self.detail = TicketDetail(side, wrap=380)
    self.detail.pack(fill="x")
    update = Card(side, padding=16)
    update.pack(fill="x", pady=(14, 0))
    label(update.body, "WORK NOTES", "section").pack(anchor="w")
    self.diag = text_box(update.body, height=4)
    self.diag.pack(fill="x", pady=(4, 8))
    button(update.body, "Save diagnosis", self.save_diagnosis, "primary").pack(anchor="w")
    ttk.Separator(update.body, orient="horizontal").pack(fill="x", pady=12)
    label(update.body, "UPDATE STATUS", "section").pack(anchor="w", pady=(0, 4))
    self.status_buttons = StatusButtons(update.body)
    self.status_buttons.pack(anchor="w", fill="x")
    self.status_buttons.clear()

    self._do_refresh()
    self.start_refresh_loop()

  def _do_refresh(self) -> None:
    tickets = self.service.list_tickets(self.tech)
    if self.hide_done.get():
      tickets = [t for t in tickets if t.status not in ServiceTicket.TERMINAL_STATUSES]
    self.table.load(tickets)
    active = sum(1 for t in tickets if t.status in ServiceTicket.ACTIVE_STATUSES)
    ready = sum(1 for t in tickets if t.status == "Ready for Pickup")
    self.subtitle.configure(
        text=f"{self.tech.name}  \u00B7  {self.tech.specialization}  \u00B7  "
             f"{active} in progress, {ready} ready for pickup")
    if self.table.selected_pk() is None:
      self._current_pk = None
      self.detail.clear()
      self.status_buttons.clear()
    else:
      self._show_selected()
    self.mark_refreshed()

  @guarded
  def on_select(self):
    self._show_selected()

  def _show_selected(self) -> None:
    pk = self.table.selected_pk()
    if pk is None:
      return
    ticket = self.service.get_ticket(self.tech, pk)
    self.detail.show(ticket)
    self.status_buttons.set(ticket.allowed_next_statuses(self.tech), self.apply_status)
    if pk != self._current_pk:
      self._current_pk = pk
      self.diag.delete("1.0", tk.END)
      if ticket.diagnosis != ServiceTicket.NO_DIAGNOSIS:
        self.diag.insert("1.0", ticket.diagnosis)

  def _selected_or_warn(self) -> Optional[int]:
    pk = self.table.selected_pk()
    if pk is None:
      self.set_status("Select a ticket first.", "warn")
    return pk

  @guarded
  def save_diagnosis(self):
    pk = self._selected_or_warn()
    if pk is None:
      return
    ticket = self.service.save_diagnosis(self.tech, pk, self.diag.get("1.0", tk.END))
    self.set_status(f"Diagnosis saved for {ticket.ticket_id}.")
    self._show_selected()

  @guarded
  def apply_status(self, new_status: str):
    pk = self._selected_or_warn()
    if pk is None:
      return
    ticket = self.service.change_status(self.tech, pk, new_status)
    self.set_status(f"{ticket.ticket_id} moved to {new_status}.")
    self._do_refresh()

  @guarded
  def change_password(self):
    if change_password_dialog(self.window, self.service, self.tech):
      self.set_status("Password changed.")


# 7. OWNER PORTAL
class OwnerPortalWindow(Portal):
  USES_IDLE_TIMEOUT = True

  def __init__(self, app, owner: Owner):
    super().__init__(app, "Owner / Administrator Portal", "1280x800", min_size=(1100, 680))
    self.owner = owner
    self._current_pk: Optional[int] = None
    self._assign_ids: List[str] = []
    self._audit_rows: list = []
    self.build_header("Owner Portal", "Shop oversight, assignments and security", "A", C.SUCCESS,
                      [("Refresh", self.refresh), ("Log out", self.close)])
    self.build_statusbar()

    stats = tk.Frame(self.window, bg=C.BG)
    stats.pack(fill="x", padx=20, pady=(16, 0))
    self.stat_cards: Dict[str, StatCard] = {}
    spec = (("Pending", "Pending", STATUS_STYLE["Pending"][0]),
            ("Diagnosing", "Diagnosing", STATUS_STYLE["Diagnosing"][0]),
            ("In Repair", "In Repair", STATUS_STYLE["In Repair"][0]),
            ("Ready for Pickup", "Ready for pickup", STATUS_STYLE["Ready for Pickup"][0]),
            ("Closed", "Closed", STATUS_STYLE["Closed"][0]),
            ("Available technicians", "Free technicians", C.PRIMARY))
    for i, (key, caption, color) in enumerate(spec):
      stats.columnconfigure(i, weight=1, uniform="stat")
      handler = (lambda: self._goto_tab(1)) if key == "Available technicians" else (lambda k=key: self._filter_by(k))
      card = StatCard(stats, caption, color, on_click=handler)
      card.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0))
      self.stat_cards[key] = card

    self.notebook = ttk.Notebook(self.window)
    self.notebook.pack(fill="both", expand=True, padx=20, pady=16)
    self._build_tickets_tab()
    self._build_technicians_tab()
    self._build_audit_tab()
    self._build_settings_tab()
    self._do_refresh()
    self.start_refresh_loop()

  def _goto_tab(self, index: int) -> None:
    self.notebook.select(index)

  def _filter_by(self, status: str) -> None:
    self.filter_combo.set(status)
    self.notebook.select(0)
    self.refresh_tickets()

  # ---- tickets tab ----
  def _build_tickets_tab(self) -> None:
    tab = ttk.Frame(self.notebook)
    self.notebook.add(tab, text="  Tickets  ")

    scroll = ScrollableFrame(tab)
    scroll.pack(fill="both", expand=True)

    inner_content = tk.Frame(scroll.scrollable_frame, bg=C.BG, padx=4, pady=4)
    inner_content.pack(fill="both", expand=True)
    inner_content.columnconfigure(0, weight=3)
    inner_content.columnconfigure(1, weight=2, minsize=430)
    inner_content.rowconfigure(1, weight=1)

    bar = tk.Frame(inner_content, bg=C.BG)
    bar.grid(row=0, column=0, sticky="ew", pady=(0, 8), padx=(0, 16))
    label(bar, "Status", "small").pack(side="left", padx=(0, 6))
    self.filter_combo = ttk.Combobox(bar, state="readonly", width=16,
                                     values=["All"] + ServiceTicket.VALID_STATUSES)
    self.filter_combo.set("All")
    self.filter_combo.pack(side="left")
    self.filter_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_tickets())
    self.search_var = tk.StringVar()
    search = ttk.Entry(bar, textvariable=self.search_var, width=28)
    search.pack(side="right")
    label(bar, "Search", "small").pack(side="right", padx=(0, 6))
    self.search_var.trace_add("write", lambda *_a: self._schedule_search())
    self._search_job = None
    button(bar, "Reset filters", self._reset_filters).pack(side="left", padx=10)

    self.table = TicketTable(inner_content, self.on_select, height=16,
                             empty_text="No tickets match your filters.")
    self.table.grid(row=1, column=0, sticky="nsew", padx=(0, 16))

    side = tk.Frame(inner_content, bg=C.BG)
    side.grid(row=0, column=1, rowspan=2, sticky="nsew")
    self.detail = TicketDetail(side, wrap=380)
    self.detail.pack(fill="x")
    manage = Card(side, padding=16)
    manage.pack(fill="x", pady=(14, 0))
    label(manage.body, "ASSIGN TECHNICIAN", "section").pack(anchor="w")
    row = tk.Frame(manage.body, bg=C.CARD)
    row.pack(fill="x", pady=(4, 0))
    self.assign_combo = ttk.Combobox(row, state="readonly", width=30)
    self.assign_combo.pack(side="left", fill="x", expand=True)
    button(row, "Assign", self.assign_tech, "primary").pack(side="left", padx=(8, 0))
    ttk.Separator(manage.body, orient="horizontal").pack(fill="x", pady=12)
    label(manage.body, "UPDATE STATUS", "section").pack(anchor="w", pady=(0, 4))
    self.status_buttons = StatusButtons(manage.body)
    self.status_buttons.pack(anchor="w", fill="x")
    self.status_buttons.clear()

  def _schedule_search(self) -> None:
    if self._search_job is not None:
      self.window.after_cancel(self._search_job)
    self._search_job = self.window.after(300, self._run_search)

  def _run_search(self) -> None:
    self._search_job = None
    try:
      self.refresh_tickets()
    except Exception:
      log.exception("Search failed")

  def _reset_filters(self) -> None:
    self.filter_combo.set("All")
    self.search_var.set("")
    self.refresh_tickets()

  # ---- technicians tab ----
  def _build_technicians_tab(self) -> None:
    tab = ttk.Frame(self.notebook)
    self.notebook.add(tab, text="  Technicians  ")

    scroll = ScrollableFrame(tab)
    scroll.pack(fill="both", expand=True)

    inner_content = tk.Frame(scroll.scrollable_frame, bg=C.BG, padx=4, pady=4)
    inner_content.pack(fill="both", expand=True)

    bar = tk.Frame(inner_content, bg=C.BG)
    bar.pack(fill="x", pady=(0, 8))
    button(bar, "+ Add technician", self.add_tech, "primary").pack(side="left")
    button(bar, "Activate / deactivate", self.toggle_tech).pack(side="left", padx=8)
    button(bar, "Reset password", self.reset_tech_password).pack(side="left")
    frame = tk.Frame(inner_content, bg=C.BORDER)
    frame.pack(fill="both", expand=True)
    inner = tk.Frame(frame, bg=C.CARD)
    inner.pack(fill="both", expand=True, padx=1, pady=1)
    cols = (("name", "Name", 200), ("specialization", "Specialization", 260),
            ("email", "Email", 240), ("state", "State", 140))
    self.tech_tree = ttk.Treeview(inner, columns=[c[0] for c in cols], show="headings",
                                  selectmode="browse")
    for key, title, width in cols:
      self.tech_tree.heading(key, text=title, anchor="w")
      self.tech_tree.column(key, width=width, anchor="w")
    self.tech_tree.pack(fill="both", expand=True)
    self.tech_tree.tag_configure("Available", foreground=STATUS_STYLE["Ready for Pickup"][0])
    self.tech_tree.tag_configure("Busy", foreground=STATUS_STYLE["In Repair"][0])
    self.tech_tree.tag_configure("Deactivated", foreground=C.MUTED)

  # ---- audit tab ----
  def _build_audit_tab(self) -> None:
    tab = ttk.Frame(self.notebook)
    self.notebook.add(tab, text="  Audit log  ")

    scroll = ScrollableFrame(tab)
    scroll.pack(fill="both", expand=True)

    inner_content = tk.Frame(scroll.scrollable_frame, bg=C.BG, padx=4, pady=4)
    inner_content.pack(fill="both", expand=True)

    bar = tk.Frame(inner_content, bg=C.BG)
    bar.pack(fill="x", pady=(0, 8))
    label(bar, "Every login, assignment and status change is recorded here.", "muted").pack(side="left")
    self.audit_search = tk.StringVar()
    ttk.Entry(bar, textvariable=self.audit_search, width=28).pack(side="right")
    label(bar, "Filter", "small").pack(side="right", padx=(0, 6))
    self.audit_search.trace_add("write", lambda *_a: self._render_audit())
    frame = tk.Frame(inner_content, bg=C.BORDER)
    frame.pack(fill="both", expand=True)
    inner = tk.Frame(frame, bg=C.CARD)
    inner.pack(fill="both", expand=True, padx=1, pady=1)
    cols = (("ts", "Time", 160), ("actor", "Actor", 240), ("action", "Action", 190), ("detail", "Detail", 420))
    self.audit_tree = ttk.Treeview(inner, columns=[c[0] for c in cols], show="headings")
    for key, title, width in cols:
      self.audit_tree.heading(key, text=title, anchor="w")
      self.audit_tree.column(key, width=width, anchor="w", stretch=(key == "detail"))
    scroll_tree = ttk.Scrollbar(inner, orient="vertical", command=self.audit_tree.yview)
    self.audit_tree.configure(yscrollcommand=scroll_tree.set)
    self.audit_tree.pack(side="left", fill="both", expand=True)
    scroll_tree.pack(side="right", fill="y")
    self.audit_tree.tag_configure("bad", foreground=C.DANGER)

  # ---- settings tab ----
  def _build_settings_tab(self) -> None:
    tab = ttk.Frame(self.notebook)
    self.notebook.add(tab, text="  Settings  ")

    scroll = ScrollableFrame(tab)
    scroll.pack(fill="both", expand=True)

    inner_content = tk.Frame(scroll.scrollable_frame, bg=C.BG, padx=4, pady=4)
    inner_content.pack(fill="both", expand=True)

    for title, text, btn_text, command in (
        ("Security", "Change the owner password. Use letters and numbers, 8+ characters.",
         "Change owner password", self.change_password),
        ("Data", f"All data is stored in:\n{DB_PATH}\nCreate a backup copy before making big changes.",
         "Back up database...", self.backup)):
      card = Card(inner_content, padding=18)
      card.pack(fill="x", pady=(0, 12), anchor="n")
      label(card.body, title, "h2").pack(anchor="w")
      label(card.body, text, "muted", wraplength=760).pack(anchor="w", pady=(4, 10))
      button(card.body, btn_text, command).pack(anchor="w")

  # ---- refresh ----
  def _do_refresh(self) -> None:
    self.refresh_tickets()
    self.refresh_technicians()
    self.refresh_audit()
    stats = self.service.stats(self.owner)
    for key, card in self.stat_cards.items():
      card.set(stats.get(key, 0))
    self.mark_refreshed()

  def refresh_tickets(self) -> None:
    tickets = self.service.list_tickets(self.owner, self.filter_combo.get() or "All",
                                        self.search_var.get())
    self.table.load(tickets)
    if self.table.selected_pk() is None:
      self._current_pk = None
      self.detail.clear()
      self.status_buttons.clear()
    else:
      self._show_selected()

  def refresh_technicians(self) -> None:
    techs = self.service.list_technicians(self.owner)
    selected = self.tech_tree.selection()
    self.tech_tree.delete(*self.tech_tree.get_children())
    for t in techs:
      state = "Deactivated" if not t.is_active else ("Available" if t.is_available else "Busy")
      self.tech_tree.insert("", "end", iid=t.user_id, tags=(state,),
                            values=(t.name, t.specialization, t.email or "-", f"\u25CF {state}"))
    if selected and self.tech_tree.exists(selected[0]):
      self.tech_tree.selection_set(selected[0])
    active = [t for t in techs if t.is_active]
    self._assign_ids = [t.user_id for t in active]
    self.assign_combo["values"] = [f"{t.name}  -  {t.specialization}" for t in active]

  def refresh_audit(self) -> None:
    self._audit_rows = list(self.service.list_audit(self.owner))
    self._render_audit()

  def _render_audit(self) -> None:
    needle = self.audit_search.get().strip().lower()
    self.audit_tree.delete(*self.audit_tree.get_children())
    for r in self._audit_rows:
      row = (r["ts"].replace("T", " "), r["actor"], r["action"], r["detail"])
      if needle and needle not in " ".join(row).lower():
        continue
      self.audit_tree.insert("", "end", values=row, tags=("bad",) if "FAILED" in r["action"] else ())

  # ---- ticket actions ----
  @guarded
  def on_select(self):
    self._show_selected()

  def _show_selected(self) -> None:
    pk = self.table.selected_pk()
    if pk is None:
      return
    ticket = self.service.get_ticket(self.owner, pk)
    self.detail.show(ticket)
    self.status_buttons.set(ticket.allowed_next_statuses(self.owner), self.apply_status)
    if pk != self._current_pk:
      self._current_pk = pk
      self.assign_combo.set("")

  def _selected_or_warn(self) -> Optional[int]:
    pk = self.table.selected_pk()
    if pk is None:
      self.set_status("Select a ticket first.", "warn")
    return pk

  @guarded
  def assign_tech(self):
    pk = self._selected_or_warn()
    if pk is None:
      return
    idx = self.assign_combo.current()
    if idx < 0 or idx >= len(self._assign_ids):
      self.set_status("Choose a technician from the list first.", "warn")
      return
    ticket = self.service.assign_technician(self.owner, pk, self._assign_ids[idx])
    self.set_status(f"{ticket.ticket_id} assigned to {ticket.assigned_technician.name}.")
    self._do_refresh()

  @guarded
  def apply_status(self, new_status: str):
    pk = self._selected_or_warn()
    if pk is None:
      return
    if new_status in ("Closed", "Cancelled") and not messagebox.askyesno(
        "Please confirm", f"Mark this ticket as {new_status}? This cannot be undone.",
        parent=self.window):
      return
    ticket = self.service.change_status(self.owner, pk, new_status)
    self.set_status(f"{ticket.ticket_id} moved to {new_status}.")
    self._do_refresh()

  # ---- technician actions ----
  def _selected_tech(self) -> Optional[str]:
    sel = self.tech_tree.selection()
    if not sel:
      self.set_status("Select a technician first.", "warn")
      return None
    return sel[0]

  @guarded
  def add_tech(self):
    def submit(v):
      return self.service.add_technician(self.owner, v["name"], v["email"], v["spec"], v["pwd"])

    dlg = FormDialog(
        self.window, "Add technician",
        [dict(label="Full name *", key="name"), dict(label="Email", key="email"),
         dict(label="Specialization *", key="spec"),
         dict(label="Initial password *", key="pwd", kind="password")],
        "Add technician", submit,
        subtitle="The technician can change this password after signing in.")
    tech = dlg.run()
    if tech:
      self.set_status(f"Technician {tech.name} added.")
      self._do_refresh()

  @guarded
  def toggle_tech(self):
    tid = self._selected_tech()
    if tid is None:
      return
    state = self.tech_tree.item(tid, "values")[3]
    activate = "Deactivated" in state
    self.service.set_technician_active(self.owner, tid, activate)
    self.set_status("Technician activated." if activate else "Technician deactivated.")
    self._do_refresh()

  @guarded
  def reset_tech_password(self):
    tid = self._selected_tech()
    if tid is None:
      return

    def submit(v):
      if v["new"] != v["confirm"]:
        raise ValidationError("The two passwords do not match.")
      self.service.reset_technician_password(self.owner, tid, v["new"])
      return True

    dlg = FormDialog(
        self.window, "Reset technician password",
        [dict(label="New password", key="new", kind="password"),
         dict(label="Repeat new password", key="confirm", kind="password")],
        "Reset password", submit)
    if dlg.run():
      self.set_status("Technician password reset.")
      self.refresh_audit()

  # ---- settings actions ----
  @guarded
  def change_password(self):
    if change_password_dialog(self.window, self.service, self.owner):
      self.set_status("Owner password changed.")

  @guarded
  def backup(self):
    default = f"repair_backup_{datetime.now():%Y%m%d_%H%M%S}.db"
    path = filedialog.asksaveasfilename(
        parent=self.window, defaultextension=".db", initialfile=default,
        filetypes=[("SQLite database", "*.db"), ("All files", "*.*")])
    if not path:
      return
    self.service.backup_to(self.owner, path)
    self.set_status("Backup completed.")


# 8. ROLE SELECTOR (start screen)
class RoleCard(tk.Frame):
  """Big clickable card used on the start screen."""

  def __init__(self, parent, letter: str, color: str, title: str, description: str,
               command: Callable):
    super().__init__(parent, bg=C.BORDER)
    self._command = command
    surface = tk.Frame(self, bg=C.CARD)
    surface.pack(fill="both", expand=True, padx=2, pady=2)
    inner = tk.Frame(surface, bg=C.CARD)
    inner.pack(fill="both", expand=True, padx=22, pady=24)
    Avatar(inner, letter, color, size=60, bg=C.CARD).pack(anchor="w")
    label(inner, title, "h2").pack(anchor="w", pady=(16, 4))
    label(inner, description, "muted", wraplength=210, justify="left").pack(anchor="w")
    tk.Frame(inner, bg=C.CARD, height=16).pack()
    self.open_btn = button(inner, "Open portal  \u2192", command, "primary")
    self.open_btn.pack(anchor="w", side="bottom")
    bind_tree(self, "<Button-1>", lambda _e: self._command(), skip=(ttk.Button,))
    bind_tree(self, "<Enter>", lambda _e: self.after_idle(self._sync_hover))
    bind_tree(self, "<Leave>", lambda _e: self.after_idle(self._sync_hover))
    self._set_cursor(self)

  def _set_cursor(self, widget) -> None:
    widget.configure(cursor="hand2")
    for child in widget.winfo_children():
      self._set_cursor(child)

  def _pointer_inside(self) -> bool:
    try:
      widget = self.winfo_containing(*self.winfo_pointerxy())
    except (tk.TclError, KeyError):
      return False
    while widget is not None:
      if widget is self:
        return True
      widget = getattr(widget, "master", None)
    return False

  def _sync_hover(self) -> None:
    try:
      self.configure(bg=C.PRIMARY if self._pointer_inside() else C.BORDER)
    except tk.TclError:
      pass


class RoleSelectorApp:

  def __init__(self, root, service: RepairService):
    self.root = root
    self.service = service
    self._open: Dict[str, Portal] = {}
    apply_theme(root)
    root.title("Computer Repair & Service Monitoring System")
    root.geometry("900x560")
    root.minsize(820, 520)
    root.protocol("WM_DELETE_WINDOW", self.quit)
    root.report_callback_exception = self._on_tk_error

    banner = tk.Frame(root, bg=C.SIDEBAR)
    banner.pack(fill="x")
    head = tk.Frame(banner, bg=C.SIDEBAR)
    head.pack(fill="x", padx=40, pady=30)
    label(head, "Computer Repair & Service Monitoring", "hdr_big").pack(anchor="w")
    label(head, "Track every repair from the front desk to the workbench to pickup.",
          "hdr_sub").pack(anchor="w", pady=(4, 0))

    label(root, "Who is using the system?", "h2").pack(anchor="w", padx=40, pady=(26, 12))
    row = tk.Frame(root, bg=C.BG)
    row.pack(fill="x", padx=40)
    cards = (
        ("C", C.PRIMARY, "Customer", "Submit a repair request or track the progress of your device.",
         self.open_customer),
        ("T", "#7C3AED", "Technician", "See your assigned repairs, write diagnoses and update status.",
         self.open_employee),
        ("A", C.SUCCESS, "Owner / Admin", "Assign technicians, manage staff, review the audit log.",
         self.open_owner),
    )
    for i, (letter, color, title, desc, command) in enumerate(cards):
      row.columnconfigure(i, weight=1, uniform="role")
      RoleCard(row, letter, color, title, desc, command).grid(
          row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 16, 0))
    label(root, f"Data file: {DB_PATH}", "small").pack(side="bottom", anchor="w", padx=40, pady=12)

  def startup(self) -> None:
    """Runs once the window is visible: demo info, then first-time setup if needed."""
    if self.service.seeded:
      InfoDialog(
          self.root, "Demo data loaded", "Demo data is ready",
          [("Owner password", MOCK_OWNER_PASSWORD),
           ("Technician password", f"{MOCK_TECH_PASSWORD}  (Santos, Reyes, Dela Cruz)"),
           ("Track a repair", "TKT-00001  +  phone 0917 555 0101"),
           ("Track a repair", "TKT-00004  +  phone 0928 555 0104")],
          footer="These logins are for demonstration only. Change the passwords inside "
                 "the app before using the system for real.").run()
    if not self.service.has_owner_password() and not self.first_run_setup():
      self.quit()

  def first_run_setup(self) -> bool:
    def submit(v):
      if v["new"] != v["confirm"]:
        raise ValidationError("The two passwords do not match.")
      self.service.set_initial_owner_password(v["new"])
      return True

    dlg = FormDialog(
        self.root, "Welcome - create the owner password",
        [dict(label="New owner password", key="new", kind="password"),
         dict(label="Repeat password", key="confirm", kind="password")],
        "Create password", submit,
        subtitle="There is no default password. Use at least 8 characters, "
                 "with letters and numbers.")
    return bool(dlg.run())

  def _on_tk_error(self, exc_type, exc, tb) -> None:
    log.error("Unhandled Tk callback error", exc_info=(exc_type, exc, tb))
    messagebox.showerror(
        "Unexpected error",
        "Something went wrong. Details were written to repair_system.log.", parent=self.root)

  def _focus_existing(self, key: str) -> bool:
    portal = self._open.get(key)
    if portal is not None and portal.window.winfo_exists():
      portal.window.deiconify()
      portal.window.lift()
      portal.window.focus_force()
      return True
    return False

  def portal_closed(self, portal: Portal) -> None:
    for key, value in list(self._open.items()):
      if value is portal:
        del self._open[key]

  def open_customer(self) -> None:
    if not self._focus_existing("customer"):
      self._open["customer"] = CustomerPortalWindow(self)

  def open_employee(self) -> None:
    techs = self.service.list_login_technicians()
    if not techs:
      messagebox.showinfo("Technician portal",
                          "No technician accounts exist yet. Ask the owner to add one.",
                          parent=self.root)
      return
    dlg = FormDialog(
        self.root, "Technician sign-in",
        [dict(label="Who are you?", key="tech", kind="choice",
              options=[(f"{t.name}  -  {t.specialization}", t.user_id) for t in techs]),
         dict(label="Password", key="password", kind="password")],
        "Sign in", lambda v: self.service.authenticate_technician(v["tech"], v["password"]))
    tech = dlg.run()
    if tech is None:
      return
    key = f"employee:{tech.user_id}"
    if not self._focus_existing(key):
      self._open[key] = EmployeePortalWindow(self, tech)

  def open_owner(self) -> None:
    if self._focus_existing("owner"):
      return
    dlg = FormDialog(
        self.root, "Owner sign-in", [dict(label="Owner password", key="password", kind="password")],
        "Sign in", lambda v: self.service.authenticate_owner(v["password"]))
    owner = dlg.run()
    if owner is not None:
      self._open["owner"] = OwnerPortalWindow(self, owner)

  def quit(self) -> None:
    self.service.close()
    self.root.destroy()


def run() -> None:
  setup_logging()
  enable_dpi_awareness()
  service = RepairService(DB_PATH)
  root = tk.Tk()
  app = RoleSelectorApp(root, service)
  center_on(root)
  root.after(150, app.startup)
  root.mainloop()


if __name__ == "__main__":
  run()