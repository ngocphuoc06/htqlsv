import tkinter as tk
import re
from datetime import datetime
from decimal import Decimal
from tkinter import ttk, messagebox, simpledialog, filedialog
import csv
from .database import Database
from .scheduling import parse_schedule, parse_multi_schedule, format_schedule_list
from . import services

original_showerror = messagebox.showerror
def custom_showerror(title, message, **kwargs):
    msg = str(message)
    # Friendly MySQL error translations
    if "1062" in msg and "Duplicate entry" in msg:
        msg = "Dữ liệu này đã tồn tại (trùng mã). Vui lòng kiểm tra lại."
    elif "1451" in msg and "a foreign key constraint fails" in msg:
        msg = "Không thể xóa dữ liệu này vì đang có dữ liệu khác liên kết với nó."
    elif "1452" in msg and "a foreign key constraint fails" in msg:
        msg = "Dữ liệu tham chiếu không tồn tại."
    elif "2003" in msg and "Can't connect" in msg:
        msg = "Không thể kết nối đến cơ sở dữ liệu. Vui lòng kiểm tra MySQL server."
    elif "Access denied" in msg:
        msg = "Sai tên đăng nhập hoặc mật khẩu MySQL. Vui lòng kiểm tra cấu hình kết nối."
    else:
        # Fallback for other unrecognized errors
        if any(keyword in msg.lower() for keyword in ["error", "exception", "failed"]):
            msg = f"Lỗi hệ thống: {msg}"
            
    # Standardise titles to Vietnamese
    if title in ("Error", "Database Error", "Lỗi kết nối", "Không thể lưu điểm") or title.startswith("Error"):
        title = "Lỗi"
    elif title == "Success":
        title = "Thành công"
    original_showerror(title, msg, **kwargs)

messagebox.showerror = custom_showerror

original_showinfo = messagebox.showinfo
def custom_showinfo(title, message, **kwargs):
    if title in ("Success", "Saved", "Info") or title.startswith("Success"):
        title = "Thành công" if title in ("Success", "Saved") else "Thông báo"
    elif title == "Info":
        title = "Thông báo"
    original_showinfo(title, message, **kwargs)

messagebox.showinfo = custom_showinfo

def check_empty_treeview(tree, message="Chưa có dữ liệu"):
    if not tree.get_children():
        values = [message] + [""] * (len(tree["columns"]) - 1)
        tree.insert("", "end", values=values, tags=("oddrow",))

# Hạn hủy đăng ký (ngày)
UNENROLL_DEADLINE_DAYS = 7

# Đơn giá học phí mỗi tín chỉ (VNĐ) — mặc định khi tạo lớp HP
TUITION_PER_CREDIT = 500_000

# ── UI THEME CONSTANTS ──────────────────────────────────────────────────────
COLOR_BG       = "#F5F7FA"
COLOR_PRIMARY  = "#0F6E71"
COLOR_DANGER   = "#E5484D"
COLOR_WARNING  = "#F5A623"
COLOR_SUCCESS  = "#28A745"
COLOR_TEXT     = "#1A1A2E"
COLOR_TOPBAR   = "#0B5B5D"
COLOR_ROW_EVEN = "#EDF2F7"
COLOR_ROW_ODD  = "#FFFFFF"

FONT_TITLE  = ("Segoe UI", 18, "bold")
FONT_BODY   = ("Segoe UI", 11)
FONT_BODY_BOLD = ("Segoe UI", 11, "bold")
FONT_LABEL  = ("Segoe UI", 11)
FONT_ENTRY  = ("Segoe UI", 11)
FONT_BTN    = ("Segoe UI", 11, "bold")
FONT_BTN_LG = ("Segoe UI", 13, "bold")
FONT_TOPBAR = ("Segoe UI", 12, "bold")

FONT_CARD_TITLE = ("Segoe UI", 11)
FONT_CARD_VALUE = ("Segoe UI", 28, "bold")
COLOR_CARD_BG   = "#FFFFFF"
COLOR_CARD_BD   = "#D0D7DE"
# ─────────────────────────────────────────────────────────────────────────────

db = None  # Initialized once by LoginWindow


def _sem_display(sem):
    """Build a display string for a semester record or business query row.

    Format: 'HK1 (2025-2026)'
    Never returns a transaction ID, enrollment ID, or class section ID as semester name.
    """
    if not sem or not isinstance(sem, dict):
        return ""

    name = sem.get('semester_name') or sem.get('name')
    if not name and 'semester_id' in sem and not any(k in sem for k in ('amount', 'midterm', 'final_score')):
        name = sem.get('semester_id')

    year = sem.get('year_name') or sem.get('academic_year_name') or sem.get('academic_year')

    if name and year:
        return f"{name} ({year})"
    elif name:
        return str(name)
    elif year:
        return str(year)
    else:
        return "N/A"


def _sem_cb_value(sem):
    """Build the combobox value string for a semester."""
    return f"{sem['id']} - {_sem_display(sem)}"


# ── TTK STYLE SETUP ─────────────────────────────────────────────────────────
def setup_styles():
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("Treeview", background=COLOR_ROW_ODD, foreground=COLOR_TEXT,
                     rowheight=32, fieldbackground=COLOR_ROW_ODD, font=FONT_BODY)
    style.configure("Treeview.Heading", background=COLOR_PRIMARY, foreground="white",
                     font=("Segoe UI", 11, "bold"), relief="flat")
    style.map("Treeview.Heading", background=[("active", COLOR_TOPBAR)])
    style.configure("TNotebook", background=COLOR_BG, borderwidth=0)
    style.configure("TNotebook.Tab", background="#DDE3EA", foreground=COLOR_TEXT,
                     font=FONT_BODY, padding=[14, 6])
    style.map("TNotebook.Tab", background=[("selected", COLOR_PRIMARY)],
              foreground=[("selected", "white")])
    style.configure("TCombobox", font=FONT_BODY)
    style.map("TCombobox", fieldbackground=[("readonly", "white")],
              selectbackground=[("readonly", "white")],
              selectforeground=[("readonly", COLOR_TEXT)])


def _configure_treeview_tags(tree):
    tree.tag_configure("evenrow", background=COLOR_ROW_EVEN)
    tree.tag_configure("oddrow", background=COLOR_ROW_ODD)


def _make_card(parent, title, value, col, accent=COLOR_PRIMARY):
    # Outer frame creates a left accent border
    outer = tk.Frame(parent, bg=accent)
    outer.grid(row=0, column=col, padx=14, pady=14, sticky="nsew")
    card = tk.Frame(outer, bg=COLOR_CARD_BG, padx=24, pady=18,
                    highlightbackground=COLOR_CARD_BD, highlightthickness=1)
    card.pack(fill="both", expand=True, padx=(3, 0))
    tk.Label(card, text=title, font=FONT_CARD_TITLE, bg=COLOR_CARD_BG,
             fg="#6B7280").pack(anchor="w")
    tk.Label(card, text=str(value), font=FONT_CARD_VALUE, bg=COLOR_CARD_BG,
             fg=accent).pack(anchor="w", pady=(8, 0))
    return card


def _make_page_header(parent, title, icon=""):
    """Create a consistent page header bar with accent stripe."""
    header = tk.Frame(parent, bg="white")
    header.pack(fill="x")
    accent_bar = tk.Frame(header, bg=COLOR_PRIMARY, width=4)
    accent_bar.pack(side="left", fill="y")
    tk.Label(header, text=f"  {icon}  {title}", font=("Segoe UI", 16, "bold"),
             bg="white", fg=COLOR_TEXT, anchor="w").pack(side="left", padx=10, pady=14)
    tk.Frame(parent, bg="#E2E8F0", height=1).pack(fill="x")
    return header


def _make_btn(parent, text, command, bg=COLOR_PRIMARY, width=15, font=FONT_BTN):
    return tk.Button(parent, text=text, bg=bg, fg="white", font=font,
                     width=width, relief="flat", cursor="hand2",
                     activebackground=COLOR_TOPBAR, activeforeground="white",
                     command=command)


def _get_schedule_display(db_inst, section_id):
    """Build human-readable schedule string from section_schedules table."""
    rows = db_inst.get_section_schedules(section_id)
    if not rows:
        return "—"
    sessions = [(r['weekday'], r['start_minutes'], r['end_minutes']) for r in rows]
    return format_schedule_list(sessions)


# ═══════════════════════════════════════════════════════════════════════════
# LOGIN WINDOW
# ═══════════════════════════════════════════════════════════════════════════

def _close_session_window(root):
    from .session import session
    session.logout()
    root.destroy()


class LoginWindow:
    def __init__(self):
        global db
        from .session import session
        session.logout()
        self.root = tk.Tk()
        self.root.protocol("WM_DELETE_WINDOW", lambda: _close_session_window(self.root))
        if db is None:
            self.root.withdraw()
            try:
                db = Database()
            except Exception as exc:
                # Show the real config/port error so the user can act on it
                msg = str(exc)
                messagebox.showerror("Lỗi kết nối", msg, parent=self.root)
                self.root.destroy()
                return
            self.root.deiconify()

        # ── Check migration readiness ──
        if not db.is_ready:
            messagebox.showerror(
                "Migration chưa hoàn tất",
                "Cơ sở dữ liệu chưa được nâng cấp xong.\n"
                "Vui lòng chạy migration trước khi sử dụng ứng dụng.\n\n"
                "cd \"Student Management System\"\n"
                "python -m gui.migration --apply",
                parent=self.root)
            self.root.destroy()
            return

        self.root.title("Hệ thống Quản lý Sinh viên")
        self.root.geometry("950x550")
        self.root.configure(bg="white")
        self.root.resizable(True, True)

        setup_styles()

        left_panel = tk.Frame(self.root, bg=COLOR_PRIMARY, width=400)
        left_panel.pack(side="left", fill="y")
        left_panel.pack_propagate(False)

        left_spacer = tk.Frame(left_panel, bg=COLOR_PRIMARY)
        left_spacer.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(left_spacer, text="🎓", font=("Segoe UI", 52),
                 bg=COLOR_PRIMARY, fg="white").pack(pady=(0, 10))
        tk.Label(left_spacer, text="HỆ THỐNG\nQUẢN LÝ SINH VIÊN",
                 font=("Segoe UI", 22, "bold"), bg=COLOR_PRIMARY, fg="white",
                 justify="center", wraplength=320).pack(pady=(0, 12))

        right_panel = tk.Frame(self.root, bg="white")
        right_panel.pack(side="right", fill="both", expand=True)

        form_container = tk.Frame(right_panel, bg="white")
        form_container.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(form_container, text="ĐĂNG NHẬP",
                 font=("Segoe UI", 20, "bold"), bg="white",
                 fg=COLOR_PRIMARY).pack(pady=(0, 6))
        tk.Label(form_container, text="Vui lòng đăng nhập để tiếp tục",
                 font=("Segoe UI", 10), bg="white", fg="#888888").pack(pady=(0, 20))

        self.mode = tk.StringVar(value="login")
        self.form_frame = tk.LabelFrame(form_container, text="Đăng nhập", bg="white",
                                         fg=COLOR_PRIMARY, font=FONT_BODY,
                                         padx=20, pady=15)
        self.form_frame.pack(pady=(0, 20), padx=30)

        btn_frame = tk.Frame(form_container, bg="white")
        btn_frame.pack(pady=(0, 10))
        self.main_btn = tk.Button(btn_frame, text="ĐĂNG NHẬP", width=30, height=2,
                                bg=COLOR_PRIMARY, fg="white", font=FONT_BTN_LG,
                                activebackground=COLOR_TOPBAR, activeforeground="white",
                                relief="flat", cursor="hand2",
                                command=self.handle_action)
        self.main_btn.pack()

        self.show_login_form()
        self.mode.trace("w", lambda *_: self.toggle_mode())
        self.root.mainloop()

    def show_login_form(self):
        for w in self.form_frame.winfo_children(): w.destroy()
        tk.Label(self.form_frame, text="Vai trò:", bg="white", font=FONT_LABEL).grid(row=0, column=0, sticky="w", pady=12)
        self.role_var = tk.StringVar(value="Sinh viên")
        ttk.Combobox(self.form_frame, textvariable=self.role_var,
                    values=["Sinh viên", "Giảng viên", "Quản trị viên"], state="readonly", width=30).grid(row=0, column=1, pady=12, padx=12)
        tk.Label(self.form_frame, text="Tên đăng nhập:", bg="white", font=FONT_LABEL).grid(row=1, column=0, sticky="w", pady=12)
        self.user_entry = tk.Entry(self.form_frame, width=32, font=FONT_ENTRY); self.user_entry.grid(row=1, column=1, pady=12, padx=12)
        tk.Label(self.form_frame, text="Mật khẩu:", bg="white", font=FONT_LABEL).grid(row=2, column=0, sticky="w", pady=12)
        self.pass_entry = tk.Entry(self.form_frame, width=32, font=FONT_ENTRY, show="*"); self.pass_entry.grid(row=2, column=1, pady=12, padx=12)
        self.main_btn.config(text="ĐĂNG NHẬP")

    def show_register_form(self):
        for w in self.form_frame.winfo_children(): w.destroy()
        entries = ["Họ và tên:", "Email:", "Tên đăng nhập:", "Mật khẩu:", "Xác nhận mật khẩu:", "Số điện thoại:", "Địa chỉ:"]
        self.reg_entries = []
        for i, text in enumerate(entries):
            tk.Label(self.form_frame, text=text, bg="white", font=FONT_LABEL).grid(row=i, column=0, sticky="w", pady=6)
            e = tk.Entry(self.form_frame, width=32, font=FONT_ENTRY, show="*" if "Mật khẩu" in text else "")
            e.grid(row=i, column=1, pady=6, padx=12)
            self.reg_entries.append(e)
        self.main_btn.config(text="Đăng ký")

    def toggle_mode(self):
        if self.mode.get() == "login": self.show_login_form()

    def handle_action(self):
        if self.mode.get() == "login": self.login()

    def login(self):
        role_disp = self.role_var.get()
        role_map = {"Sinh viên": "Student", "Giảng viên": "Lecturer", "Quản trị viên": "Admin"}
        role = role_map.get(role_disp, role_disp)
        username = self.user_entry.get().strip()
        password = self.pass_entry.get()
        if not username or not password:
            messagebox.showerror("Lỗi", "Vui lòng nhập đầy đủ thông tin"); return
        try:
            from .session import session
            ok = session.login(db, username, password, role)
        except Exception as e:
            messagebox.showerror("Lỗi cơ sở dữ liệu", f"Không thể kết nối cơ sở dữ liệu. Vui lòng kiểm tra lại cấu hình kết nối."); return
        if ok:
            self.root.destroy()
            if role == "Admin":
                AdminDashboard(username)
            elif role == "Lecturer":
                LecturerDashboard(username)
            else:
                StudentDashboard(username)
        else:
            messagebox.showerror("Đăng nhập thất bại", "Tên đăng nhập hoặc mật khẩu không chính xác")


# ═══════════════════════════════════════════════════════════════════════════
# ADMIN DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════

class AdminDashboard:
    def __init__(self, username):
        self.username = username
        self.root = tk.Tk()
        self.root.protocol("WM_DELETE_WINDOW", lambda: _close_session_window(self.root))
        self.root.title(f"Quản trị viên - {username}")
        self.root.geometry("1200x750")
        self.root.minsize(1024, 600)
        self.root.resizable(True, True)
        self.root.configure(bg=COLOR_BG)

        sidebar = tk.Frame(self.root, bg=COLOR_TOPBAR, width=245)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(sidebar, text="👤 Admin", font=("Segoe UI", 10),
                 bg=COLOR_TOPBAR, fg="#B2DFDB").pack(pady=(18, 2))
        tk.Label(sidebar, text=username, font=("Segoe UI", 13, "bold"),
                 bg=COLOR_TOPBAR, fg="white").pack(pady=(0, 18))
        tk.Frame(sidebar, bg="#1A8A8D", height=1).pack(fill="x", padx=15, pady=(0, 10))

        # Sidebar menu with category grouping
        menu_structure = [
            (None, [("📊  Tổng quan", 0)]),
            ("DANH MỤC", [
                ("🏛️  Khoa / Ngành", 1),
                ("📅  Năm học & Học kỳ", 2),
                ("🏫  Khóa TS & Lớp HC", 3),
                ("📖  Môn học", 4),
            ]),
            ("ĐÀO TẠO", [
                ("📚  Lớp học phần", 5),
            ]),
            ("NHÂN SỰ", [
                ("👨‍🏫  Tài khoản GV", 6),
                ("🎓  Quản lý Sinh viên", 7),
            ]),
        ]

        self.sidebar_buttons = []
        for category, items in menu_structure:
            if category:
                tk.Frame(sidebar, bg="#1A8A8D", height=1).pack(fill="x", padx=18, pady=(10, 0))
                tk.Label(sidebar, text=f"  {category}", font=("Segoe UI", 9),
                         bg=COLOR_TOPBAR, fg="#70B8BA", anchor="w",
                         padx=18).pack(fill="x", pady=(4, 2))
            for text, idx in items:
                btn = tk.Button(sidebar, text=text, font=("Segoe UI", 11),
                                bg=COLOR_TOPBAR, fg="white", relief="flat",
                                anchor="w", padx=18, pady=8, cursor="hand2",
                                activebackground=COLOR_PRIMARY, activeforeground="white",
                                command=lambda i=idx: self._show_page(i))
                btn.pack(fill="x")
                self.sidebar_buttons.append(btn)

        tk.Frame(sidebar, bg=COLOR_TOPBAR).pack(fill="both", expand=True)
        tk.Button(sidebar, text="🚪  Đăng xuất", font=FONT_BTN,
                  bg=COLOR_DANGER, fg="white", relief="flat", cursor="hand2", pady=10,
                  activebackground="#C13639", activeforeground="white",
                  command=self.logout).pack(fill="x", padx=12, pady=15)

        content = tk.Frame(self.root, bg=COLOR_BG)
        content.pack(side="right", fill="both", expand=True)
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)

        self.pages = []
        page_builders = [
            self.build_overview,
            self.build_dept_program,
            self.build_academic,
            self.build_batch_class,
            self.build_subjects,
            self.build_sections,
            self.build_create_lecturer,
            self.build_students,
        ]
        for builder in page_builders:
            page = tk.Frame(content, bg=COLOR_BG)
            page.grid(row=0, column=0, sticky="nsew")
            builder(page)
            self.pages.append(page)

        self._show_page(0)
        self.root.mainloop()

    def _show_page(self, index):
        self.pages[index].tkraise()
        for i, btn in enumerate(self.sidebar_buttons):
            if i == index:
                btn.config(bg=COLOR_PRIMARY, font=("Segoe UI", 11, "bold"))
            else:
                btn.config(bg=COLOR_TOPBAR, font=("Segoe UI", 11))

    def logout(self):
        if messagebox.askyesno("Đăng xuất", "Bạn có chắc muốn đăng xuất?"):
            from .session import session
            session.logout()
            self.root.destroy()
            LoginWindow()

    def build_overview(self, parent):
        self.overview_parent = parent
        _make_page_header(parent, "Tổng quan hệ thống", "📊")
        self.cards_frame = tk.Frame(parent, bg=COLOR_BG)
        self.cards_frame.pack(padx=30, pady=10)
        
        self.nb_stats = ttk.Notebook(parent)
        self.nb_stats.pack(fill="both", expand=True, padx=30, pady=20)
        
        self.tab_status = tk.Frame(self.nb_stats, bg=COLOR_BG)
        self.nb_stats.add(self.tab_status, text="Theo trạng thái")
        self.tab_dept = tk.Frame(self.nb_stats, bg=COLOR_BG)
        self.nb_stats.add(self.tab_dept, text="Theo khoa")
        self.tab_prog = tk.Frame(self.nb_stats, bg=COLOR_BG)
        self.nb_stats.add(self.tab_prog, text="Theo ngành")
        self.tab_batch = tk.Frame(self.nb_stats, bg=COLOR_BG)
        self.nb_stats.add(self.tab_batch, text="Theo khóa TS")
        self.tab_class = tk.Frame(self.nb_stats, bg=COLOR_BG)
        self.nb_stats.add(self.tab_class, text="Theo lớp HC")
        
        def create_tree(tab, columns):
            tree = ttk.Treeview(tab, columns=columns, show="headings")
            for c in columns:
                tree.heading(c, text=c)
                tree.column(c, width=200)
            scrollbar = ttk.Scrollbar(tab, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side="right", fill="y")
            tree.pack(fill="both", expand=True)
            _configure_treeview_tags(tree)
            return tree
            
        self.tree_status = create_tree(self.tab_status, ("Trạng thái", "Số lượng"))
        self.tree_dept = create_tree(self.tab_dept, ("Tên Khoa", "Số lượng"))
        self.tree_prog = create_tree(self.tab_prog, ("Tên Ngành", "Số lượng"))
        self.tree_batch = create_tree(self.tab_batch, ("Tên Khóa", "Số lượng"))
        self.tree_class = create_tree(self.tab_class, ("Tên Lớp", "Số lượng"))
        
        self.refresh_overview()
        
    def refresh_overview(self):
        for w in self.cards_frame.winfo_children(): w.destroy()
        for c in range(4): self.cards_frame.grid_columnconfigure(c, weight=1)
        
        total_subjects = len(db.list_subjects())
        total_lecturers = db.count_lecturers()
        total_enrollments = db.count_all_enrollments()
        stats = db.get_student_statistics()
        
        _make_card(self.cards_frame, "Tổng số môn học", total_subjects, 0, accent="#3B82F6")
        _make_card(self.cards_frame, "Tổng số sinh viên", stats['total_students'], 1, accent=COLOR_PRIMARY)
        _make_card(self.cards_frame, "Tổng số giảng viên", total_lecturers, 2, accent="#8B5CF6")
        _make_card(self.cards_frame, "Tổng lượt đăng ký", total_enrollments, 3, accent="#F59E0B")
        
        def populate_tree(tree, data):
            for t in tree.get_children(): tree.delete(t)
            for i, row in enumerate(data):
                tag = "evenrow" if i % 2 == 0 else "oddrow"
                keys = list(row.keys())
                tree.insert("", "end", values=(row[keys[0]], row['cnt']), tags=(tag,))
                
        populate_tree(self.tree_status, stats['by_status'])
        populate_tree(self.tree_dept, stats['by_department'])
        populate_tree(self.tree_prog, stats['by_program'])
        populate_tree(self.tree_batch, stats['by_batch'])
        populate_tree(self.tree_class, stats['by_admin_class'])

    # ── DEPARTMENT / PROGRAM ─────────────────────────────────────────────
    def build_dept_program(self, parent):
        _make_page_header(parent, "Quản lý Khoa / Ngành", "🏛️")

        # Department section
        dept_frame = tk.LabelFrame(parent, text="Thêm Khoa", bg=COLOR_BG,
                                    fg=COLOR_PRIMARY, font=FONT_BODY, padx=15, pady=10)
        dept_frame.pack(fill="x", padx=30, pady=5)
        tk.Label(dept_frame, text="Mã khoa:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.dept_id_entry = tk.Entry(dept_frame, width=15, font=FONT_ENTRY)
        self.dept_id_entry.grid(row=0, column=1, padx=5, pady=5)
        tk.Label(dept_frame, text="Tên khoa:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.dept_name_entry = tk.Entry(dept_frame, width=30, font=FONT_ENTRY)
        self.dept_name_entry.grid(row=0, column=3, padx=5, pady=5)
        _make_btn(dept_frame, "Thêm Khoa", self.add_department, width=12).grid(row=0, column=4, padx=5, pady=5)
        _make_btn(dept_frame, "Sửa Khoa", self.edit_department, bg=COLOR_WARNING, width=10).grid(row=0, column=5, padx=5, pady=5)

        # Program section
        prog_frame = tk.LabelFrame(parent, text="Thêm Ngành", bg=COLOR_BG,
                                    fg=COLOR_PRIMARY, font=FONT_BODY, padx=15, pady=10)
        prog_frame.pack(fill="x", padx=30, pady=5)
        tk.Label(prog_frame, text="Mã ngành:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.prog_id_entry = tk.Entry(prog_frame, width=15, font=FONT_ENTRY)
        self.prog_id_entry.grid(row=0, column=1, padx=5, pady=5)
        tk.Label(prog_frame, text="Tên ngành:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.prog_name_entry = tk.Entry(prog_frame, width=25, font=FONT_ENTRY)
        self.prog_name_entry.grid(row=0, column=3, padx=5, pady=5)
        tk.Label(prog_frame, text="Khoa:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=4, padx=5, pady=5, sticky="w")
        self.prog_dept_var = tk.StringVar()
        self.prog_dept_cb = ttk.Combobox(prog_frame, textvariable=self.prog_dept_var, state="readonly", width=15)
        self.prog_dept_cb.grid(row=0, column=5, padx=5, pady=5)
        _make_btn(prog_frame, "Thêm Ngành", self.add_program, width=12).grid(row=0, column=6, padx=5, pady=5)
        _make_btn(prog_frame, "Sửa Ngành", self.edit_program, bg=COLOR_WARNING, width=10).grid(row=0, column=7, padx=5, pady=5)

        # Tables
        cols_d = ("Mã khoa", "Tên khoa")
        dept_frame = tk.Frame(parent)
        dept_frame.pack(fill="x", padx=30, pady=5)
        self.dept_tree = ttk.Treeview(dept_frame, columns=cols_d, show="headings", height=5)
        dept_scroll = ttk.Scrollbar(dept_frame, orient="vertical", command=self.dept_tree.yview)
        self.dept_tree.configure(yscrollcommand=dept_scroll.set)
        self.dept_tree.pack(side="left", fill="x", expand=True)
        dept_scroll.pack(side="right", fill="y")
        for c in cols_d: self.dept_tree.heading(c, text=c); self.dept_tree.column(c, width=200)
        _configure_treeview_tags(self.dept_tree)

        cols_p = ("Mã ngành", "Tên ngành", "Khoa")
        prog_frame = tk.Frame(parent)
        prog_frame.pack(fill="both", expand=True, padx=30, pady=5)
        self.prog_tree = ttk.Treeview(prog_frame, columns=cols_p, show="headings", height=5)
        prog_scroll = ttk.Scrollbar(prog_frame, orient="vertical", command=self.prog_tree.yview)
        self.prog_tree.configure(yscrollcommand=prog_scroll.set)
        self.prog_tree.pack(side="left", fill="both", expand=True)
        prog_scroll.pack(side="right", fill="y")
        for c in cols_p: self.prog_tree.heading(c, text=c); self.prog_tree.column(c, width=200)
        _configure_treeview_tags(self.prog_tree)

        self.refresh_dept_prog()

    def refresh_dept_prog(self):
        for t in self.dept_tree.get_children(): self.dept_tree.delete(t)
        depts = db.list_departments()
        for i, d in enumerate(depts):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            self.dept_tree.insert("", "end", values=(d['id'], d['name']), tags=(tag,))
        self.prog_dept_cb['values'] = [f"{d['id']} - {d['name']}" for d in depts]

        for t in self.prog_tree.get_children(): self.prog_tree.delete(t)
        progs = db.list_programs()
        for i, p in enumerate(progs):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            self.prog_tree.insert("", "end", values=(p['id'], p['name'], p.get('dept_name', '')), tags=(tag,))

    def add_department(self):
        did = self.dept_id_entry.get().strip().upper()
        name = self.dept_name_entry.get().strip()
        if not did or not name:
            messagebox.showerror("Error", "Điền đầy đủ mã và tên khoa"); return
        try:
            db.add_department(did, name)
            messagebox.showinfo("Success", f"Đã thêm khoa {did}")
            self.dept_id_entry.delete(0, "end")
            self.dept_name_entry.delete(0, "end")
            self.refresh_dept_prog()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def edit_department(self):
        item = self.dept_tree.selection()
        if not item:
            messagebox.showerror("Error", "Chọn một khoa để sửa"); return
        did = str(self.dept_tree.item(item[0])['values'][0])
        old_name = str(self.dept_tree.item(item[0])['values'][1])
        new_name = simpledialog.askstring("Sửa Khoa", f"Tên mới cho khoa {did}:", initialvalue=old_name)
        if not new_name or not new_name.strip():
            return
        try:
            db.update_department(did, name=new_name.strip())
            messagebox.showinfo("Success", "Đã cập nhật")
            self.refresh_dept_prog()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def add_program(self):
        pid = self.prog_id_entry.get().strip().upper()
        name = self.prog_name_entry.get().strip()
        dept_sel = self.prog_dept_var.get()
        if not pid or not name or not dept_sel:
            messagebox.showerror("Error", "Điền đầy đủ thông tin ngành"); return
        dept_id = dept_sel.split(" - ")[0]
        try:
            db.add_program(pid, name, dept_id)
            messagebox.showinfo("Success", f"Đã thêm ngành {pid}")
            self.prog_id_entry.delete(0, "end")
            self.prog_name_entry.delete(0, "end")
            self.refresh_dept_prog()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def refresh_all_admin_comboboxes(self):
        """Refresh all catalog trees and dependent comboboxes across Admin Dashboard."""
        self.refresh_dept_prog()
        self.refresh_academic()
        self.refresh_batch_class()
        self.refresh_subjects()
        self.refresh_courses()
        self.refresh_students()

    def edit_program(self):
        item = self.prog_tree.selection()
        if not item:
            messagebox.showerror("Error", "Chọn một ngành để sửa"); return
        pid = str(self.prog_tree.item(item[0])['values'][0])
        prog = db.get_program(pid)
        if not prog:
            messagebox.showerror("Error", f"Ngành {pid} không tồn tại"); return

        top = tk.Toplevel(self.root)
        top.title(f"Sửa Ngành - {pid}")
        top.geometry("400x250")
        top.grab_set()

        tk.Label(top, text=f"Mã ngành: {pid}", font=FONT_BODY_BOLD).pack(pady=(15, 10))

        f_name = tk.Frame(top)
        f_name.pack(fill="x", padx=20, pady=5)
        tk.Label(f_name, text="Tên ngành:", width=12, anchor="w", font=FONT_LABEL).pack(side="left")
        entry_name = tk.Entry(f_name, width=28, font=FONT_ENTRY)
        entry_name.insert(0, prog['name'])
        entry_name.pack(side="left")

        f_dept = tk.Frame(top)
        f_dept.pack(fill="x", padx=20, pady=5)
        tk.Label(f_dept, text="Khoa:", width=12, anchor="w", font=FONT_LABEL).pack(side="left")
        depts = db.list_departments()
        dept_vals = [f"{d['id']} - {d['name']}" for d in depts]
        var_dept = tk.StringVar()
        cb_dept = ttk.Combobox(f_dept, textvariable=var_dept, values=dept_vals, state="readonly", width=26)
        curr_dept_val = next((v for v in dept_vals if v.startswith(str(prog['department_id']) + " -")), dept_vals[0] if dept_vals else "")
        var_dept.set(curr_dept_val)
        cb_dept.pack(side="left")

        def save():
            name = entry_name.get().strip()
            dept_sel = var_dept.get()
            if not name or not dept_sel:
                messagebox.showerror("Error", "Vui lòng nhập đầy đủ thông tin", parent=top)
                return
            dept_id = dept_sel.split(" - ")[0]
            try:
                db.update_program(pid, name=name, department_id=dept_id)
                messagebox.showinfo("Success", "Đã cập nhật ngành", parent=top)
                top.destroy()
                self.refresh_all_admin_comboboxes()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=top)

        _make_btn(top, "Lưu thay đổi", save, bg=COLOR_PRIMARY, width=15).pack(pady=20)

    # ── ACADEMIC YEAR & SEMESTER ─────────────────────────────────────────
    def build_academic(self, parent):
        _make_page_header(parent, "Năm học & Học kỳ", "📅")

        ay_frame = tk.LabelFrame(parent, text="Thêm Năm học", bg=COLOR_BG,
                                  fg=COLOR_PRIMARY, font=FONT_BODY, padx=15, pady=10)
        ay_frame.pack(fill="x", padx=30, pady=5)
        tk.Label(ay_frame, text="Mã:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=0, padx=5)
        self.ay_id = tk.Entry(ay_frame, width=12, font=FONT_ENTRY); self.ay_id.grid(row=0, column=1, padx=5)
        tk.Label(ay_frame, text="Tên:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=2, padx=5)
        self.ay_name = tk.Entry(ay_frame, width=20, font=FONT_ENTRY); self.ay_name.grid(row=0, column=3, padx=5)
        tk.Label(ay_frame, text="Năm BĐ:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=4, padx=5)
        self.ay_start = tk.Entry(ay_frame, width=6, font=FONT_ENTRY); self.ay_start.grid(row=0, column=5, padx=5)
        tk.Label(ay_frame, text="Năm KT:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=6, padx=5)
        self.ay_end = tk.Entry(ay_frame, width=6, font=FONT_ENTRY); self.ay_end.grid(row=0, column=7, padx=5)
        _make_btn(ay_frame, "Thêm", self.add_academic_year, width=8).grid(row=0, column=8, padx=5)
        _make_btn(ay_frame, "Sửa", self.edit_academic_year, bg=COLOR_WARNING, width=6).grid(row=0, column=9, padx=5)

        sem_frame = tk.LabelFrame(parent, text="Thêm Học kỳ", bg=COLOR_BG,
                                   fg=COLOR_PRIMARY, font=FONT_BODY, padx=15, pady=10)
        sem_frame.pack(fill="x", padx=30, pady=5)
        tk.Label(sem_frame, text="Mã HK:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=0, padx=5)
        self.sem_id = tk.Entry(sem_frame, width=12, font=FONT_ENTRY); self.sem_id.grid(row=0, column=1, padx=5)
        tk.Label(sem_frame, text="Tên HK:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=2, padx=5)
        self.sem_name = tk.Entry(sem_frame, width=15, font=FONT_ENTRY); self.sem_name.grid(row=0, column=3, padx=5)
        tk.Label(sem_frame, text="Năm học:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=4, padx=5)
        self.sem_ay_var = tk.StringVar()
        self.sem_ay_cb = ttk.Combobox(sem_frame, textvariable=self.sem_ay_var, state="readonly", width=18)
        self.sem_ay_cb.grid(row=0, column=5, padx=5)
        self.sem_reg_var = tk.IntVar(value=0)
        tk.Checkbutton(sem_frame, text="Mở ĐK", variable=self.sem_reg_var, bg=COLOR_BG).grid(row=0, column=6, padx=5)
        _make_btn(sem_frame, "Thêm", self.add_semester, width=8).grid(row=0, column=7, padx=5)
        _make_btn(sem_frame, "Sửa học kỳ", self.edit_semester, bg=COLOR_WARNING, width=10).grid(row=0, column=8, padx=5)

        # Date editing row
        date_frame = tk.LabelFrame(parent, text="Sửa nhanh ngày học kỳ", bg=COLOR_BG,
                                    fg=COLOR_PRIMARY, font=FONT_BODY, padx=15, pady=10)
        date_frame.pack(fill="x", padx=30, pady=5)
        tk.Label(date_frame, text="Ngày BĐ (YYYY-MM-DD):", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=0, padx=5)
        self.sem_start_date = tk.Entry(date_frame, width=12, font=FONT_ENTRY)
        self.sem_start_date.grid(row=0, column=1, padx=5)
        tk.Label(date_frame, text="Ngày KT:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=2, padx=5)
        self.sem_end_date = tk.Entry(date_frame, width=12, font=FONT_ENTRY)
        self.sem_end_date.grid(row=0, column=3, padx=5)
        _make_btn(date_frame, "Cập nhật ngày", self.update_semester_dates, bg=COLOR_WARNING, width=14).grid(row=0, column=4, padx=10)

        btn_f = tk.Frame(parent, bg=COLOR_BG)
        btn_f.pack(pady=5)
        _make_btn(btn_f, "Mở/Đóng ĐK học kỳ", self.toggle_semester_reg, bg=COLOR_WARNING, width=20).pack()

        cols_ay = ("Mã", "Tên", "Năm BĐ", "Năm KT")
        ay_frame = tk.Frame(parent)
        ay_frame.pack(fill="x", padx=30, pady=5)
        self.ay_tree = ttk.Treeview(ay_frame, columns=cols_ay, show="headings", height=4)
        ay_scroll = ttk.Scrollbar(ay_frame, orient="vertical", command=self.ay_tree.yview)
        self.ay_tree.configure(yscrollcommand=ay_scroll.set)
        self.ay_tree.pack(side="left", fill="x", expand=True)
        ay_scroll.pack(side="right", fill="y")
        for c in cols_ay: self.ay_tree.heading(c, text=c); self.ay_tree.column(c, width=150)
        _configure_treeview_tags(self.ay_tree)

        cols_sem = ("Mã HK", "Tên HK", "Năm học", "Ngày BĐ", "Ngày KT", "Đăng ký")
        sem_frame = tk.Frame(parent)
        sem_frame.pack(fill="both", expand=True, padx=30, pady=5)
        self.sem_tree = ttk.Treeview(sem_frame, columns=cols_sem, show="headings", height=5)
        sem_scroll = ttk.Scrollbar(sem_frame, orient="vertical", command=self.sem_tree.yview)
        self.sem_tree.configure(yscrollcommand=sem_scroll.set)
        self.sem_tree.pack(side="left", fill="both", expand=True)
        sem_scroll.pack(side="right", fill="y")
        for c in cols_sem: self.sem_tree.heading(c, text=c); self.sem_tree.column(c, width=130)
        _configure_treeview_tags(self.sem_tree)

        self.refresh_academic()

    def refresh_academic(self):
        for t in self.ay_tree.get_children(): self.ay_tree.delete(t)
        years = db.list_academic_years()
        for i, y in enumerate(years):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            self.ay_tree.insert("", "end", values=(y['id'], y['name'], y.get('start_year', ''), y.get('end_year', '')), tags=(tag,))
        self.sem_ay_cb['values'] = [f"{y['id']} - {y['name']}" for y in years]

        for t in self.sem_tree.get_children(): self.sem_tree.delete(t)
        sems = db.list_semesters()
        for i, s in enumerate(sems):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            reg = "✅ Mở" if s['registration_open'] else "❌ Đóng"
            sd = str(s.get('start_date', '')) if s.get('start_date') else '—'
            ed = str(s.get('end_date', '')) if s.get('end_date') else '—'
            self.sem_tree.insert("", "end", values=(
                s['id'], s['name'], s.get('year_name', ''), sd, ed, reg
            ), tags=(tag,))

    def add_academic_year(self):
        yid = self.ay_id.get().strip()
        name = self.ay_name.get().strip()
        if not yid or not name:
            messagebox.showerror("Error", "Điền mã và tên năm học"); return
        try:
            sy = int(self.ay_start.get()) if self.ay_start.get().strip() else None
            ey = int(self.ay_end.get()) if self.ay_end.get().strip() else None
        except ValueError:
            messagebox.showerror("Error", "Năm phải là số"); return
        try:
            db.add_academic_year(yid, name, sy, ey)
            messagebox.showinfo("Success", f"Đã thêm năm học {yid}")
            self.ay_id.delete(0, "end"); self.ay_name.delete(0, "end")
            self.ay_start.delete(0, "end"); self.ay_end.delete(0, "end")
            self.refresh_academic()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def edit_academic_year(self):
        item = self.ay_tree.selection()
        if not item:
            messagebox.showerror("Error", "Chọn một năm học để sửa"); return
        yid = str(self.ay_tree.item(item[0])['values'][0])
        ay = db.get_academic_year(yid)
        if not ay:
            messagebox.showerror("Error", f"Năm học {yid} không tồn tại"); return

        top = tk.Toplevel(self.root)
        top.title(f"Sửa Năm học - {yid}")
        top.geometry("400x280")
        top.grab_set()

        tk.Label(top, text=f"Mã năm học: {yid}", font=FONT_BODY_BOLD).pack(pady=(15, 10))

        f_name = tk.Frame(top)
        f_name.pack(fill="x", padx=20, pady=5)
        tk.Label(f_name, text="Tên năm học:", width=14, anchor="w", font=FONT_LABEL).pack(side="left")
        entry_name = tk.Entry(f_name, width=25, font=FONT_ENTRY)
        entry_name.insert(0, ay['name'])
        entry_name.pack(side="left")

        f_sy = tk.Frame(top)
        f_sy.pack(fill="x", padx=20, pady=5)
        tk.Label(f_sy, text="Năm bắt đầu:", width=14, anchor="w", font=FONT_LABEL).pack(side="left")
        entry_sy = tk.Entry(f_sy, width=25, font=FONT_ENTRY)
        if ay.get('start_year') is not None:
            entry_sy.insert(0, str(ay['start_year']))
        entry_sy.pack(side="left")

        f_ey = tk.Frame(top)
        f_ey.pack(fill="x", padx=20, pady=5)
        tk.Label(f_ey, text="Năm kết thúc:", width=14, anchor="w", font=FONT_LABEL).pack(side="left")
        entry_ey = tk.Entry(f_ey, width=25, font=FONT_ENTRY)
        if ay.get('end_year') is not None:
            entry_ey.insert(0, str(ay['end_year']))
        entry_ey.pack(side="left")

        def save():
            name = entry_name.get().strip()
            sy_s = entry_sy.get().strip()
            ey_s = entry_ey.get().strip()
            if not name:
                messagebox.showerror("Error", "Tên năm học không được để trống", parent=top)
                return
            try:
                sy = int(sy_s) if sy_s else None
                ey = int(ey_s) if ey_s else None
            except ValueError:
                messagebox.showerror("Error", "Năm phải là số nguyên", parent=top)
                return
            try:
                db.update_academic_year(yid, name=name, start_year=sy, end_year=ey)
                messagebox.showinfo("Success", "Đã cập nhật năm học", parent=top)
                top.destroy()
                self.refresh_all_admin_comboboxes()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=top)

        _make_btn(top, "Lưu thay đổi", save, bg=COLOR_PRIMARY, width=15).pack(pady=15)

    def add_semester(self):
        sid = self.sem_id.get().strip()
        name = self.sem_name.get().strip()
        ay_sel = self.sem_ay_var.get()
        if not sid or not name or not ay_sel:
            messagebox.showerror("Error", "Điền đầy đủ thông tin học kỳ"); return
        ay_id = ay_sel.split(" - ")[0]
        try:
            db.add_semester(sid, name, ay_id, registration_open=self.sem_reg_var.get())
            messagebox.showinfo("Success", f"Đã thêm học kỳ {sid}")
            self.sem_id.delete(0, "end"); self.sem_name.delete(0, "end")
            self.refresh_academic()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def edit_semester(self):
        item = self.sem_tree.selection()
        if not item:
            messagebox.showerror("Error", "Chọn một học kỳ để sửa"); return
        sid = str(self.sem_tree.item(item[0])['values'][0])
        sem = db.get_semester(sid)
        if not sem:
            messagebox.showerror("Error", f"Học kỳ {sid} không tồn tại"); return

        top = tk.Toplevel(self.root)
        top.title(f"Sửa Học kỳ - {sid}")
        top.geometry("450x360")
        top.grab_set()

        tk.Label(top, text=f"Mã học kỳ: {sid}", font=FONT_BODY_BOLD).pack(pady=(15, 10))

        f_name = tk.Frame(top)
        f_name.pack(fill="x", padx=20, pady=5)
        tk.Label(f_name, text="Tên học kỳ:", width=14, anchor="w", font=FONT_LABEL).pack(side="left")
        entry_name = tk.Entry(f_name, width=28, font=FONT_ENTRY)
        entry_name.insert(0, sem['name'])
        entry_name.pack(side="left")

        f_ay = tk.Frame(top)
        f_ay.pack(fill="x", padx=20, pady=5)
        tk.Label(f_ay, text="Năm học:", width=14, anchor="w", font=FONT_LABEL).pack(side="left")
        years = db.list_academic_years()
        ay_vals = [f"{y['id']} - {y['name']}" for y in years]
        var_ay = tk.StringVar()
        cb_ay = ttk.Combobox(f_ay, textvariable=var_ay, values=ay_vals, state="readonly", width=26)
        curr_ay = next((v for v in ay_vals if v.startswith(sem['academic_year_id'] + " -")), ay_vals[0] if ay_vals else "")
        var_ay.set(curr_ay)
        cb_ay.pack(side="left")

        f_sd = tk.Frame(top)
        f_sd.pack(fill="x", padx=20, pady=5)
        tk.Label(f_sd, text="Ngày BĐ (YYYY-MM-DD):", width=20, anchor="w", font=FONT_LABEL).pack(side="left")
        entry_sd = tk.Entry(f_sd, width=20, font=FONT_ENTRY)
        if sem.get('start_date'):
            entry_sd.insert(0, str(sem['start_date']))
        entry_sd.pack(side="left")

        f_ed = tk.Frame(top)
        f_ed.pack(fill="x", padx=20, pady=5)
        tk.Label(f_ed, text="Ngày KT (YYYY-MM-DD):", width=20, anchor="w", font=FONT_LABEL).pack(side="left")
        entry_ed = tk.Entry(f_ed, width=20, font=FONT_ENTRY)
        if sem.get('end_date'):
            entry_ed.insert(0, str(sem['end_date']))
        entry_ed.pack(side="left")

        var_reg = tk.IntVar(value=sem['registration_open'])
        f_reg = tk.Frame(top)
        f_reg.pack(fill="x", padx=20, pady=5)
        tk.Checkbutton(f_reg, text="Mở đăng ký học kỳ", variable=var_reg, font=FONT_LABEL).pack(side="left")

        def save():
            name = entry_name.get().strip()
            ay_sel = var_ay.get()
            sd_s = entry_sd.get().strip()
            ed_s = entry_ed.get().strip()
            if not name or not ay_sel:
                messagebox.showerror("Error", "Điền đầy đủ thông tin", parent=top)
                return
            ay_id = ay_sel.split(" - ")[0]
            sd = sd_s or None
            ed = ed_s or None
            clear_sd = (entry_sd.get().strip() == "" and sem.get('start_date') is not None)
            clear_ed = (entry_ed.get().strip() == "" and sem.get('end_date') is not None)

            if sd:
                try:
                    datetime.strptime(sd, "%Y-%m-%d")
                except ValueError:
                    messagebox.showerror("Error", "Ngày BĐ không hợp lệ (YYYY-MM-DD)", parent=top)
                    return
            if ed:
                try:
                    datetime.strptime(ed, "%Y-%m-%d")
                except ValueError:
                    messagebox.showerror("Error", "Ngày KT không hợp lệ (YYYY-MM-DD)", parent=top)
                    return

            try:
                db.update_semester(
                    sid, registration_open=var_reg.get(), name=name,
                    academic_year_id=ay_id, start_date=sd, end_date=ed,
                    clear_start_date=clear_sd, clear_end_date=clear_ed
                )
                messagebox.showinfo("Success", "Đã cập nhật học kỳ", parent=top)
                top.destroy()
                self.refresh_all_admin_comboboxes()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=top)

        _make_btn(top, "Lưu thay đổi", save, bg=COLOR_PRIMARY, width=15).pack(pady=15)

    def update_semester_dates(self):
        item = self.sem_tree.selection()
        if not item:
            messagebox.showerror("Error", "Chọn một học kỳ trong bảng"); return
        sid = str(self.sem_tree.item(item[0])['values'][0])
        sd = self.sem_start_date.get().strip() or None
        ed = self.sem_end_date.get().strip() or None
        if sd:
            try:
                datetime.strptime(sd, "%Y-%m-%d")
            except ValueError:
                messagebox.showerror("Error", "Ngày BĐ không hợp lệ (YYYY-MM-DD)"); return
        if ed:
            try:
                datetime.strptime(ed, "%Y-%m-%d")
            except ValueError:
                messagebox.showerror("Error", "Ngày KT không hợp lệ (YYYY-MM-DD)"); return
        if sd and ed and sd > ed:
            messagebox.showerror("Error", "Ngày bắt đầu phải trước ngày kết thúc"); return
        try:
            db.update_semester(sid, start_date=sd, end_date=ed)
            messagebox.showinfo("Success", f"Đã cập nhật ngày cho HK {sid}")
            self.sem_start_date.delete(0, "end"); self.sem_end_date.delete(0, "end")
            self.refresh_academic()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def toggle_semester_reg(self):
        item = self.sem_tree.selection()
        if not item:
            messagebox.showerror("Error", "Chọn một học kỳ"); return
        sid = str(self.sem_tree.item(item[0])['values'][0])
        sem = db.get_semester(sid)
        if not sem:
            return
        new_val = 0 if sem['registration_open'] else 1
        db.update_semester(sid, registration_open=new_val)
        self.refresh_academic()
        status = "mở" if new_val else "đóng"
        messagebox.showinfo("Success", f"Đã {status} đăng ký cho HK {sid}")

    # ── BATCH & ADMIN CLASS ──────────────────────────────────────────────
    def build_batch_class(self, parent):
        _make_page_header(parent, "Khóa tuyển sinh & Lớp hành chính", "🏫")

        b_frame = tk.LabelFrame(parent, text="Thêm Khóa tuyển sinh", bg=COLOR_BG,
                                 fg=COLOR_PRIMARY, font=FONT_BODY, padx=15, pady=10)
        b_frame.pack(fill="x", padx=30, pady=5)
        tk.Label(b_frame, text="Mã:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=0, padx=5)
        self.batch_id = tk.Entry(b_frame, width=12, font=FONT_ENTRY); self.batch_id.grid(row=0, column=1, padx=5)
        tk.Label(b_frame, text="Tên:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=2, padx=5)
        self.batch_name = tk.Entry(b_frame, width=15, font=FONT_ENTRY); self.batch_name.grid(row=0, column=3, padx=5)
        tk.Label(b_frame, text="Năm:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=4, padx=5)
        self.batch_year = tk.Entry(b_frame, width=6, font=FONT_ENTRY); self.batch_year.grid(row=0, column=5, padx=5)
        _make_btn(b_frame, "Thêm", self.add_batch, width=8).grid(row=0, column=6, padx=5)
        _make_btn(b_frame, "Sửa", self.edit_batch, bg=COLOR_WARNING, width=6).grid(row=0, column=7, padx=5)

        ac_frame = tk.LabelFrame(parent, text="Thêm Lớp hành chính", bg=COLOR_BG,
                                  fg=COLOR_PRIMARY, font=FONT_BODY, padx=15, pady=10)
        ac_frame.pack(fill="x", padx=30, pady=5)
        tk.Label(ac_frame, text="Mã:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=0, padx=5)
        self.ac_id = tk.Entry(ac_frame, width=12, font=FONT_ENTRY); self.ac_id.grid(row=0, column=1, padx=5)
        tk.Label(ac_frame, text="Tên:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=2, padx=5)
        self.ac_name = tk.Entry(ac_frame, width=15, font=FONT_ENTRY); self.ac_name.grid(row=0, column=3, padx=5)
        tk.Label(ac_frame, text="Ngành:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=4, padx=5)
        self.ac_prog_var = tk.StringVar()
        self.ac_prog_cb = ttk.Combobox(ac_frame, textvariable=self.ac_prog_var, state="readonly", width=18)
        self.ac_prog_cb.grid(row=0, column=5, padx=5)
        tk.Label(ac_frame, text="Khóa:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=6, padx=5)
        self.ac_batch_var = tk.StringVar()
        self.ac_batch_cb = ttk.Combobox(ac_frame, textvariable=self.ac_batch_var, state="readonly", width=15)
        self.ac_batch_cb.grid(row=0, column=7, padx=5)
        _make_btn(ac_frame, "Thêm", self.add_admin_class, width=8).grid(row=0, column=8, padx=5)
        _make_btn(ac_frame, "Sửa", self.edit_admin_class, bg=COLOR_WARNING, width=6).grid(row=0, column=9, padx=5)

        cols_b = ("Mã", "Tên", "Năm")
        batch_frame = tk.Frame(parent)
        batch_frame.pack(fill="x", padx=30, pady=5)
        self.batch_tree = ttk.Treeview(batch_frame, columns=cols_b, show="headings", height=4)
        batch_scroll = ttk.Scrollbar(batch_frame, orient="vertical", command=self.batch_tree.yview)
        self.batch_tree.configure(yscrollcommand=batch_scroll.set)
        for c in cols_b: self.batch_tree.heading(c, text=c); self.batch_tree.column(c, width=180)
        self.batch_tree.pack(side="left", fill="x", expand=True)
        batch_scroll.pack(side="right", fill="y")
        _configure_treeview_tags(self.batch_tree)

        cols_ac = ("Mã lớp", "Tên lớp", "Ngành", "Khóa")
        ac_frame = tk.Frame(parent)
        ac_frame.pack(fill="both", expand=True, padx=30, pady=5)
        self.ac_tree = ttk.Treeview(ac_frame, columns=cols_ac, show="headings", height=6)
        ac_scroll = ttk.Scrollbar(ac_frame, orient="vertical", command=self.ac_tree.yview)
        self.ac_tree.configure(yscrollcommand=ac_scroll.set)
        for c in cols_ac: self.ac_tree.heading(c, text=c); self.ac_tree.column(c, width=180)
        self.ac_tree.pack(side="left", fill="both", expand=True)
        ac_scroll.pack(side="right", fill="y")
        _configure_treeview_tags(self.ac_tree)

        self.refresh_batch_class()

    def refresh_batch_class(self):
        for t in self.batch_tree.get_children(): self.batch_tree.delete(t)
        batches = db.list_admission_batches()
        for i, b in enumerate(batches):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            self.batch_tree.insert("", "end", values=(b['id'], b['name'], b['year']), tags=(tag,))
        self.ac_batch_cb['values'] = [f"{b['id']} - {b['name']}" for b in batches]

        progs = db.list_programs()
        self.ac_prog_cb['values'] = [f"{p['id']} - {p['name']}" for p in progs]

        for t in self.ac_tree.get_children(): self.ac_tree.delete(t)
        classes = db.list_admin_classes()
        for i, c in enumerate(classes):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            self.ac_tree.insert("", "end", values=(c['id'], c['name'], c.get('program_name', ''), c.get('batch_name', '')), tags=(tag,))
        check_empty_treeview(self.batch_tree, "Chưa có khóa tuyển sinh")
        check_empty_treeview(self.ac_tree, "Chưa có lớp hành chính")

    def add_batch(self):
        bid = self.batch_id.get().strip().upper()
        name = self.batch_name.get().strip()
        year_s = self.batch_year.get().strip()
        if not bid or not name or not year_s:
            messagebox.showerror("Error", "Điền đầy đủ thông tin"); return
        try:
            year = int(year_s)
        except ValueError:
            messagebox.showerror("Error", "Năm phải là số"); return
        try:
            db.add_admission_batch(bid, name, year)
            messagebox.showinfo("Success", f"Đã thêm khóa {bid}")
            self.batch_id.delete(0, "end"); self.batch_name.delete(0, "end"); self.batch_year.delete(0, "end")
            self.refresh_batch_class()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def edit_batch(self):
        item = self.batch_tree.selection()
        if not item:
            messagebox.showerror("Error", "Chọn một khóa để sửa"); return
        bid = str(self.batch_tree.item(item[0])['values'][0])
        batch = db.get_admission_batch(bid)
        if not batch:
            messagebox.showerror("Error", f"Khóa {bid} không tồn tại"); return

        top = tk.Toplevel(self.root)
        top.title(f"Sửa Khóa tuyển sinh - {bid}")
        top.geometry("400x240")
        top.grab_set()

        tk.Label(top, text=f"Mã khóa: {bid}", font=FONT_BODY_BOLD).pack(pady=(15, 10))

        f_name = tk.Frame(top)
        f_name.pack(fill="x", padx=20, pady=5)
        tk.Label(f_name, text="Tên khóa:", width=12, anchor="w", font=FONT_LABEL).pack(side="left")
        entry_name = tk.Entry(f_name, width=28, font=FONT_ENTRY)
        entry_name.insert(0, batch['name'])
        entry_name.pack(side="left")

        f_yr = tk.Frame(top)
        f_yr.pack(fill="x", padx=20, pady=5)
        tk.Label(f_yr, text="Năm tuyển sinh:", width=12, anchor="w", font=FONT_LABEL).pack(side="left")
        entry_yr = tk.Entry(f_yr, width=28, font=FONT_ENTRY)
        entry_yr.insert(0, str(batch['year']))
        entry_yr.pack(side="left")

        def save():
            name = entry_name.get().strip()
            year_s = entry_yr.get().strip()
            if not name or not year_s:
                messagebox.showerror("Error", "Điền đầy đủ thông tin", parent=top)
                return
            try:
                year = int(year_s)
            except ValueError:
                messagebox.showerror("Error", "Năm tuyển sinh phải là số", parent=top)
                return
            try:
                db.update_admission_batch(bid, name=name, year=year)
                messagebox.showinfo("Success", "Đã cập nhật khóa tuyển sinh", parent=top)
                top.destroy()
                self.refresh_all_admin_comboboxes()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=top)

        _make_btn(top, "Lưu thay đổi", save, bg=COLOR_PRIMARY, width=15).pack(pady=15)

    def add_admin_class(self):
        cid = self.ac_id.get().strip().upper()
        name = self.ac_name.get().strip()
        prog_sel = self.ac_prog_var.get()
        batch_sel = self.ac_batch_var.get()
        if not cid or not name or not prog_sel or not batch_sel:
            messagebox.showerror("Error", "Điền đầy đủ thông tin"); return
        prog_id = prog_sel.split(" - ")[0]
        batch_id = batch_sel.split(" - ")[0]
        try:
            db.add_admin_class(cid, name, prog_id, batch_id)
            messagebox.showinfo("Success", f"Đã thêm lớp {cid}")
            self.ac_id.delete(0, "end"); self.ac_name.delete(0, "end")
            self.refresh_batch_class()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def edit_admin_class(self):
        item = self.ac_tree.selection()
        if not item:
            messagebox.showerror("Error", "Chọn một lớp HC để sửa"); return
        cid = str(self.ac_tree.item(item[0])['values'][0])
        ac = db.get_admin_class(cid)
        if not ac:
            messagebox.showerror("Error", f"Lớp {cid} không tồn tại"); return

        top = tk.Toplevel(self.root)
        top.title(f"Sửa Lớp hành chính - {cid}")
        top.geometry("420x280")
        top.grab_set()

        tk.Label(top, text=f"Mã lớp HC: {cid}", font=FONT_BODY_BOLD).pack(pady=(15, 10))

        f_name = tk.Frame(top)
        f_name.pack(fill="x", padx=20, pady=5)
        tk.Label(f_name, text="Tên lớp:", width=12, anchor="w", font=FONT_LABEL).pack(side="left")
        entry_name = tk.Entry(f_name, width=28, font=FONT_ENTRY)
        entry_name.insert(0, ac['name'])
        entry_name.pack(side="left")

        f_prog = tk.Frame(top)
        f_prog.pack(fill="x", padx=20, pady=5)
        tk.Label(f_prog, text="Ngành:", width=12, anchor="w", font=FONT_LABEL).pack(side="left")
        progs = db.list_programs()
        prog_vals = [f"{p['id']} - {p['name']}" for p in progs]
        var_prog = tk.StringVar()
        cb_prog = ttk.Combobox(f_prog, textvariable=var_prog, values=prog_vals, state="readonly", width=26)
        curr_prog = next((v for v in prog_vals if v.startswith(str(ac['program_id']) + " -")), prog_vals[0] if prog_vals else "")
        var_prog.set(curr_prog)
        cb_prog.pack(side="left")

        f_batch = tk.Frame(top)
        f_batch.pack(fill="x", padx=20, pady=5)
        tk.Label(f_batch, text="Khóa:", width=12, anchor="w", font=FONT_LABEL).pack(side="left")
        batches = db.list_admission_batches()
        batch_vals = [f"{b['id']} - {b['name']}" for b in batches]
        var_batch = tk.StringVar()
        cb_batch = ttk.Combobox(f_batch, textvariable=var_batch, values=batch_vals, state="readonly", width=26)
        curr_batch = next((v for v in batch_vals if v.startswith(str(ac['batch_id']) + " -")), batch_vals[0] if batch_vals else "")
        var_batch.set(curr_batch)
        cb_batch.pack(side="left")

        def save():
            name = entry_name.get().strip()
            prog_sel = var_prog.get()
            batch_sel = var_batch.get()
            if not name or not prog_sel or not batch_sel:
                messagebox.showerror("Error", "Điền đầy đủ thông tin", parent=top)
                return
            prog_id = prog_sel.split(" - ")[0]
            batch_id = batch_sel.split(" - ")[0]
            try:
                db.update_admin_class(cid, name=name, program_id=prog_id, batch_id=batch_id)
                messagebox.showinfo("Success", "Đã cập nhật lớp hành chính", parent=top)
                top.destroy()
                self.refresh_all_admin_comboboxes()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=top)

        _make_btn(top, "Lưu thay đổi", save, bg=COLOR_PRIMARY, width=15).pack(pady=15)

    # ── SUBJECTS ─────────────────────────────────────────────────────────
    def build_subjects(self, parent):
        _make_page_header(parent, "Danh mục Môn học", "📖")

        form = tk.LabelFrame(parent, text="Thêm Môn học", bg=COLOR_BG,
                              fg=COLOR_PRIMARY, font=FONT_BODY, padx=15, pady=10)
        form.pack(fill="x", padx=30, pady=5)
        tk.Label(form, text="Mã môn:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=0, padx=5)
        self.subj_id = tk.Entry(form, width=15, font=FONT_ENTRY); self.subj_id.grid(row=0, column=1, padx=5)
        tk.Label(form, text="Tên môn:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=2, padx=5)
        self.subj_name = tk.Entry(form, width=25, font=FONT_ENTRY); self.subj_name.grid(row=0, column=3, padx=5)
        tk.Label(form, text="Tín chỉ:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=4, padx=5)
        self.subj_credits = tk.Entry(form, width=5, font=FONT_ENTRY); self.subj_credits.grid(row=0, column=5, padx=5)
        _make_btn(form, "Thêm", self.add_subject, width=8).grid(row=0, column=6, padx=5)
        _make_btn(form, "Sửa", self.edit_subject, bg=COLOR_WARNING, width=6).grid(row=0, column=7, padx=5)

        btn_f = tk.Frame(parent, bg=COLOR_BG)
        btn_f.pack(pady=5)
        _make_btn(btn_f, "Xóa môn", self.delete_subject, bg=COLOR_DANGER, width=12).pack(side="left", padx=5)

        cols = ("Mã môn", "Tên môn", "Tín chỉ")
        subj_frame = tk.Frame(parent)
        subj_frame.pack(fill="both", expand=True, padx=30, pady=5)
        self.subj_tree = ttk.Treeview(subj_frame, columns=cols, show="headings")
        subj_scroll = ttk.Scrollbar(subj_frame, orient="vertical", command=self.subj_tree.yview)
        self.subj_tree.configure(yscrollcommand=subj_scroll.set)
        for c in cols: self.subj_tree.heading(c, text=c); self.subj_tree.column(c, width=200)
        self.subj_tree.pack(side="left", fill="both", expand=True)
        subj_scroll.pack(side="right", fill="y")
        _configure_treeview_tags(self.subj_tree)
        self.refresh_subjects()

    def refresh_subjects(self):
        for t in self.subj_tree.get_children(): self.subj_tree.delete(t)
        for i, s in enumerate(db.list_subjects()):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            self.subj_tree.insert("", "end", values=(s['id'], s['name'], s['credits']), tags=(tag,))
        check_empty_treeview(self.subj_tree, "Chưa có môn học")

    def add_subject(self):
        sid = self.subj_id.get().strip().upper()
        name = self.subj_name.get().strip()
        cred_s = self.subj_credits.get().strip()
        if not sid or not name or not cred_s:
            messagebox.showerror("Error", "Điền đầy đủ thông tin môn học"); return
        try:
            credits = int(cred_s)
            if credits <= 0: raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Tín chỉ phải là số dương"); return
        try:
            db.add_subject(sid, name, credits)
            messagebox.showinfo("Success", f"Đã thêm môn {sid}")
            self.subj_id.delete(0, "end"); self.subj_name.delete(0, "end"); self.subj_credits.delete(0, "end")
            self.refresh_subjects()
            # Refresh section combos if they exist
            if hasattr(self, 'sec_subj_cb'):
                self._refresh_section_combos()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def edit_subject(self):
        item = self.subj_tree.selection()
        if not item:
            messagebox.showerror("Error", "Chọn một môn học để sửa"); return
        sid = str(self.subj_tree.item(item[0])['values'][0])
        old_name = str(self.subj_tree.item(item[0])['values'][1])
        new_name = simpledialog.askstring("Sửa Môn học", f"Tên mới cho {sid}:", initialvalue=old_name)
        if new_name is None:
            return
        new_cred = simpledialog.askinteger("Sửa Tín chỉ", f"Tín chỉ mới cho {sid}:",
                                            initialvalue=int(self.subj_tree.item(item[0])['values'][2]),
                                            minvalue=1, maxvalue=20)
        if new_cred is None:
            return
        try:
            db.update_subject(sid, name=new_name.strip() if new_name else None, credits=new_cred)
            messagebox.showinfo("Success", "Đã cập nhật")
            self.refresh_subjects()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def delete_subject(self):
        item = self.subj_tree.selection()
        if not item:
            messagebox.showerror("Error", "Chọn một môn học"); return
        sid = str(self.subj_tree.item(item[0])['values'][0])
        if messagebox.askyesno("Xác nhận", f"Xóa môn {sid}? Chỉ xóa được môn chưa có lớp HP."):
            try:
                services.delete_subject(db, sid)
                messagebox.showinfo("Success", "Đã xóa")
                self.refresh_subjects()
            except Exception as e:
                messagebox.showerror("Error", str(e))

    # ── CLASS SECTIONS ───────────────────────────────────────────────────
    def build_sections(self, parent):
        _make_page_header(parent, "Quản lý Lớp học phần", "📚")

        # Filter
        filt = tk.Frame(parent, bg=COLOR_BG)
        filt.pack(fill="x", padx=30, pady=5)
        tk.Label(filt, text="Lọc theo HK:", bg=COLOR_BG, font=FONT_LABEL).pack(side="left", padx=5)
        self.sec_sem_var = tk.StringVar()
        self.sec_sem_cb = ttk.Combobox(filt, textvariable=self.sec_sem_var, state="readonly", width=30)
        self.sec_sem_cb.pack(side="left", padx=5)
        _make_btn(filt, "Lọc", self.refresh_sections, width=8).pack(side="left", padx=5)

        # Add form
        form = tk.LabelFrame(parent, text="Thêm Lớp HP", bg=COLOR_BG,
                              fg=COLOR_PRIMARY, font=FONT_BODY, padx=10, pady=8)
        form.pack(fill="x", padx=30, pady=5)

        tk.Label(form, text="Mã lớp HP:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=0, padx=3, pady=3, sticky="w")
        self.sec_id = tk.Entry(form, width=15, font=FONT_ENTRY); self.sec_id.grid(row=0, column=1, padx=3, pady=3)
        tk.Label(form, text="Môn:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=2, padx=3, pady=3, sticky="w")
        self.sec_subj_var = tk.StringVar()
        self.sec_subj_cb = ttk.Combobox(form, textvariable=self.sec_subj_var, state="readonly", width=20)
        self.sec_subj_cb.grid(row=0, column=3, padx=3, pady=3)
        tk.Label(form, text="HK:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=4, padx=3, pady=3, sticky="w")
        self.sec_sem2_var = tk.StringVar()
        self.sec_sem2_cb = ttk.Combobox(form, textvariable=self.sec_sem2_var, state="readonly", width=22)
        self.sec_sem2_cb.grid(row=0, column=5, padx=3, pady=3)

        tk.Label(form, text="GV:", bg=COLOR_BG, font=FONT_LABEL).grid(row=1, column=0, padx=3, pady=3, sticky="w")
        self.sec_lect = tk.Entry(form, width=15, font=FONT_ENTRY); self.sec_lect.grid(row=1, column=1, padx=3, pady=3)
        tk.Label(form, text="Sĩ số:", bg=COLOR_BG, font=FONT_LABEL).grid(row=1, column=2, padx=3, pady=3, sticky="w")
        self.sec_max = tk.Entry(form, width=6, font=FONT_ENTRY); self.sec_max.insert(0, "40"); self.sec_max.grid(row=1, column=3, padx=3, pady=3, sticky="w")
        tk.Label(form, text="Lịch (VD: Thu 2 7h-9h; Thu 4 13h-15h):", bg=COLOR_BG, font=FONT_LABEL).grid(row=1, column=4, padx=3, pady=3, sticky="w", columnspan=2)

        tk.Label(form, text="Lịch học:", bg=COLOR_BG, font=FONT_LABEL).grid(row=2, column=0, padx=3, pady=3, sticky="w")
        self.sec_sched = tk.Entry(form, width=50, font=FONT_ENTRY)
        self.sec_sched.grid(row=2, column=1, padx=3, pady=3, columnspan=4, sticky="w")
        _make_btn(form, "Thêm lớp HP", self.add_section, width=12).grid(row=2, column=5, padx=10, pady=3)

        # Buttons
        btn_f = tk.Frame(parent, bg=COLOR_BG)
        btn_f.pack(pady=5)
        _make_btn(btn_f, "Mở/Đóng ĐK", self.toggle_section_reg, bg=COLOR_WARNING, width=14).pack(side="left", padx=5)
        _make_btn(btn_f, "Sửa lớp HP", self.edit_section, bg=COLOR_WARNING, width=12).pack(side="left", padx=5)
        _make_btn(btn_f, "Xóa lớp HP", self.delete_section, bg=COLOR_DANGER, width=12).pack(side="left", padx=5)

        cols = ("Mã lớp", "Môn", "Học kỳ", "Giảng viên", "Lịch", "Sĩ số", "Đã ĐK", "Đăng ký")
        sec_frame = tk.Frame(parent)
        sec_frame.pack(fill="both", expand=True, padx=30, pady=5)
        self.sec_tree = ttk.Treeview(sec_frame, columns=cols, show="headings")
        sec_tree_scroll = ttk.Scrollbar(sec_frame, orient="vertical", command=self.sec_tree.yview)
        self.sec_tree.configure(yscrollcommand=sec_tree_scroll.set)
        for c in cols: self.sec_tree.heading(c, text=c); self.sec_tree.column(c, width=110)
        self.sec_tree.pack(side="left", fill="both", expand=True)
        sec_tree_scroll.pack(side="right", fill="y")
        _configure_treeview_tags(self.sec_tree)

        self._refresh_section_combos()
        self.refresh_sections()

    def _refresh_section_combos(self):
        sems = db.list_semesters()
        vals = [_sem_cb_value(s) for s in sems]
        self.sec_sem_cb['values'] = ["Tất cả"] + vals
        self.sec_sem2_cb['values'] = vals
        subjs = db.list_subjects()
        self.sec_subj_cb['values'] = [f"{s['id']} - {s['name']}" for s in subjs]

    def refresh_sections(self):
        for t in self.sec_tree.get_children(): self.sec_tree.delete(t)
        sem_sel = self.sec_sem_var.get()
        sem_id = None
        if sem_sel and sem_sel != "Tất cả":
            sem_id = sem_sel.split(" - ")[0]
        sections = db.list_sections(semester_id=sem_id)
        for i, s in enumerate(sections):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            sched = _get_schedule_display(db, s['id'])
            enrolled = db.count_section_enrollments(s['id'])
            reg = "✅ Mở" if s['registration_open'] else "❌ Đóng"
            sem_display = f"{s.get('semester_name', '')} ({s.get('year_name', '')})"
            self.sec_tree.insert("", "end", values=(
                s['id'], s.get('subject_name', ''), sem_display,
                s.get('lecturer', ''), sched, s['max_students'], enrolled, reg
            ), tags=(tag,))
        check_empty_treeview(self.sec_tree, "Chưa có lớp học phần")

    def add_section(self):
        sid = self.sec_id.get().strip().upper()
        subj_sel = self.sec_subj_var.get()
        sem_sel = self.sec_sem2_var.get()
        lect = self.sec_lect.get().strip()
        max_s = self.sec_max.get().strip()
        sched_str = self.sec_sched.get().strip()

        if not sid or not subj_sel or not sem_sel:
            messagebox.showerror("Error", "Điền đầy đủ thông tin lớp HP"); return

        subj_id = subj_sel.split(" - ")[0]
        sem_id = sem_sel.split(" - ")[0]

        try:
            max_students = int(max_s) if max_s else 40
            if max_students <= 0: raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Sĩ số phải là số dương"); return

        if lect and not db.get_user("Lecturer", lect):
            messagebox.showerror("Error", "Giảng viên không tồn tại"); return

        schedules = []
        if sched_str:
            parsed = parse_multi_schedule(sched_str)
            if parsed is None:
                messagebox.showerror("Error", "Lịch không hợp lệ. VD: Thu 2 7h-9h; Thu 4 13h-15h"); return
            schedules = parsed

        try:
            services.create_class_section(db, sid, subj_id, sem_id, lect or None,
                                          max_students, schedules, TUITION_PER_CREDIT)
            if not schedules:
                messagebox.showinfo("Success", f"Đã thêm lớp HP {sid} (nháp — chưa có lịch, đóng ĐK)")
            else:
                messagebox.showinfo("Success", f"Đã thêm lớp HP {sid}")
            self.sec_id.delete(0, "end"); self.sec_sched.delete(0, "end"); self.sec_lect.delete(0, "end")
            self.refresh_sections()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def edit_section(self):
        item = self.sec_tree.selection()
        if not item:
            messagebox.showerror("Error", "Chọn một lớp HP để sửa"); return
        sid = str(self.sec_tree.item(item[0])['values'][0])
        section = db.get_section(sid)
        if not section:
            return
        enrolled = db.count_section_enrollments(sid)
        # Edit max_students
        new_max = simpledialog.askinteger("Sửa Sĩ số", f"Sĩ số tối đa cho {sid}:",
                                           initialvalue=section['max_students'], minvalue=1)
        if new_max is None:
            return
        try:
            services.update_class_section(db, sid, max_students=new_max)
            messagebox.showinfo("Success", "Đã cập nhật")
            self.refresh_sections()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def toggle_section_reg(self):
        item = self.sec_tree.selection()
        if not item:
            messagebox.showerror("Error", "Chọn một lớp HP"); return
        sid = str(self.sec_tree.item(item[0])['values'][0])
        section = db.get_section(sid)
        if not section:
            return
        new_val = 0 if section['registration_open'] else 1
        try:
            services.update_class_section(db, sid, registration_open=new_val)
            self.refresh_sections()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def delete_section(self):
        item = self.sec_tree.selection()
        if not item:
            messagebox.showerror("Error", "Chọn một lớp HP"); return
        sid = str(self.sec_tree.item(item[0])['values'][0])
        if messagebox.askyesno("Xác nhận", f"Xóa lớp HP {sid}?"):
            try:
                services.delete_class_section(db, sid)
                messagebox.showinfo("Success", "Đã xóa")
                self.refresh_sections()
            except Exception as e:
                messagebox.showerror("Error", str(e))

    # ── CREATE LECTURER ──────────────────────────────────────────────────
    def build_create_lecturer(self, parent):
        _make_page_header(parent, "Tạo tài khoản Giảng viên", "👨‍🏫")
        lf = tk.LabelFrame(parent, text="Thông tin giảng viên", bg=COLOR_BG,
                           fg=COLOR_PRIMARY, font=FONT_BODY, padx=20, pady=15)
        lf.pack(pady=20, padx=60)
        tk.Label(lf, text="Username:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=0, pady=12, sticky="w")
        self.l_user = tk.Entry(lf, width=30, font=FONT_ENTRY); self.l_user.grid(row=0, column=1, padx=12, pady=12)
        tk.Label(lf, text="Password:", bg=COLOR_BG, font=FONT_LABEL).grid(row=1, column=0, pady=12, sticky="w")
        self.l_pass = tk.Entry(lf, width=30, font=FONT_ENTRY, show="*"); self.l_pass.grid(row=1, column=1, padx=12, pady=12)
        tk.Button(parent, text="TẠO TÀI KHOẢN", bg=COLOR_PRIMARY, fg="white", font=FONT_BTN_LG,
                  width=20, relief="flat", cursor="hand2",
                  activebackground=COLOR_TOPBAR, activeforeground="white",
                  command=self.create_lecturer).pack(pady=20)

    def create_lecturer(self):
        user = self.l_user.get().strip()
        pw = self.l_pass.get()
        if not user or not pw:
            messagebox.showerror("Error", "Điền đầy đủ thông tin"); return
        if db.get_user("Lecturer", user):
            messagebox.showerror("Error", "Tài khoản đã tồn tại"); return
        try:
            db.create_lecturer(user, pw)
            messagebox.showinfo("Success", f"Đã tạo giảng viên {user}")
            self.l_user.delete(0, "end"); self.l_pass.delete(0, "end")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # ── STUDENTS ─────────────────────────────────────────────────────────
    # ── STUDENTS ─────────────────────────────────────────────────────────
    def build_students(self, parent):
        _make_page_header(parent, "Quản lý Sinh viên", "🎓")

        # Filter and Search bar
        filter_f = tk.LabelFrame(parent, text="Tìm kiếm & Bộ lọc", bg=COLOR_BG, fg=COLOR_PRIMARY, font=FONT_BODY, padx=15, pady=8)
        filter_f.pack(fill="x", padx=30, pady=5)
        
        # Row 1: Search & Status
        tk.Label(filter_f, text="🔍 Tìm (MSSV/Tên):", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=0, padx=5, sticky="w")
        self.st_search_var = tk.StringVar()
        tk.Entry(filter_f, textvariable=self.st_search_var, width=20, font=FONT_ENTRY).grid(row=0, column=1, padx=5)
        
        tk.Label(filter_f, text="Trạng thái:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=2, padx=5, sticky="w")
        self.st_status_var = tk.StringVar()
        self.st_status_cb = ttk.Combobox(filter_f, textvariable=self.st_status_var, state="readonly", width=15)
        self.st_status_cb['values'] = ["(Tất cả)", "Đang học", "Bảo lưu", "Thôi học", "Tốt nghiệp"]
        self.st_status_cb.current(0)
        self.st_status_cb.grid(row=0, column=3, padx=5)

        tk.Label(filter_f, text="Khoa:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=4, padx=5, sticky="w")
        self.st_dept_var = tk.StringVar()
        self.st_dept_cb = ttk.Combobox(filter_f, textvariable=self.st_dept_var, state="readonly", width=15)
        self.st_dept_cb.grid(row=0, column=5, padx=5)
        self.st_dept_cb.bind("<<ComboboxSelected>>", self._on_dept_filter_change)

        _make_btn(filter_f, "Lọc / Tìm", self.search_students, width=8).grid(row=0, column=6, padx=10)
        _make_btn(filter_f, "Xóa lọc", self.clear_filters_and_search, width=8, bg=COLOR_WARNING).grid(row=0, column=7, padx=5)

        # Row 2: Program, Batch, Admin Class
        tk.Label(filter_f, text="Ngành:", bg=COLOR_BG, font=FONT_LABEL).grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.st_prog_var = tk.StringVar()
        self.st_prog_cb = ttk.Combobox(filter_f, textvariable=self.st_prog_var, state="readonly", width=20)
        self.st_prog_cb.grid(row=1, column=1, padx=5, pady=5)
        self.st_prog_cb.bind("<<ComboboxSelected>>", self._on_prog_filter_change)

        tk.Label(filter_f, text="Khóa TS:", bg=COLOR_BG, font=FONT_LABEL).grid(row=1, column=2, padx=5, pady=5, sticky="w")
        self.st_batch_var = tk.StringVar()
        self.st_batch_cb = ttk.Combobox(filter_f, textvariable=self.st_batch_var, state="readonly", width=15)
        self.st_batch_cb.grid(row=1, column=3, padx=5, pady=5)
        self.st_batch_cb.bind("<<ComboboxSelected>>", self._on_batch_filter_change)

        tk.Label(filter_f, text="Lớp HC:", bg=COLOR_BG, font=FONT_LABEL).grid(row=1, column=4, padx=5, pady=5, sticky="w")
        self.st_class_filter_var = tk.StringVar()
        self.st_class_filter_cb = ttk.Combobox(filter_f, textvariable=self.st_class_filter_var, state="readonly", width=15)
        self.st_class_filter_cb.grid(row=1, column=5, padx=5, pady=5)

        # Create student (Collapsed into a smaller line or button if space is tight, but we keep it)
        form = tk.LabelFrame(parent, text="Tạo tài khoản sinh viên", bg=COLOR_BG, fg=COLOR_PRIMARY, font=FONT_BODY, padx=15, pady=8)
        form.pack(fill="x", padx=30, pady=5)
        tk.Label(form, text="Username:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=0, padx=5, sticky="w")
        self.st_user = tk.Entry(form, width=15, font=FONT_ENTRY); self.st_user.grid(row=0, column=1, padx=5)
        tk.Label(form, text="Password:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=2, padx=5, sticky="w")
        self.st_pass = tk.Entry(form, width=15, font=FONT_ENTRY, show="*"); self.st_pass.grid(row=0, column=3, padx=5)
        tk.Label(form, text="Lớp HC:", bg=COLOR_BG, font=FONT_LABEL).grid(row=0, column=4, padx=5, sticky="w")
        self.st_class_var = tk.StringVar()
        self.st_class_cb = ttk.Combobox(form, textvariable=self.st_class_var, state="readonly", width=18)
        self.st_class_cb.grid(row=0, column=5, padx=5)
        _make_btn(form, "Tạo SV", self.create_student, width=10).grid(row=0, column=6, padx=10)

        # Action toolbar
        btn_f = tk.Frame(parent, bg=COLOR_BG)
        btn_f.pack(fill="x", padx=30, pady=5)
        # Primary actions
        _make_btn(btn_f, "📋 Xem hồ sơ", self.view_student_profile, bg=COLOR_PRIMARY, width=13).pack(side="left", padx=3)
        _make_btn(btn_f, "✏️ Sửa thông tin", self.edit_student, bg=COLOR_WARNING, width=14).pack(side="left", padx=3)
        _make_btn(btn_f, "🔄 Đổi trạng thái", self.change_student_status_dialog, bg=COLOR_WARNING, width=15).pack(side="left", padx=3)
        _make_btn(btn_f, "🏫 Gán lớp HC", self.assign_class, bg=COLOR_WARNING, width=12).pack(side="left", padx=3)
        _make_btn(btn_f, "🔑 Đổi mật khẩu", self.change_pw, bg=COLOR_WARNING, width=14).pack(side="left", padx=3)
        # Separator
        tk.Frame(btn_f, bg="#CBD5E1", width=2, height=28).pack(side="left", padx=8, fill="y")
        _make_btn(btn_f, "📊 Xuất CSV", self.export_students_csv, bg=COLOR_SUCCESS, width=11).pack(side="left", padx=3)
        # Danger action - right aligned
        _make_btn(btn_f, "🗑️ Xóa SV", self.delete_student, bg=COLOR_DANGER, width=10).pack(side="right", padx=3)

        self.st_count_label = tk.Label(parent, text="Số kết quả: 0", bg=COLOR_BG, font=FONT_LABEL, fg=COLOR_PRIMARY)
        self.st_count_label.pack(anchor="w", padx=30)

        cols = ("Username", "MSSV", "Tên", "Giới tính", "Lớp HC", "Ngành", "Trạng thái")
        st_frame = tk.Frame(parent)
        st_frame.pack(fill="both", expand=True, padx=30, pady=5)
        self.st_tree = ttk.Treeview(st_frame, columns=cols, show="headings")
        st_scroll = ttk.Scrollbar(st_frame, orient="vertical", command=self.st_tree.yview)
        self.st_tree.configure(yscrollcommand=st_scroll.set)
        for c in cols: self.st_tree.heading(c, text=c); self.st_tree.column(c, width=110)
        self.st_tree.pack(side="left", fill="both", expand=True)
        st_scroll.pack(side="right", fill="y")
        _configure_treeview_tags(self.st_tree)

        # Pagination controls
        page_f = tk.Frame(parent, bg=COLOR_BG)
        page_f.pack(pady=5)
        self.st_page = 1
        self.st_limit = 50
        _make_btn(page_f, "Trang trước", self.prev_page_st, width=10).pack(side="left", padx=5)
        self.st_page_label = tk.Label(page_f, text="Trang 1", bg=COLOR_BG, font=FONT_LABEL)
        self.st_page_label.pack(side="left", padx=10)
        _make_btn(page_f, "Trang sau", self.next_page_st, width=10).pack(side="left", padx=5)

        self.refresh_students()

    def _on_dept_filter_change(self, event=None):
        dept_sel = self.st_dept_var.get()
        if not dept_sel or dept_sel == "(Tất cả)":
            self.st_prog_cb['values'] = ["(Tất cả)"] + [f"{p['id']} - {p['name']}" for p in db.list_programs()]
        else:
            dept_id = dept_sel.split(" - ")[0]
            progs = [p for p in db.list_programs() if str(p.get('department_id')) == str(dept_id)]
            self.st_prog_cb['values'] = ["(Tất cả)"] + [f"{p['id']} - {p['name']}" for p in progs]
        self.st_prog_var.set("(Tất cả)")
        self._update_class_filter_combobox()

    def _on_prog_filter_change(self, event=None):
        self._update_class_filter_combobox()

    def _on_batch_filter_change(self, event=None):
        self._update_class_filter_combobox()

    def _update_class_filter_combobox(self):
        dept_sel = self.st_dept_var.get()
        prog_sel = self.st_prog_var.get()
        batch_sel = self.st_batch_var.get()
        classes = db.list_admin_classes()
        
        if dept_sel and dept_sel != "(Tất cả)":
            dept_id = dept_sel.split(" - ")[0]
            classes = [c for c in classes if str(c.get('department_id', '')) == str(dept_id)]
            
        if prog_sel and prog_sel != "(Tất cả)":
            prog_id = prog_sel.split(" - ")[0]
            classes = [c for c in classes if str(c.get('program_id')) == str(prog_id)]
            
        if batch_sel and batch_sel != "(Tất cả)":
            batch_id = batch_sel.split(" - ")[0]
            classes = [c for c in classes if str(c.get('batch_id')) == str(batch_id)]
            
        old_val = self.st_class_filter_var.get()
        new_values = ["(Tất cả)"] + [f"{c['id']} - {c['name']}" for c in classes]
        self.st_class_filter_cb['values'] = new_values
        
        if old_val in new_values:
            self.st_class_filter_var.set(old_val)
        else:
            self.st_class_filter_var.set("(Tất cả)")

    def clear_filters_and_search(self):
        self.st_search_var.set("")
        self.st_status_var.set("(Tất cả)")
        self.st_dept_var.set("(Tất cả)")
        
        # Restore full prog/class list
        self.st_prog_cb['values'] = ["(Tất cả)"] + [f"{p['id']} - {p['name']}" for p in db.list_programs()]
        self.st_prog_var.set("(Tất cả)")
        self.st_batch_var.set("(Tất cả)")
        
        self.st_class_filter_cb['values'] = ["(Tất cả)"] + [f"{c['id']} - {c['name']}" for c in db.list_admin_classes()]
        self.st_class_filter_var.set("(Tất cả)")
        
        self.st_page = 1
        self.refresh_students()

    def search_students(self):
        self.st_page = 1
        self._load_students()

    def _get_current_student_filters(self):
        filters = {}
        status = self.st_status_var.get()
        if status and status != "(Tất cả)": filters['academic_status'] = status
        
        dept = self.st_dept_var.get()
        if dept and dept != "(Tất cả)": filters['department_id'] = dept.split(" - ")[0]
        
        prog = self.st_prog_var.get()
        if prog and prog != "(Tất cả)": filters['program_id'] = prog.split(" - ")[0]
        
        batch = self.st_batch_var.get()
        if batch and batch != "(Tất cả)": filters['batch_id'] = batch.split(" - ")[0]
        
        cls = self.st_class_filter_var.get()
        if cls and cls != "(Tất cả)": filters['admin_class_id'] = cls.split(" - ")[0]
        
        return filters

    def _load_students(self):
        search_term = self.st_search_var.get().strip()
        filters = self._get_current_student_filters()
        
        # Populate form combobox
        classes = db.list_admin_classes()
        self.st_class_cb['values'] = ["(Chưa phân)"] + [f"{c['id']} - {c['name']}" for c in classes]

        # Populate filter comboboxes if they are empty
        if not self.st_dept_cb['values']:
            self.st_dept_cb['values'] = ["(Tất cả)"] + [f"{d['id']} - {d['name']}" for d in db.list_departments()]
            self.st_prog_cb['values'] = ["(Tất cả)"] + [f"{p['id']} - {p['name']}" for p in db.list_programs()]
            self.st_batch_cb['values'] = ["(Tất cả)"] + [f"{b['id']} - {b['name']}" for b in db.list_admission_batches()]
            self.st_class_filter_cb['values'] = ["(Tất cả)"] + [f"{c['id']} - {c['name']}" for c in classes]

        total_count = db.count_students(search=search_term, filters=filters)
        self.st_count_label.config(text=f"Số kết quả: {total_count}")

        # Adjust page if result set is smaller
        max_page = max(1, (total_count + self.st_limit - 1) // self.st_limit)
        if self.st_page > max_page:
            self.st_page = max_page

        offset = (self.st_page - 1) * self.st_limit
        rows = db.list_students(search=search_term, filters=filters, limit=self.st_limit, offset=offset)

        for t in self.st_tree.get_children(): self.st_tree.delete(t)
        for i, r in enumerate(rows):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            self.st_tree.insert("", "end", values=(
                r['username'], r['mssv'], r.get('name', ''), r.get('gender', ''),
                r.get('class_name', '—'), r.get('program_name', '—'),
                r.get('academic_status', 'Đang học')
            ), tags=(tag,))
        check_empty_treeview(self.st_tree, "Không tìm thấy sinh viên")
        self.st_page_label.config(text=f"Trang {self.st_page}")

    def prev_page_st(self):
        if self.st_page > 1:
            self.st_page -= 1
            self._load_students()

    def next_page_st(self):
        search_term = self.st_search_var.get().strip()
        filters = self._get_current_student_filters()
        total_count = db.count_students(search=search_term, filters=filters)
        max_page = max(1, (total_count + self.st_limit - 1) // self.st_limit)
        if self.st_page < max_page:
            self.st_page += 1
            self._load_students()

    def refresh_students(self):
        self._load_students()

    def create_student(self):
        user = self.st_user.get().strip()
        pw = self.st_pass.get()
        if not user or not pw:
            messagebox.showerror("Error", "Điền username và password"); return
        if db.get_user("Student", user):
            messagebox.showerror("Error", "Tài khoản đã tồn tại"); return
        try:
            mssv = db.add_student(user, pw)
            # Assign admin class if selected
            class_sel = self.st_class_var.get()
            if class_sel and class_sel != "(Chưa phân)":
                class_id = class_sel.split(" - ")[0]
                services.assign_admin_class(db, user, class_id)
            messagebox.showinfo("Success", f"Đã tạo SV {user} (MSSV: {mssv})")
            self.st_user.delete(0, "end"); self.st_pass.delete(0, "end")
            self.refresh_students()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def edit_student(self):
        item = self.st_tree.selection()
        if not item:
            messagebox.showerror("Error", "Chọn một sinh viên để sửa"); return
        username = str(self.st_tree.item(item[0])['values'][0])
        user = db.get_user("Student", username)
        if not user:
            return

        # Edit dialog
        win = tk.Toplevel(self.root)
        win.title(f"Sửa hồ sơ — {username}")
        win.geometry("420x350")
        win.configure(bg=COLOR_BG)
        win.grab_set()

        fields = {
            "Họ tên": tk.StringVar(value=user.get('name', '') or ''),
            "Giới tính": tk.StringVar(value=user.get('gender', '') or ''),
            "Email": tk.StringVar(value=user.get('email', '') or ''),
            "Điện thoại": tk.StringVar(value=user.get('phone', '') or ''),
            "Địa chỉ": tk.StringVar(value=user.get('address', '') or ''),
        }
        entries = {}
        for i, (label, var) in enumerate(fields.items()):
            tk.Label(win, text=f"{label}:", bg=COLOR_BG, font=FONT_LABEL).grid(row=i, column=0, padx=15, pady=8, sticky="w")
            e = tk.Entry(win, textvariable=var, font=FONT_ENTRY, width=30)
            e.grid(row=i, column=1, padx=15, pady=8)
            entries[label] = e

        # Admin class combobox
        tk.Label(win, text="Lớp HC:", bg=COLOR_BG, font=FONT_LABEL).grid(row=len(fields), column=0, padx=15, pady=8, sticky="w")
        cls_var = tk.StringVar()
        classes = db.list_admin_classes()
        cls_values = ["(Không phân)"] + [f"{c['id']} - {c['name']}" for c in classes]
        cls_cb = ttk.Combobox(win, textvariable=cls_var, state="readonly", width=28, values=cls_values)
        cls_cb.grid(row=len(fields), column=1, padx=15, pady=8)
        # Set current
        current_cls = user.get('admin_class_id')
        if current_cls:
            for v in cls_values:
                if v.startswith(f"{current_cls} -"):
                    cls_var.set(v); break
        else:
            cls_var.set("(Không phân)")

        def save():
            name = fields["Họ tên"].get().strip()
            gender = fields["Giới tính"].get().strip()
            email = fields["Email"].get().strip()
            phone = fields["Điện thoại"].get().strip()
            address = fields["Địa chỉ"].get().strip()
            cls_sel = cls_var.get()
            cls_id = None
            if cls_sel and cls_sel != "(Không phân)":
                cls_id = cls_sel.split(" - ")[0]
            try:
                db.update_student_profile(username, name=name, gender=gender,
                                          email=email, phone=phone, address=address,
                                          admin_class_id=cls_id)
                messagebox.showinfo("Success", "Đã cập nhật hồ sơ")
                win.destroy()
                self.refresh_students()
            except Exception as e:
                messagebox.showerror("Error", str(e))

        _make_btn(win, "Lưu", save, width=12).grid(row=len(fields)+1, column=1, pady=15, sticky="e", padx=15)

    def assign_class(self):
        item = self.st_tree.selection()
        if not item:
            messagebox.showerror("Error", "Chọn một sinh viên"); return
        username = str(self.st_tree.item(item[0])['values'][0])
        classes = db.list_admin_classes()
        choices = ["(Bỏ gán)"] + [f"{c['id']} - {c['name']}" for c in classes]
        sel = simpledialog.askstring("Gán lớp HC", f"Chọn lớp cho {username}:\n" + "\n".join(choices))
        if sel is None:
            return
        if sel == "(Bỏ gán)" or not sel.strip():
            class_id = None
        else:
            class_id = sel.strip().split(" - ")[0]
        try:
            services.assign_admin_class(db, username, class_id)
            messagebox.showinfo("Success", "Đã cập nhật")
            self.refresh_students()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def change_pw(self):
        item = self.st_tree.selection()
        if not item:
            messagebox.showerror("Error", "Chọn một sinh viên"); return
        username = str(self.st_tree.item(item[0])['values'][0])
        new_pw = simpledialog.askstring("Đổi mật khẩu", f"Mật khẩu mới cho {username}:")
        if not new_pw or not new_pw.strip():
            return
        from .database import hash_password
        hashed = hash_password(new_pw.strip())
        db.cursor.execute("UPDATE students SET password=%s WHERE username=%s", (hashed, username))
        db.conn.commit()
        messagebox.showinfo("Success", "Đã đổi mật khẩu")

    def delete_student(self):
        item = self.st_tree.selection()
        if not item:
            messagebox.showerror("Error", "Chọn một sinh viên"); return
        username = str(self.st_tree.item(item[0])['values'][0])
        if messagebox.askyesno("Xác nhận", f"Xóa SV {username}? Chỉ xóa được hồ sơ chưa có lịch sử."):
            try:
                services.delete_student(db, username)
                messagebox.showinfo("Success", "Đã xóa")
                self.refresh_students()
            except Exception as e:
                messagebox.showerror("Error", str(e))

    def export_students_csv(self):
        search_term = self.st_search_var.get().strip()
        filters = self._get_current_student_filters()
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Lưu danh sách sinh viên"
        )
        if not file_path:
            return
            
        try:
            count = services.export_students_csv(db, search_term, filters, file_path)
            if count == 0:
                messagebox.showinfo("Info", "Không có dữ liệu để xuất")
            else:
                messagebox.showinfo("Success", f"Đã xuất {count} sinh viên ra file CSV")
        except Exception as e:
            messagebox.showerror("Error", f"Lỗi khi xuất CSV: {e}")

    def change_student_status_dialog(self):
        item = self.st_tree.selection()
        if not item:
            messagebox.showerror("Error", "Chọn một sinh viên")
            return
        mssv = str(self.st_tree.item(item[0])['values'][1])
        curr_status = str(self.st_tree.item(item[0])['values'][6])
        
        top = tk.Toplevel(self.root)
        top.title(f"Đổi trạng thái - {mssv}")
        top.geometry("400x250")
        top.grab_set()
        
        tk.Label(top, text=f"Trạng thái hiện tại: {curr_status}", font=FONT_LABEL).pack(pady=10)
        
        f1 = tk.Frame(top)
        f1.pack(pady=5)
        tk.Label(f1, text="Trạng thái mới:", font=FONT_LABEL).pack(side="left")
        var_status = tk.StringVar(value=curr_status)
        cb = ttk.Combobox(f1, textvariable=var_status, state="readonly", width=15)
        cb['values'] = ["Đang học", "Bảo lưu", "Thôi học", "Tốt nghiệp"]
        cb.pack(side="left", padx=5)
        
        f2 = tk.Frame(top)
        f2.pack(pady=5)
        tk.Label(f2, text="Lý do:", font=FONT_LABEL).pack(side="left")
        entry_reason = tk.Entry(f2, width=30, font=FONT_ENTRY)
        entry_reason.pack(side="left", padx=5)
        
        def save():
            new_st = var_status.get()
            reason = entry_reason.get()
            try:
                services.change_student_status(db, mssv, new_st, reason)
                messagebox.showinfo("Success", "Đã đổi trạng thái thành công", parent=top)
                top.destroy()
                self.refresh_students()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=top)
                
        _make_btn(top, "Lưu", save, width=10).pack(pady=15)

    def view_student_profile(self):
        item = self.st_tree.selection()
        if not item:
            messagebox.showerror("Error", "Chọn một sinh viên")
            return
        mssv = str(self.st_tree.item(item[0])['values'][1])
        
        prof = db.get_student_profile(mssv)
        if not prof:
            messagebox.showerror("Error", "Không tìm thấy hồ sơ")
            return
            
        top = tk.Toplevel(self.root)
        top.title(f"Hồ sơ tổng hợp - {mssv}")
        top.geometry("800x600")
        
        # Info frame
        info_f = tk.LabelFrame(top, text="Thông tin chung", font=FONT_LABEL, padx=10, pady=10)
        info_f.pack(fill="x", padx=10, pady=10)
        
        i = prof['info']
        tk.Label(info_f, text=f"Họ tên: {i.get('name', '')}").grid(row=0, column=0, sticky="w", padx=10)
        tk.Label(info_f, text=f"MSSV: {i['mssv']}").grid(row=0, column=1, sticky="w", padx=10)
        tk.Label(info_f, text=f"Lớp HC: {i.get('class_name', '')}").grid(row=1, column=0, sticky="w", padx=10)
        tk.Label(info_f, text=f"Ngành: {i.get('program_name', '')}").grid(row=1, column=1, sticky="w", padx=10)
        tk.Label(info_f, text=f"Khoa: {i.get('department_name', '')}").grid(row=2, column=0, sticky="w", padx=10)
        tk.Label(info_f, text=f"Khóa: {i.get('batch_name', '')}").grid(row=2, column=1, sticky="w", padx=10)
        tk.Label(info_f, text=f"Trạng thái: {i.get('academic_status', 'Đang học')}", fg=COLOR_PRIMARY, font=("Segoe UI", 11, "bold")).grid(row=3, column=0, sticky="w", padx=10, pady=5)
        
        # Notebook for tabs
        nb = ttk.Notebook(top)
        nb.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Tab 1: Enrollments & Grades
        tab_eg = tk.Frame(nb)
        nb.add(tab_eg, text="Học tập & Điểm")
        
        cols_eg = ("Học kỳ", "Mã HP", "Môn học", "TC", "Giữa kỳ", "Cuối kỳ")
        tree_eg = ttk.Treeview(tab_eg, columns=cols_eg, show="headings")
        for c in cols_eg: tree_eg.heading(c, text=c)
        tree_eg.column("Học kỳ", width=120)
        tree_eg.column("TC", width=40)
        tree_eg.pack(fill="both", expand=True, padx=5, pady=5)
        
        for en in prof['enrollments']:
            g = prof['grades'].get(en['enrollment_id'], {})
            tree_eg.insert("", "end", values=(
                f"{en['semester_name']} ({en['academic_year_name']})",
                en['section_id'],
                en['subject_name'],
                en['credits'],
                g.get('midterm', ''),
                g.get('final_score', '')
            ))
            
        # Tab 2: Payments
        tab_p = tk.Frame(nb)
        nb.add(tab_p, text="Thanh toán")
        
        cols_p = ("Ngày", "Mã HP", "Số tiền", "Trạng thái")
        tree_p = ttk.Treeview(tab_p, columns=cols_p, show="headings")
        for c in cols_p: tree_p.heading(c, text=c)
        tree_p.pack(fill="both", expand=True, padx=5, pady=5)
        
        # We need to map payment to section_id
        # We can create a mapping from enrollment_id to section_id
        en_map = {e['enrollment_id']: e['section_id'] for e in prof['enrollments']}
        for p in prof['payments']:
            tree_p.insert("", "end", values=(
                p['time'],
                en_map.get(p['enrollment_id'], ''),
                f"{p['amount']:,.0f}",
                p['status']
            ))
            
        # Tab 3: History
        tab_h = tk.Frame(nb)
        nb.add(tab_h, text="Lịch sử trạng thái")
        
        cols_h = ("Ngày", "Từ", "Sang", "Lý do", "Người đổi")
        tree_h = ttk.Treeview(tab_h, columns=cols_h, show="headings")
        for c in cols_h: tree_h.heading(c, text=c)
        tree_h.pack(fill="both", expand=True, padx=5, pady=5)
        
        for h in prof['history']:
            tree_h.insert("", "end", values=(
                h['changed_at'],
                h['old_status'],
                h['new_status'],
                h['reason'],
                h['changed_by']
            ))


# ═══════════════════════════════════════════════════════════════════════════
# STUDENT DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════

class StudentDashboard:
    def __init__(self, username):
        self.username = username
        user = db.get_user("Student", username)
        if not user:
            messagebox.showerror("Lỗi", "Không tìm thấy thông tin sinh viên"); return
        self.mssv = user['mssv']
        name = user.get('name') or username

        self.root = tk.Tk()
        self.root.protocol("WM_DELETE_WINDOW", lambda: _close_session_window(self.root))
        self.root.title(f"Cổng Sinh Viên - Quản Lý Đào Tạo | {name} ({self.mssv})")
        self.root.geometry("1220x750")
        self.root.minsize(1050, 650)
        self.root.resizable(True, True)
        self.root.configure(bg=COLOR_BG)

        # ── SIDEBAR ──────────────────────────────────────────────────────────
        sidebar = tk.Frame(self.root, bg=COLOR_TOPBAR, width=245)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        # Profile Card
        tk.Label(sidebar, text="🎓  SINH VIÊN", font=("Segoe UI", 9, "bold"),
                 bg=COLOR_TOPBAR, fg="#99F6E4").pack(pady=(20, 2))
        tk.Label(sidebar, text=name, font=("Segoe UI", 13, "bold"),
                 bg=COLOR_TOPBAR, fg="white", wraplength=220).pack(pady=(0, 2))
        tk.Label(sidebar, text=f"MSSV: {self.mssv}", font=("Segoe UI", 9),
                 bg=COLOR_TOPBAR, fg="#A0AEC0").pack(pady=(0, 16))
        tk.Frame(sidebar, bg="#1A8A8D", height=1).pack(fill="x", padx=16, pady=(0, 10))

        # Menu structure with category grouping
        menu_structure = [
            ("CHÍNH", [
                ("📊  Tổng quan", 0),
            ]),
            ("HỌC TẬP", [
                ("📚  Đăng ký môn học", 1),
                ("📅  Thời khóa biểu", 2),
                ("📊  Kết quả học tập", 3),
            ]),
            ("CÁ NHÂN & TÀI CHÍNH", [
                ("👤  Hồ sơ cá nhân", 4),
                ("💳  Tra cứu học phí", 5),
            ]),
        ]

        self.sidebar_buttons = []
        for category, items in menu_structure:
            if category:
                tk.Label(sidebar, text=f"  {category}", font=("Segoe UI", 9, "bold"),
                         bg=COLOR_TOPBAR, fg="#70B8BA", anchor="w",
                         padx=18).pack(fill="x", pady=(8, 2))
            for text, idx in items:
                btn = tk.Button(sidebar, text=text, font=("Segoe UI", 11),
                                bg=COLOR_TOPBAR, fg="white", relief="flat",
                                anchor="w", padx=18, pady=8, cursor="hand2",
                                activebackground=COLOR_PRIMARY, activeforeground="white",
                                command=lambda i=idx: self._show_page(i))
                btn.pack(fill="x")
                self.sidebar_buttons.append(btn)

        tk.Frame(sidebar, bg=COLOR_TOPBAR).pack(fill="both", expand=True)

        # System info badge & Logout button
        tk.Label(sidebar, text="Học kỳ 2025-2026 • Đào tạo Tín chỉ", font=("Segoe UI", 8),
                 bg=COLOR_TOPBAR, fg="#70B8BA").pack(pady=(0, 6))
        tk.Button(sidebar, text="🚪  Đăng xuất", font=FONT_BTN,
                  bg=COLOR_DANGER, fg="white", relief="flat", cursor="hand2", pady=10,
                  activebackground="#C13639", activeforeground="white",
                  command=self.logout).pack(fill="x", padx=14, pady=(0, 16))

        # ── MAIN CONTENT ─────────────────────────────────────────────────────
        content = tk.Frame(self.root, bg=COLOR_BG)
        content.pack(side="right", fill="both", expand=True)
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)

        self.pages = []
        page_builders = [
            self.build_overview,
            self.build_registration,
            self.build_schedule,
            self.build_grades,
            self.build_profile,
            self.build_payments,
        ]
        for builder in page_builders:
            page = tk.Frame(content, bg=COLOR_BG)
            page.grid(row=0, column=0, sticky="nsew")
            builder(page)
            self.pages.append(page)

        self._show_page(0)
        self.root.mainloop()

    def _show_page(self, index):
        self.pages[index].tkraise()
        for i, btn in enumerate(self.sidebar_buttons):
            if i == index:
                btn.config(bg=COLOR_PRIMARY, font=("Segoe UI", 11, "bold"))
            else:
                btn.config(bg=COLOR_TOPBAR, font=("Segoe UI", 11))
        # Refresh dynamic data on page change
        if index == 0 and hasattr(self, 'refresh_overview'):
            self.refresh_overview()
        elif index == 1 and hasattr(self, 'refresh_registration'):
            self.refresh_registration()
        elif index == 2 and hasattr(self, 'refresh_schedule'):
            self.refresh_schedule()
        elif index == 3 and hasattr(self, 'refresh_grades'):
            self.refresh_grades()
        elif index == 4 and hasattr(self, 'build_profile'):
            self.build_profile(self.pages[4])
        elif index == 5 and hasattr(self, 'refresh_payments'):
            self.refresh_payments()

    def logout(self):
        if messagebox.askyesno("Đăng xuất", "Bạn có chắc muốn đăng xuất khỏi hệ thống?"):
            from .session import session
            session.logout()
            self.root.destroy()
            LoginWindow()

    # ── 1. OVERVIEW ──────────────────────────────────────────────────────
    def build_overview(self, parent):
        user = db.get_user("Student", self.username)
        name = user.get('name') or self.username
        _make_page_header(parent, f"Chào mừng, {name} ({self.mssv})", "🎓")

        container = tk.Frame(parent, bg=COLOR_BG)
        container.pack(fill="both", expand=True, padx=25, pady=15)

        # Stat cards frame (4 cards)
        self.ov_cards_frame = tk.Frame(container, bg=COLOR_BG)
        self.ov_cards_frame.pack(fill="x", pady=(0, 15))
        for c in range(4):
            self.ov_cards_frame.grid_columnconfigure(c, weight=1)

        # Split layout: Left (65%) enrolled courses, Right (35%) academic info & shortcuts
        body_frame = tk.Frame(container, bg=COLOR_BG)
        body_frame.pack(fill="both", expand=True)
        body_frame.grid_columnconfigure(0, weight=65)
        body_frame.grid_columnconfigure(1, weight=35)
        body_frame.grid_rowconfigure(0, weight=1)

        # Left Card: Recent / Enrolled courses
        left_card = tk.Frame(body_frame, bg="white", highlightbackground=COLOR_CARD_BD, highlightthickness=1)
        left_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        left_header = tk.Frame(left_card, bg="#F8FAFC", padx=16, pady=10)
        left_header.pack(fill="x")
        tk.Label(left_header, text="📋  Lớp học phần đang theo học", font=("Segoe UI", 11, "bold"),
                 bg="#F8FAFC", fg=COLOR_TEXT).pack(side="left")
        _make_btn(left_header, "Xem TKB chi tiết", lambda: self._show_page(2), bg=COLOR_PRIMARY, width=15,
                  font=("Segoe UI", 9, "bold")).pack(side="right")
        tk.Frame(left_card, bg="#E2E8F0", height=1).pack(fill="x")

        # Treeview in Left Card
        cols = ("Mã lớp HP", "Tên môn học", "Giảng viên", "Lịch học", "TC", "Học kỳ")
        tree_box = tk.Frame(left_card, bg="white", padx=10, pady=10)
        tree_box.pack(fill="both", expand=True)

        self.ov_tree = ttk.Treeview(tree_box, columns=cols, show="headings", height=8)
        ov_scroll = ttk.Scrollbar(tree_box, orient="vertical", command=self.ov_tree.yview)
        self.ov_tree.configure(yscrollcommand=ov_scroll.set)

        col_config = {
            "Mã lớp HP": (95, "center"),
            "Tên môn học": (180, "w"),
            "Giảng viên": (120, "w"),
            "Lịch học": (140, "w"),
            "TC": (50, "center"),
            "Học kỳ": (110, "center"),
        }
        for c in cols:
            width, align = col_config.get(c, (100, "w"))
            self.ov_tree.heading(c, text=c)
            self.ov_tree.column(c, width=width, anchor=align)

        self.ov_tree.pack(side="left", fill="both", expand=True)
        ov_scroll.pack(side="right", fill="y")
        _configure_treeview_tags(self.ov_tree)
        self.ov_tree.bind("<Double-1>", lambda e: self._show_page(2))

        # Tip under tree
        ov_tip = tk.Frame(left_card, bg="white", padx=14, pady=8)
        ov_tip.pack(fill="x")
        tk.Label(ov_tip, text="💡 Nhấp đúp vào lớp để chuyển sang màn hình Thời khóa biểu chi tiết",
                 font=("Segoe UI", 9, "italic"), bg="white", fg="#64748B").pack(side="left")

        # Right Card: Academic Info & Quick Actions
        right_card = tk.Frame(body_frame, bg="white", highlightbackground=COLOR_CARD_BD, highlightthickness=1)
        right_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        right_header = tk.Frame(right_card, bg="#F8FAFC", padx=16, pady=10)
        right_header.pack(fill="x")
        tk.Label(right_header, text="📌  Thông tin học vụ", font=("Segoe UI", 11, "bold"),
                 bg="#F8FAFC", fg=COLOR_TEXT).pack(side="left")
        tk.Frame(right_card, bg="#E2E8F0", height=1).pack(fill="x")

        right_body = tk.Frame(right_card, bg="white", padx=16, pady=12)
        right_body.pack(fill="both", expand=True)

        self.ov_info_box = tk.Frame(right_body, bg="#F8FAFC", padx=12, pady=10,
                                    highlightbackground="#E2E8F0", highlightthickness=1)
        self.ov_info_box.pack(fill="x", pady=(0, 10))

        # Shortcuts
        tk.Label(right_body, text="Thao tác nhanh:", font=("Segoe UI", 10, "bold"),
                 bg="white", fg=COLOR_TEXT).pack(anchor="w", pady=(2, 6))
        _make_btn(right_body, "📚 Đăng ký môn học mới", lambda: self._show_page(1), bg="#2563EB", width=22).pack(fill="x", pady=3)
        _make_btn(right_body, "📊 Xem bảng điểm chi tiết", lambda: self._show_page(3), bg="#0F6E71", width=22).pack(fill="x", pady=3)
        _make_btn(right_body, "💳 Tra cứu & Đóng học phí", lambda: self._show_page(5), bg="#7C3AED", width=22).pack(fill="x", pady=3)
        _make_btn(right_body, "🔄 Làm mới dữ liệu", self.refresh_overview, bg="#4B5563", width=22).pack(fill="x", pady=3)

        # Notice box
        tip_box = tk.Frame(right_body, bg="#EFF6FF", padx=12, pady=10,
                           highlightbackground="#BFDBFE", highlightthickness=1)
        tip_box.pack(fill="x", pady=(10, 0))
        tk.Label(tip_box, text="💡 Nhắc nhở sinh viên:", font=("Segoe UI", 9, "bold"),
                 bg="#EFF6FF", fg="#1D4ED8").pack(anchor="w")
        tip_text = (
            "• Kiểm tra lịch học trước khi lên giảng đường.\n"
            "• Hạn hủy lớp là 7 ngày sau khi đăng ký.\n"
            "• Hoàn tất học phí đúng hạn quy định."
        )
        tk.Label(tip_box, text=tip_text, font=("Segoe UI", 9),
                 bg="#EFF6FF", fg="#1E40AF", justify="left").pack(anchor="w", pady=(4, 0))

        self.refresh_overview()

    def refresh_overview(self):
        for w in self.ov_cards_frame.winfo_children():
            w.destroy()

        enrollments = db.get_enrollment_details(self.mssv)
        enrolled_count = len(enrollments)
        total_credits = sum(int(e.get('credits_snapshot', 0)) for e in enrollments)

        grades = db.get_grades(self.mssv)
        valid = [(float(g['midterm']) + float(g['final_score'])) / 2
                 for g in grades
                 if g.get('midterm') is not None and g.get('final_score') is not None]
        gpa_str = f"{sum(valid) / len(valid):.2f}" if valid else "Chưa có"

        payments = db.list_payments(self.mssv)
        total_paid = sum(float(p['amount']) for p in payments if p.get('status') == 'Paid')

        _make_card(self.ov_cards_frame, "Lớp HP đã đăng ký", enrolled_count, 0, accent="#0F6E71")
        _make_card(self.ov_cards_frame, "Tổng số tín chỉ", total_credits, 1, accent="#2563EB")
        _make_card(self.ov_cards_frame, "Điểm trung bình (GPA)", gpa_str, 2, accent="#7C3AED")
        _make_card(self.ov_cards_frame, "Học phí đã đóng", f"{total_paid:,.0f} đ", 3, accent="#16A34A")

        if hasattr(self, 'ov_tree'):
            for item in self.ov_tree.get_children():
                self.ov_tree.delete(item)
            for i, e in enumerate(enrollments[:10]):
                tag = "evenrow" if i % 2 == 0 else "oddrow"
                sched = _get_schedule_display(db, e['section_id'])
                sem_display = _sem_display(e)
                self.ov_tree.insert("", "end", values=(
                    e['section_id'], e.get('subject_name', ''),
                    e.get('lecturer') or 'Chưa phân công', sched, e.get('credits_snapshot', ''),
                    sem_display
                ), tags=(tag,))
            check_empty_treeview(self.ov_tree, "Chưa đăng ký lớp học phần nào")

        if hasattr(self, 'ov_info_box'):
            for w in self.ov_info_box.winfo_children():
                w.destroy()
            students = db.list_students()
            my_info = next((s for s in students if s['username'] == self.username), None)
            cls = my_info.get('class_name', '—') if my_info else '—'
            prog = my_info.get('program_name', '—') if my_info else '—'
            batch = my_info.get('batch_name', '—') if my_info else '—'
            status = my_info.get('academic_status', 'Đang học') if my_info else 'Đang học'

            tk.Label(self.ov_info_box, text=f"MSSV: {self.mssv}", font=("Segoe UI", 11, "bold"),
                     bg="#F8FAFC", fg=COLOR_TEXT).pack(anchor="w")
            tk.Label(self.ov_info_box, text=f"Lớp: {cls}  |  Khóa: {batch}", font=("Segoe UI", 9),
                     bg="#F8FAFC", fg="#475569").pack(anchor="w", pady=(2, 0))
            tk.Label(self.ov_info_box, text=f"Ngành: {prog}", font=("Segoe UI", 9),
                     bg="#F8FAFC", fg="#475569").pack(anchor="w", pady=(2, 0))
            tk.Label(self.ov_info_box, text=f"Trạng thái: {status}", font=("Segoe UI", 9, "bold"),
                     bg="#F8FAFC", fg="#16A34A" if status == "Đang học" else "#D97706").pack(anchor="w", pady=(2, 0))

    # ── 2. REGISTRATION ──────────────────────────────────────────────────
    def build_registration(self, parent):
        _make_page_header(parent, "Đăng ký môn học & Lớp học phần", "📚")

        container = tk.Frame(parent, bg=COLOR_BG)
        container.pack(fill="both", expand=True, padx=25, pady=15)

        # Filter & Action toolbar card
        card_toolbar = tk.Frame(container, bg="white", highlightbackground=COLOR_CARD_BD,
                                highlightthickness=1, padx=16, pady=12)
        card_toolbar.pack(fill="x", pady=(0, 10))

        # Left filter tools
        left_tools = tk.Frame(card_toolbar, bg="white")
        left_tools.pack(side="left")

        tk.Label(left_tools, text="📅  Học kỳ mở ĐK:", bg="white", font=FONT_LABEL).pack(side="left", padx=(0, 6))
        self.reg_sem_var = tk.StringVar()
        self.reg_sem_cb = ttk.Combobox(left_tools, textvariable=self.reg_sem_var, state="readonly", width=32)
        self.reg_sem_cb.pack(side="left", padx=(0, 8))
        sems = db.list_semesters()
        open_sems = [s for s in sems if s.get('registration_open')]
        self.reg_sem_cb['values'] = [_sem_cb_value(s) for s in open_sems]
        if open_sems:
            self.reg_sem_cb.current(0)
        self.reg_sem_cb.bind("<<ComboboxSelected>>", lambda e: self.refresh_registration())

        _make_btn(left_tools, "🔄 Làm mới", self.refresh_registration, bg="#4B5563", width=10).pack(side="left", padx=4)

        # Right action tools
        right_tools = tk.Frame(card_toolbar, bg="white")
        right_tools.pack(side="right")

        self.reg_count_lbl = tk.Label(right_tools, text="Tổng: 0 lớp mở",
                                      bg="white", font=("Segoe UI", 10, "bold"), fg="#475569")
        self.reg_count_lbl.pack(side="left", padx=(0, 14))

        _make_btn(right_tools, "✏️ Đăng ký lớp HP", self.enroll_course, bg=COLOR_PRIMARY, width=15).pack(side="left")

        # Guideline banner
        tip_frame = tk.Frame(container, bg="#EFF6FF", highlightbackground="#BFDBFE",
                             highlightthickness=1, padx=12, pady=8)
        tip_frame.pack(fill="x", pady=(0, 10))
        tk.Label(tip_frame, text="💡 Hướng dẫn:", font=("Segoe UI", 9, "bold"), bg="#EFF6FF", fg="#1D4ED8").pack(side="left", padx=(0, 6))
        tk.Label(tip_frame, text="Chọn lớp học phần rồi nhấn 'Đăng ký lớp HP' (hoặc Nhấp đúp chuột). Hệ thống sẽ tự động kiểm tra trùng lịch học và số lượng còn chỗ.",
                 font=("Segoe UI", 9), bg="#EFF6FF", fg="#1E40AF").pack(side="left")

        # Treeview Card
        table_card = tk.Frame(container, bg="white", highlightbackground=COLOR_CARD_BD, highlightthickness=1)
        table_card.pack(fill="both", expand=True)

        cols = ("Mã lớp HP", "Mã môn", "Tên môn học", "Giảng viên", "Lịch học", "Số TC", "Sĩ số", "Còn chỗ")
        tree_frame = tk.Frame(table_card, bg="white", padx=10, pady=10)
        tree_frame.pack(fill="both", expand=True)

        self.reg_tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
        reg_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.reg_tree.yview)
        self.reg_tree.configure(yscrollcommand=reg_scroll.set)

        col_config = {
            "Mã lớp HP": (100, "center"),
            "Mã môn": (80, "center"),
            "Tên môn học": (220, "w"),
            "Giảng viên": (130, "w"),
            "Lịch học": (180, "w"),
            "Số TC": (65, "center"),
            "Sĩ số": (75, "center"),
            "Còn chỗ": (75, "center"),
        }
        for c in cols:
            width, align = col_config.get(c, (100, "w"))
            self.reg_tree.heading(c, text=c)
            self.reg_tree.column(c, width=width, anchor=align)

        self.reg_tree.pack(side="left", fill="both", expand=True)
        reg_scroll.pack(side="right", fill="y")
        _configure_treeview_tags(self.reg_tree)
        self.reg_tree.bind("<Double-1>", self.enroll_course)

        self.refresh_registration()

    def refresh_registration(self):
        if not hasattr(self, 'reg_tree'):
            return
        for t in self.reg_tree.get_children():
            self.reg_tree.delete(t)
        sem_sel = self.reg_sem_var.get() if hasattr(self, 'reg_sem_var') else ""
        if not sem_sel:
            check_empty_treeview(self.reg_tree, "Hiện không có học kỳ nào mở đăng ký")
            return
        sem_id = sem_sel.split(" - ")[0]

        sections = db.list_sections(semester_id=sem_id)
        enrolled = db.get_enrollments(self.mssv, semester_id=sem_id)

        idx = 0
        for s in sections:
            if s['id'] in enrolled:
                continue
            if not s.get('registration_open'):
                continue
            sched = _get_schedule_display(db, s['id'])
            enrolled_count = db.count_section_enrollments(s['id'])
            remaining = s['max_students'] - enrolled_count
            tag = "evenrow" if idx % 2 == 0 else "oddrow"
            self.reg_tree.insert("", "end", values=(
                s['id'], s.get('subject_id', ''), s.get('subject_name', ''),
                s.get('lecturer') or 'Chưa phân công', sched, s.get('credits_snapshot', ''),
                s['max_students'], remaining
            ), tags=(tag,))
            idx += 1

        check_empty_treeview(self.reg_tree, "Không có lớp học phần nào mở đăng ký trong học kỳ này")
        if hasattr(self, 'reg_count_lbl'):
            self.reg_count_lbl.config(text=f"Tổng: {idx} lớp mở")

    def enroll_course(self, event=None):
        if event and hasattr(event, 'widget'):
            item = event.widget.selection()
        else:
            item = self.reg_tree.selection()
        if not item:
            messagebox.showinfo("Thông báo", "Vui lòng chọn một lớp học phần trong danh sách để đăng ký."); return
        vals = self.reg_tree.item(item[0])['values']
        if not vals or any(k in str(vals[0]) for k in ("Hiện không", "Không có", "Chưa")):
            return
        section_id = str(vals[0])
        subject_name = str(vals[2])
        if messagebox.askyesno("Xác nhận đăng ký", f"Bạn có chắc muốn đăng ký lớp học phần:\n{section_id} - {subject_name}?"):
            try:
                services.enroll_student(db, self.mssv, section_id)
                messagebox.showinfo("Thành công", f"Đăng ký thành công lớp {section_id}!")
                self.refresh_registration()
                self.refresh_schedule()
                self.refresh_payments()
                if hasattr(self, 'refresh_overview'):
                    self.refresh_overview()
            except Exception as exc:
                messagebox.showerror("Không thể đăng ký", str(exc))

    # ── 3. SCHEDULE ──────────────────────────────────────────────────────
    def build_schedule(self, parent):
        _make_page_header(parent, "Thời khóa biểu & Lớp học phần đã đăng ký", "📅")

        container = tk.Frame(parent, bg=COLOR_BG)
        container.pack(fill="both", expand=True, padx=25, pady=15)

        # Filter & Action toolbar card
        card_toolbar = tk.Frame(container, bg="white", highlightbackground=COLOR_CARD_BD,
                                highlightthickness=1, padx=16, pady=12)
        card_toolbar.pack(fill="x", pady=(0, 10))

        # Left filter tools
        left_tools = tk.Frame(card_toolbar, bg="white")
        left_tools.pack(side="left")

        tk.Label(left_tools, text="📅  Học kỳ:", bg="white", font=FONT_LABEL).pack(side="left", padx=(0, 6))
        self.sched_sem_var = tk.StringVar(value="Tất cả")
        self.sched_sem_cb = ttk.Combobox(left_tools, textvariable=self.sched_sem_var, state="readonly", width=32)
        self.sched_sem_cb.pack(side="left", padx=(0, 8))
        sems = db.list_semesters()
        self.sched_sem_cb['values'] = ["Tất cả"] + [_sem_cb_value(s) for s in sems]
        self.sched_sem_cb.bind("<<ComboboxSelected>>", lambda e: self.refresh_schedule())

        _make_btn(left_tools, "🔄 Làm mới", self.refresh_schedule, bg="#4B5563", width=10).pack(side="left", padx=4)

        # Right action tools
        right_tools = tk.Frame(card_toolbar, bg="white")
        right_tools.pack(side="right")

        self.sched_count_lbl = tk.Label(right_tools, text="Tổng: 0 lớp đã đăng ký",
                                        bg="white", font=("Segoe UI", 10, "bold"), fg="#475569")
        self.sched_count_lbl.pack(side="left", padx=(0, 14))

        _make_btn(right_tools, "❌ Hủy đăng ký lớp này", self.unenroll_course, bg=COLOR_DANGER, width=17).pack(side="left")

        # Guideline banner
        tip_frame = tk.Frame(container, bg="#EFF6FF", highlightbackground="#BFDBFE",
                             highlightthickness=1, padx=12, pady=8)
        tip_frame.pack(fill="x", pady=(0, 10))
        tk.Label(tip_frame, text="💡 Quy định học vụ:", font=("Segoe UI", 9, "bold"), bg="#EFF6FF", fg="#1D4ED8").pack(side="left", padx=(0, 6))
        tk.Label(tip_frame, text=f"Hạn hủy đăng ký lớp là {UNENROLL_DEADLINE_DAYS} ngày kể từ ngày đăng ký. Lớp đã có điểm hoặc đã thanh toán học phí không thể hủy tự động.",
                 font=("Segoe UI", 9), bg="#EFF6FF", fg="#1E40AF").pack(side="left")

        # Treeview Card
        table_card = tk.Frame(container, bg="white", highlightbackground=COLOR_CARD_BD, highlightthickness=1)
        table_card.pack(fill="both", expand=True)

        cols = ("Mã lớp HP", "Mã môn", "Tên môn học", "Giảng viên", "Lịch học", "Số TC", "Học kỳ")
        tree_frame = tk.Frame(table_card, bg="white", padx=10, pady=10)
        tree_frame.pack(fill="both", expand=True)

        self.sched_tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
        sched_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.sched_tree.yview)
        self.sched_tree.configure(yscrollcommand=sched_scroll.set)

        col_config = {
            "Mã lớp HP": (105, "center"),
            "Mã môn": (85, "center"),
            "Tên môn học": (230, "w"),
            "Giảng viên": (140, "w"),
            "Lịch học": (190, "w"),
            "Số TC": (65, "center"),
            "Học kỳ": (130, "center"),
        }
        for c in cols:
            width, align = col_config.get(c, (110, "w"))
            self.sched_tree.heading(c, text=c)
            self.sched_tree.column(c, width=width, anchor=align)

        self.sched_tree.pack(side="left", fill="both", expand=True)
        sched_scroll.pack(side="right", fill="y")
        _configure_treeview_tags(self.sched_tree)

        self.refresh_schedule()

    def refresh_schedule(self):
        if not hasattr(self, 'sched_tree'):
            return
        for t in self.sched_tree.get_children():
            self.sched_tree.delete(t)
        sem_sel = self.sched_sem_var.get() if hasattr(self, 'sched_sem_var') else ""
        sem_id = None
        if sem_sel and sem_sel != "Tất cả":
            sem_id = sem_sel.split(" - ")[0]

        enrollments = db.get_enrollment_details(self.mssv, semester_id=sem_id)
        for i, e in enumerate(enrollments):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            sched = _get_schedule_display(db, e['section_id'])
            sem_display = _sem_display(e)
            self.sched_tree.insert("", "end", values=(
                e['section_id'], e.get('subject_id', ''), e.get('subject_name', ''),
                e.get('lecturer') or 'Chưa phân công', sched, e.get('credits_snapshot', ''),
                sem_display
            ), tags=(tag,))

        check_empty_treeview(self.sched_tree, "Chưa đăng ký lớp học phần nào trong học kỳ này")
        if hasattr(self, 'sched_count_lbl'):
            self.sched_count_lbl.config(text=f"Tổng: {len(enrollments)} lớp đã đăng ký")

    def unenroll_course(self):
        item = self.sched_tree.selection()
        if not item:
            messagebox.showinfo("Thông báo", "Vui lòng chọn một lớp học phần để hủy đăng ký."); return
        vals = self.sched_tree.item(item[0])['values']
        if not vals or any(k in str(vals[0]) for k in ("Chưa", "Không có", "Vui lòng")):
            return
        section_id = str(vals[0])
        subject_name = str(vals[2]) if len(vals) > 2 else section_id
        if messagebox.askyesno("Xác nhận hủy", f"Bạn có chắc muốn hủy đăng ký lớp học phần:\n{section_id} - {subject_name}?"):
            try:
                services.unenroll_student(db, self.mssv, section_id, UNENROLL_DEADLINE_DAYS)
                messagebox.showinfo("Thành công", f"Đã hủy đăng ký lớp {section_id} thành công!")
                self.refresh_schedule()
                self.refresh_registration()
                self.refresh_payments()
                if hasattr(self, 'refresh_overview'):
                    self.refresh_overview()
            except Exception as exc:
                messagebox.showerror("Không thể hủy", str(exc))

    # ── 4. GRADES ────────────────────────────────────────────────────────
    def build_grades(self, parent):
        _make_page_header(parent, "Kết quả học tập & Bảng điểm", "📊")

        container = tk.Frame(parent, bg=COLOR_BG)
        container.pack(fill="both", expand=True, padx=25, pady=15)

        # Control Panel Card
        ctrl_card = tk.Frame(container, bg="white", highlightbackground=COLOR_CARD_BD,
                             highlightthickness=1, padx=16, pady=12)
        ctrl_card.pack(fill="x", pady=(0, 10))

        # Top row: filters & export
        row1 = tk.Frame(ctrl_card, bg="white")
        row1.pack(fill="x", pady=(0, 10))

        tk.Label(row1, text="📅  Học kỳ:", bg="white", font=FONT_LABEL).pack(side="left", padx=(0, 6))
        self.grade_sem_var_st = tk.StringVar(value="Tất cả")
        self.grade_sem_cb_st = ttk.Combobox(row1, textvariable=self.grade_sem_var_st, state="readonly", width=30)
        self.grade_sem_cb_st.pack(side="left", padx=(0, 10))
        sems = db.list_semesters()
        self.grade_sem_cb_st['values'] = ["Tất cả"] + [_sem_cb_value(s) for s in sems]
        self.grade_sem_cb_st.bind("<<ComboboxSelected>>", lambda e: self.refresh_grades())

        _make_btn(row1, "🔄 Làm mới", self.refresh_grades, bg="#4B5563", width=10).pack(side="left", padx=4)
        _make_btn(row1, "📥 Xuất bảng điểm (CSV)", self.export_student_grades_csv, bg=COLOR_SUCCESS, width=20).pack(side="right")

        # Separator
        tk.Frame(ctrl_card, bg="#E2E8F0", height=1).pack(fill="x", pady=(0, 10))

        # Bottom row: Grade Statistics
        row2 = tk.Frame(ctrl_card, bg="white")
        row2.pack(fill="x")
        self.grade_stats_lbl_st = tk.Label(
            row2, text="Tổng môn: 0  |  Số TC tích lũy: 0  |  Điểm trung bình (GPA): —  |  Số môn đạt: 0",
            bg="white", font=("Segoe UI", 10, "bold"), fg="#0F6E71"
        )
        self.grade_stats_lbl_st.pack(side="left")

        # Treeview Card
        table_card = tk.Frame(container, bg="white", highlightbackground=COLOR_CARD_BD, highlightthickness=1)
        table_card.pack(fill="both", expand=True)

        cols = ("STT", "Mã lớp HP", "Tên môn học", "Học kỳ", "Số TC", "Điểm GK", "Điểm CK", "Điểm TB", "Kết quả")
        tree_frame = tk.Frame(table_card, bg="white", padx=10, pady=10)
        tree_frame.pack(fill="both", expand=True)

        self.grade_tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
        grade_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.grade_tree.yview)
        self.grade_tree.configure(yscrollcommand=grade_scroll.set)

        col_config = {
            "STT": (45, "center"),
            "Mã lớp HP": (100, "center"),
            "Tên môn học": (220, "w"),
            "Học kỳ": (120, "center"),
            "Số TC": (60, "center"),
            "Điểm GK": (90, "center"),
            "Điểm CK": (90, "center"),
            "Điểm TB": (90, "center"),
            "Kết quả": (110, "center"),
        }
        for c in cols:
            width, align = col_config.get(c, (100, "w"))
            self.grade_tree.heading(c, text=c)
            self.grade_tree.column(c, width=width, anchor=align)

        self.grade_tree.pack(side="left", fill="both", expand=True)
        grade_scroll.pack(side="right", fill="y")
        _configure_treeview_tags(self.grade_tree)

        self.refresh_grades()

    def refresh_grades(self):
        if not hasattr(self, 'grade_tree'):
            return
        for t in self.grade_tree.get_children():
            self.grade_tree.delete(t)
        sem_sel = self.grade_sem_var_st.get() if hasattr(self, 'grade_sem_var_st') else ""
        sem_id = None
        if sem_sel and sem_sel != "Tất cả":
            sem_id = sem_sel.split(" - ")[0]

        grades = db.get_grades(self.mssv, semester_id=sem_id)
        total_subjects = len(grades)
        accum_credits = 0
        passed_subjects = 0
        valid_avgs = []

        for i, g in enumerate(grades):
            mid = g.get('midterm')
            fin = g.get('final_score')
            credits = int(g.get('credits_snapshot', 0))

            mid_disp = f"{float(mid):.1f}" if mid is not None else "—"
            fin_disp = f"{float(fin):.1f}" if fin is not None else "—"

            if mid is not None and fin is not None:
                avg = round((float(mid) + float(fin)) / 2, 1)
                valid_avgs.append(avg)
                avg_disp = f"{avg:.1f}"
                if avg >= 4.0:
                    status = "✅ Đạt"
                    passed_subjects += 1
                    accum_credits += credits
                else:
                    status = "❌ Chưa đạt"
            elif mid is not None or fin is not None:
                avg_disp = "—"
                status = "⏳ Thiếu điểm"
            else:
                avg_disp = "—"
                status = "⏳ Đang học"

            tag = "evenrow" if i % 2 == 0 else "oddrow"
            sem_display = _sem_display(g)
            self.grade_tree.insert("", "end", values=(
                i + 1,
                g['section_id'], g.get('subject_name', ''),
                sem_display, credits,
                mid_disp, fin_disp, avg_disp, status
            ), tags=(tag,))

        check_empty_treeview(self.grade_tree, "Chưa có dữ liệu điểm học phần")

        # Update stats label
        gpa_str = f"{(sum(valid_avgs) / len(valid_avgs)):.2f}" if valid_avgs else "—"
        if hasattr(self, 'grade_stats_lbl_st'):
            self.grade_stats_lbl_st.config(
                text=f"Tổng môn: {total_subjects}  |  Số TC tích lũy: {accum_credits}  |  Điểm trung bình (GPA): {gpa_str}  |  Số môn đạt: {passed_subjects}"
            )

    def export_student_grades_csv(self):
        children = self.grade_tree.get_children()
        if not children:
            messagebox.showinfo("Thông báo", "Không có dữ liệu điểm để xuất."); return

        first_vals = self.grade_tree.item(children[0])['values']
        if not first_vals or any(k in str(first_vals[0]) for k in ("Chưa", "Không có", "Vui lòng")):
            messagebox.showinfo("Thông báo", "Không có dữ liệu điểm hợp lệ để xuất."); return

        default_filename = f"BangDiem_{self.mssv}_{datetime.now().strftime('%Y%m%d')}.csv"
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=default_filename,
            filetypes=[("CSV file (*.csv)", "*.csv"), ("Tất cả tập tin (*.*)", "*.*")],
            title="Xuất bảng điểm sinh viên ra file CSV"
        )
        if not file_path:
            return

        try:
            with open(file_path, mode="w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["STT", "Mã lớp HP", "Tên môn học", "Học kỳ", "Số TC", "Điểm GK", "Điểm CK", "Điểm TB", "Kết quả"])
                for item in children:
                    vals = self.grade_tree.item(item)['values']
                    writer.writerow(vals)
            messagebox.showinfo("Thành công", f"Đã xuất bảng điểm thành công!\nĐường dẫn: {file_path}")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể xuất file: {e}")

    # ── 5. PROFILE ───────────────────────────────────────────────────────
    def build_profile(self, parent):
        for w in parent.winfo_children():
            w.destroy()

        _make_page_header(parent, "Hồ sơ cá nhân sinh viên", "👤")

        container = tk.Frame(parent, bg=COLOR_BG)
        container.pack(fill="both", expand=True, padx=25, pady=15)

        user = db.get_user("Student", self.username)
        students = db.list_students()
        my_info = next((s for s in students if s['username'] == self.username), None)

        cls = my_info.get('class_name', '—') if my_info else '—'
        prog = my_info.get('program_name', '—') if my_info else '—'
        batch = my_info.get('batch_name', '—') if my_info else '—'
        status = my_info.get('academic_status', 'Đang học') if my_info else 'Đang học'
        st_name = user.get('name') or self.username

        # Identity Card (Top)
        id_card = tk.Frame(container, bg="white", highlightbackground=COLOR_CARD_BD,
                           highlightthickness=1, padx=24, pady=18)
        id_card.pack(fill="x", pady=(0, 15))

        id_top = tk.Frame(id_card, bg="white")
        id_top.pack(fill="x")

        # Avatar & Name
        tk.Label(id_top, text="🎓", font=("Segoe UI", 36), bg="white").pack(side="left", padx=(0, 16))

        id_text = tk.Frame(id_top, bg="white")
        id_text.pack(side="left", fill="y")
        self.profile_name_lbl = tk.Label(id_text, text=st_name, font=("Segoe UI", 16, "bold"),
                                         bg="white", fg=COLOR_TEXT)
        self.profile_name_lbl.pack(anchor="w")
        tk.Label(id_text, text=f"Mã số sinh viên: {self.mssv}   •   Tài khoản: {self.username}",
                 font=("Segoe UI", 10), bg="white", fg="#475569").pack(anchor="w", pady=(2, 0))

        # Tags row
        tags_row = tk.Frame(id_card, bg="white")
        tags_row.pack(fill="x", pady=(14, 0))

        def make_pill(parent, text, bg, fg):
            lbl = tk.Label(parent, text=f"  {text}  ", font=("Segoe UI", 9, "bold"),
                           bg=bg, fg=fg, padx=6, pady=4)
            lbl.pack(side="left", padx=(0, 8))

        make_pill(tags_row, f"🏫 Lớp HC: {cls}", "#EFF6FF", "#1D4ED8")
        make_pill(tags_row, f"🏛️ Ngành: {prog}", "#F3E8FF", "#7E22CE")
        make_pill(tags_row, f"📅 Khóa: {batch}", "#FEF3C7", "#B45309")
        make_pill(tags_row, f"🟢 Trạng thái: {status}", "#DCFCE7", "#15803D")

        # Form Card (Bottom)
        form_card = tk.Frame(container, bg="white", highlightbackground=COLOR_CARD_BD,
                             highlightthickness=1, padx=24, pady=20)
        form_card.pack(fill="both", expand=True)

        tk.Label(form_card, text="Thông tin liên lạc & Chi tiết cá nhân",
                 font=("Segoe UI", 12, "bold"), bg="white", fg=COLOR_TEXT).pack(anchor="w", pady=(0, 14))
        tk.Frame(form_card, bg="#E2E8F0", height=1).pack(fill="x", pady=(0, 16))

        self.profile_vars = {
            "name": tk.StringVar(value=user.get('name', '') or ''),
            "gender": tk.StringVar(value=user.get('gender', '') or ''),
            "email": tk.StringVar(value=user.get('email', '') or ''),
            "phone": tk.StringVar(value=user.get('phone', '') or ''),
            "address": tk.StringVar(value=user.get('address', '') or ''),
        }

        # 2-column grid for inputs
        grid_frame = tk.Frame(form_card, bg="white")
        grid_frame.pack(fill="x", pady=(0, 16))
        grid_frame.grid_columnconfigure(0, weight=1)
        grid_frame.grid_columnconfigure(1, weight=1)

        self.profile_entries = {}
        fields = [
            ("name", "Họ và tên sinh viên:", 0, 0),
            ("gender", "Giới tính (Nam / Nữ / Khác):", 1, 0),
            ("email", "Email liên hệ:", 2, 0),
            ("phone", "Số điện thoại:", 0, 1),
            ("address", "Địa chỉ liên lạc:", 1, 1),
        ]

        for key, label_text, r, c in fields:
            cell = tk.Frame(grid_frame, bg="white", padx=12, pady=8)
            cell.grid(row=r, column=c, sticky="nsew")

            tk.Label(cell, text=label_text, bg="white", font=("Segoe UI", 10, "bold"),
                     fg="#334155").pack(anchor="w", pady=(0, 4))
            entry = tk.Entry(cell, textvariable=self.profile_vars[key], font=FONT_ENTRY,
                             relief="solid", bd=1, state="disabled")
            entry.pack(fill="x", ipady=4)
            self.profile_entries[key] = entry

        # Read-only field for status
        status_cell = tk.Frame(grid_frame, bg="white", padx=12, pady=8)
        status_cell.grid(row=2, column=1, sticky="nsew")
        tk.Label(status_cell, text="Tình trạng đào tạo:", bg="white", font=("Segoe UI", 10, "bold"),
                 fg="#334155").pack(anchor="w", pady=(0, 4))
        st_ent = tk.Entry(status_cell, font=FONT_ENTRY, relief="solid", bd=1, state="normal")
        st_ent.insert(0, f"{status} (Được quản lý bởi P.Đào tạo)")
        st_ent.config(state="disabled")
        st_ent.pack(fill="x", ipady=4)

        # Buttons
        btn_bar = tk.Frame(form_card, bg="white")
        btn_bar.pack(anchor="w", padx=12, pady=(10, 0))

        self.edit_btn = _make_btn(btn_bar, "✏️ Chỉnh sửa hồ sơ", self.edit_profile, bg=COLOR_WARNING, width=17)
        self.edit_btn.pack(side="left", padx=(0, 10))

        self.save_btn = _make_btn(btn_bar, "💾 Lưu thay đổi", self.save_profile, bg=COLOR_SUCCESS, width=15)
        self.save_btn.pack(side="left", padx=(0, 10))
        self.save_btn.config(state="disabled")

        self.cancel_btn = _make_btn(btn_bar, "Hủy bỏ", self.cancel_profile_edit, bg="#64748B", width=12)
        self.cancel_btn.pack(side="left")
        self.cancel_btn.config(state="disabled")

    def edit_profile(self):
        for entry in self.profile_entries.values():
            entry.config(state="normal")
        self.edit_btn.config(state="disabled")
        self.save_btn.config(state="normal")
        self.cancel_btn.config(state="normal")

    def cancel_profile_edit(self):
        user = db.get_user("Student", self.username)
        for key in self.profile_vars:
            self.profile_vars[key].set(user.get(key, '') or '')
        for entry in self.profile_entries.values():
            entry.config(state="disabled")
        self.edit_btn.config(state="normal")
        self.save_btn.config(state="disabled")
        self.cancel_btn.config(state="disabled")

    def save_profile(self):
        name = self.profile_vars["name"].get().strip()
        gender = self.profile_vars["gender"].get().strip()
        email = self.profile_vars["email"].get().strip()
        phone = self.profile_vars["phone"].get().strip()
        address = self.profile_vars["address"].get().strip()

        if not name or not email:
            messagebox.showerror("Lỗi", "Họ tên và Email không được để trống!"); return
        if "@" not in email or "." not in email:
            messagebox.showerror("Lỗi", "Định dạng Email không hợp lệ!"); return

        try:
            db.update_student_profile(self.username, name=name, gender=gender,
                                      email=email, phone=phone, address=address)
        except Exception as e:
            messagebox.showerror("Lỗi cập nhật", str(e)); return

        messagebox.showinfo("Thành công", "Đã cập nhật hồ sơ cá nhân thành công!")
        for entry in self.profile_entries.values():
            entry.config(state="disabled")
        self.edit_btn.config(state="normal")
        self.save_btn.config(state="disabled")
        self.cancel_btn.config(state="disabled")
        self.root.title(f"Cổng Sinh Viên - Quản Lý Đào Tạo | {name} ({self.mssv})")
        if hasattr(self, 'profile_name_lbl'):
            self.profile_name_lbl.config(text=name)
        if hasattr(self, 'refresh_overview'):
            self.refresh_overview()

    # ── 6. PAYMENTS ──────────────────────────────────────────────────────
    def build_payments(self, parent):
        _make_page_header(parent, "Quản lý & Tra cứu học phí", "💳")

        container = tk.Frame(parent, bg=COLOR_BG)
        container.pack(fill="both", expand=True, padx=25, pady=15)

        # Card 1: Enrolled sections tuition
        card1 = tk.Frame(container, bg="white", highlightbackground=COLOR_CARD_BD,
                         highlightthickness=1, padx=16, pady=12)
        card1.pack(fill="both", expand=True, pady=(0, 12))

        c1_head = tk.Frame(card1, bg="white")
        c1_head.pack(fill="x", pady=(0, 8))
        tk.Label(c1_head, text="💳  Danh sách học phí các lớp học phần", font=("Segoe UI", 11, "bold"),
                 bg="white", fg=COLOR_TEXT).pack(side="left")
        self.pay_summary_lbl = tk.Label(c1_head, text="Chưa thanh toán: 0 đ",
                                        font=("Segoe UI", 10, "bold"), bg="white", fg=COLOR_DANGER)
        self.pay_summary_lbl.pack(side="right")

        cols = ("Mã lớp HP", "Tên môn học", "Số TC", "Đơn giá / TC", "Thành tiền (VNĐ)", "Học kỳ", "Trạng thái")
        tree1_box = tk.Frame(card1, bg="white")
        tree1_box.pack(fill="both", expand=True, pady=(0, 8))

        self.pay_enroll_tree = ttk.Treeview(tree1_box, columns=cols, show="headings", height=5)
        scroll1 = ttk.Scrollbar(tree1_box, orient="vertical", command=self.pay_enroll_tree.yview)
        self.pay_enroll_tree.configure(yscrollcommand=scroll1.set)

        col_config1 = {
            "Mã lớp HP": (110, "center"),
            "Tên môn học": (230, "w"),
            "Số TC": (65, "center"),
            "Đơn giá / TC": (110, "center"),
            "Thành tiền (VNĐ)": (130, "center"),
            "Học kỳ": (120, "center"),
            "Trạng thái": (120, "center"),
        }
        for c in cols:
            width, align = col_config1.get(c, (110, "w"))
            self.pay_enroll_tree.heading(c, text=c)
            self.pay_enroll_tree.column(c, width=width, anchor=align)

        self.pay_enroll_tree.pack(side="left", fill="both", expand=True)
        scroll1.pack(side="right", fill="y")
        _configure_treeview_tags(self.pay_enroll_tree)

        # Action bar under pay_enroll_tree
        act_bar = tk.Frame(card1, bg="white")
        act_bar.pack(fill="x")
        tk.Label(act_bar, text="💡 Chọn lớp học phần và bấm 'Thanh toán' để đóng học phí (Cổng mô phỏng ngân hàng)",
                 font=("Segoe UI", 9, "italic"), bg="white", fg="#64748B").pack(side="left")
        _make_btn(act_bar, "💳 Thanh toán lớp đã chọn", self.pay_selected, bg=COLOR_PRIMARY, width=22).pack(side="right")

        # Card 2: Payment History
        card2 = tk.Frame(container, bg="white", highlightbackground=COLOR_CARD_BD,
                         highlightthickness=1, padx=16, pady=12)
        card2.pack(fill="both", expand=True)

        c2_head = tk.Frame(card2, bg="white")
        c2_head.pack(fill="x", pady=(0, 8))
        tk.Label(c2_head, text="🧾  Lịch sử giao dịch thanh toán", font=("Segoe UI", 11, "bold"),
                 bg="white", fg=COLOR_TEXT).pack(side="left")

        # Filter in card 2
        f_box = tk.Frame(c2_head, bg="white")
        f_box.pack(side="right")
        tk.Label(f_box, text="📅 Học kỳ:", bg="white", font=FONT_LABEL).pack(side="left", padx=4)
        self.pay_sem_var = tk.StringVar(value="Tất cả")
        self.pay_sem_cb = ttk.Combobox(f_box, textvariable=self.pay_sem_var, state="readonly", width=22)
        self.pay_sem_cb.pack(side="left", padx=4)
        sems = db.list_semesters()
        self.pay_sem_cb['values'] = ["Tất cả"] + [_sem_cb_value(s) for s in sems]
        self.pay_sem_cb.bind("<<ComboboxSelected>>", lambda e: self.refresh_payment_history())
        _make_btn(f_box, "Lọc", self.refresh_payment_history, bg="#4B5563", width=6).pack(side="left", padx=4)

        cols2 = ("Mã GD", "Mã lớp HP", "Tên môn học", "Số tiền (VNĐ)", "Trạng thái", "Thời gian thanh toán", "Học kỳ")
        tree2_box = tk.Frame(card2, bg="white")
        tree2_box.pack(fill="both", expand=True)

        self.pay_hist_tree = ttk.Treeview(tree2_box, columns=cols2, show="headings", height=5)
        scroll2 = ttk.Scrollbar(tree2_box, orient="vertical", command=self.pay_hist_tree.yview)
        self.pay_hist_tree.configure(yscrollcommand=scroll2.set)

        col_config2 = {
            "Mã GD": (70, "center"),
            "Mã lớp HP": (110, "center"),
            "Tên môn học": (220, "w"),
            "Số tiền (VNĐ)": (130, "center"),
            "Trạng thái": (100, "center"),
            "Thời gian thanh toán": (150, "center"),
            "Học kỳ": (120, "center"),
        }
        for c in cols2:
            width, align = col_config2.get(c, (110, "w"))
            self.pay_hist_tree.heading(c, text=c)
            self.pay_hist_tree.column(c, width=width, anchor=align)

        self.pay_hist_tree.pack(side="left", fill="both", expand=True)
        scroll2.pack(side="right", fill="y")
        _configure_treeview_tags(self.pay_hist_tree)

        self.refresh_payments()

    def refresh_payments(self):
        if not hasattr(self, 'pay_enroll_tree'):
            return
        for t in self.pay_enroll_tree.get_children():
            self.pay_enroll_tree.delete(t)

        enrollments = db.get_enrollment_details(self.mssv)
        payments = db.list_payments(self.mssv)
        paid_sections = {p['section_id'] for p in payments if p.get('status') == 'Paid'}

        unpaid_total = Decimal(0)
        paid_total = Decimal(0)

        for i, e in enumerate(enrollments):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            credits = e['credits_snapshot']
            price = e['tuition_per_credit']
            total = Decimal(str(credits)) * Decimal(str(price))
            sem_display = _sem_display(e)
            is_paid = e['section_id'] in paid_sections
            status_text = "✅ Đã thanh toán" if is_paid else "⏳ Chưa thanh toán"

            if is_paid:
                paid_total += total
            else:
                unpaid_total += total

            self.pay_enroll_tree.insert("", "end", values=(
                e['section_id'], e.get('subject_name', ''), credits,
                f"{float(price):,.0f}", f"{float(total):,.0f}", sem_display,
                status_text
            ), tags=(tag,))

        check_empty_treeview(self.pay_enroll_tree, "Chưa có lớp học phần nào được đăng ký")

        if hasattr(self, 'pay_summary_lbl'):
            self.pay_summary_lbl.config(
                text=f"Chưa thanh toán: {float(unpaid_total):,.0f} đ   |   Đã thanh toán: {float(paid_total):,.0f} đ"
            )

        self.refresh_payment_history()

    def refresh_payment_history(self):
        if not hasattr(self, 'pay_hist_tree'):
            return
        for t in self.pay_hist_tree.get_children():
            self.pay_hist_tree.delete(t)
        sem_sel = self.pay_sem_var.get() if hasattr(self, 'pay_sem_var') else ""
        sem_id = None
        if sem_sel and sem_sel != "Tất cả":
            sem_id = sem_sel.split(" - ")[0]

        payments = db.list_payments(self.mssv, semester_id=sem_id)
        for i, p in enumerate(payments):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            sem_display = _sem_display(p)
            self.pay_hist_tree.insert("", "end", values=(
                p['id'], p.get('section_id', ''), p.get('subject_name', ''),
                f"{float(p['amount']):,.0f}", p['status'], p.get('time', ''),
                sem_display
            ), tags=(tag,))

        check_empty_treeview(self.pay_hist_tree, "Chưa có giao dịch thanh toán học phí nào")

    def pay_selected(self):
        item = self.pay_enroll_tree.selection()
        if not item:
            messagebox.showinfo("Thông báo", "Vui lòng chọn một lớp học phần để thanh toán học phí."); return

        vals = self.pay_enroll_tree.item(item[0])['values']
        if not vals or len(vals) < 5 or any(k in str(vals[0]) for k in ("Chưa", "Không có", "Vui lòng")):
            messagebox.showerror("Lỗi", "Vui lòng chọn một lớp học phần hợp lệ."); return

        if len(vals) > 6 and "Đã thanh toán" in str(vals[6]):
            messagebox.showinfo("Thông báo", "Lớp học phần này đã được thanh toán hoàn tất trước đó."); return

        section_id = str(vals[0])
        subject_name = str(vals[1])
        total_str = str(vals[4])

        try:
            total = float(str(total_str).replace(",", ""))
        except ValueError:
            messagebox.showerror("Lỗi", "Không thể đọc số tiền thanh toán."); return

        if not messagebox.askyesno("Xác nhận thanh toán học phí",
                                   f"Thực hiện thanh toán {total_str} VNĐ cho lớp:\n{section_id} ({subject_name})?\n\n(Cổng thanh toán điện tử mô phỏng)"):
            return
        try:
            pid = services.create_payment(db, self.mssv, section_id, total, status="Paid")
            messagebox.showinfo("Thành công", f"Ghi nhận thanh toán thành công!\nMã giao dịch: {pid}\nSố tiền: {total_str} VNĐ")
            self.refresh_payments()
            if hasattr(self, 'refresh_overview'):
                self.refresh_overview()
        except Exception as e:
            messagebox.showerror("Lỗi thanh toán", str(e))


# ═══════════════════════════════════════════════════════════════════════════
# LECTURER DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════

class LecturerDashboard:
    def __init__(self, username):
        self.username = username
        self.root = tk.Tk()
        self.root.protocol("WM_DELETE_WINDOW", lambda: _close_session_window(self.root))
        self.root.title(f"Cổng Giảng Viên - Quản Lý Đào Tạo | {username}")
        self.root.geometry("1200x750")
        self.root.minsize(1050, 650)
        self.root.resizable(True, True)
        self.root.configure(bg=COLOR_BG)

        # ── SIDEBAR ──────────────────────────────────────────────────────────
        sidebar = tk.Frame(self.root, bg=COLOR_TOPBAR, width=245)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        # Lecturer Profile Card
        tk.Label(sidebar, text="👨‍🏫  GIẢNG VIÊN", font=("Segoe UI", 9, "bold"),
                 bg=COLOR_TOPBAR, fg="#99F6E4").pack(pady=(20, 2))
        tk.Label(sidebar, text=username, font=("Segoe UI", 14, "bold"),
                 bg=COLOR_TOPBAR, fg="white").pack(pady=(0, 4))
        tk.Label(sidebar, text="Cổng Quản Lý Đào Tạo", font=("Segoe UI", 9),
                 bg=COLOR_TOPBAR, fg="#A0AEC0").pack(pady=(0, 16))
        tk.Frame(sidebar, bg="#1A8A8D", height=1).pack(fill="x", padx=16, pady=(0, 10))

        # Menu structure with category grouping
        menu_structure = [
            ("CHÍNH", [
                ("📊  Tổng quan", 0),
            ]),
            ("GIẢNG DẠY", [
                ("📚  Lớp HP của tôi", 1),
                ("📝  Quản lý điểm số", 2),
            ]),
        ]

        self.sidebar_buttons = []
        for category, items in menu_structure:
            if category:
                tk.Label(sidebar, text=f"  {category}", font=("Segoe UI", 9, "bold"),
                         bg=COLOR_TOPBAR, fg="#70B8BA", anchor="w",
                         padx=18).pack(fill="x", pady=(8, 2))
            for text, idx in items:
                btn = tk.Button(sidebar, text=text, font=("Segoe UI", 11),
                                bg=COLOR_TOPBAR, fg="white", relief="flat",
                                anchor="w", padx=18, pady=9, cursor="hand2",
                                activebackground=COLOR_PRIMARY, activeforeground="white",
                                command=lambda i=idx: self._show_page(i))
                btn.pack(fill="x")
                self.sidebar_buttons.append(btn)

        tk.Frame(sidebar, bg=COLOR_TOPBAR).pack(fill="both", expand=True)

        # System info badge & Logout button
        tk.Label(sidebar, text="Phiên bản 2.0  •  Học kỳ 2025-2026", font=("Segoe UI", 8),
                 bg=COLOR_TOPBAR, fg="#70B8BA").pack(pady=(0, 6))
        tk.Button(sidebar, text="🚪  Đăng xuất", font=FONT_BTN,
                  bg=COLOR_DANGER, fg="white", relief="flat", cursor="hand2", pady=10,
                  activebackground="#C13639", activeforeground="white",
                  command=self.logout).pack(fill="x", padx=14, pady=(0, 16))

        # ── MAIN CONTENT ─────────────────────────────────────────────────────
        content = tk.Frame(self.root, bg=COLOR_BG)
        content.pack(side="right", fill="both", expand=True)
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)

        self.section_var = tk.StringVar()
        self.loaded_section_id = None
        self.section_var.trace_add("write", self._section_changed)

        self.pages = []
        page_builders = [
            self.build_overview,
            self.build_my_sections,
            self.build_grade_entry,
        ]
        for builder in page_builders:
            page = tk.Frame(content, bg=COLOR_BG)
            page.grid(row=0, column=0, sticky="nsew")
            builder(page)
            self.pages.append(page)

        self._show_page(0)
        self.root.mainloop()

    def _show_page(self, index):
        self.pages[index].tkraise()
        for i, btn in enumerate(self.sidebar_buttons):
            if i == index:
                btn.config(bg=COLOR_PRIMARY, font=("Segoe UI", 11, "bold"))
            else:
                btn.config(bg=COLOR_TOPBAR, font=("Segoe UI", 11))
        # Refresh dynamic data on page change
        if index == 0 and hasattr(self, 'refresh_overview'):
            self.refresh_overview()
        elif index == 1 and hasattr(self, 'refresh_my_sections'):
            self.refresh_my_sections()

    def logout(self):
        if messagebox.askyesno("Đăng xuất", "Bạn có chắc muốn đăng xuất khỏi hệ thống?"):
            from .session import session
            session.logout()
            self.root.destroy()
            LoginWindow()

    # ── 1. OVERVIEW ──────────────────────────────────────────────────────
    def build_overview(self, parent):
        self.overview_parent = parent
        _make_page_header(parent, "Tổng quan giảng viên", "📊")

        container = tk.Frame(parent, bg=COLOR_BG)
        container.pack(fill="both", expand=True, padx=25, pady=15)

        # Stat cards frame (4 cards)
        self.cards_frame = tk.Frame(container, bg=COLOR_BG)
        self.cards_frame.pack(fill="x", pady=(0, 15))
        for c in range(4):
            self.cards_frame.grid_columnconfigure(c, weight=1)

        # Split layout: Left (70%) table of sections, Right (30%) shortcuts & tips
        body_frame = tk.Frame(container, bg=COLOR_BG)
        body_frame.pack(fill="both", expand=True)
        body_frame.grid_columnconfigure(0, weight=7)
        body_frame.grid_columnconfigure(1, weight=3)
        body_frame.grid_rowconfigure(0, weight=1)

        # Left Card: Assigned sections
        left_card = tk.Frame(body_frame, bg="white", highlightbackground=COLOR_CARD_BD, highlightthickness=1)
        left_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        left_header = tk.Frame(left_card, bg="#F8FAFC", padx=16, pady=10)
        left_header.pack(fill="x")
        tk.Label(left_header, text="📋  Lớp học phần đang phụ trách", font=("Segoe UI", 11, "bold"),
                 bg="#F8FAFC", fg=COLOR_TEXT).pack(side="left")
        _make_btn(left_header, "Xem tất cả", lambda: self._show_page(1), bg=COLOR_PRIMARY, width=10,
                  font=("Segoe UI", 9, "bold")).pack(side="right")
        tk.Frame(left_card, bg="#E2E8F0", height=1).pack(fill="x")

        # Treeview for Overview
        cols = ("Mã lớp HP", "Tên môn học", "Lịch dạy", "TC", "Đã ĐK / Tối đa", "Học kỳ")
        tree_box = tk.Frame(left_card, bg="white", padx=10, pady=10)
        tree_box.pack(fill="both", expand=True)

        self.ov_tree = ttk.Treeview(tree_box, columns=cols, show="headings", height=8)
        ov_scroll = ttk.Scrollbar(tree_box, orient="vertical", command=self.ov_tree.yview)
        self.ov_tree.configure(yscrollcommand=ov_scroll.set)

        col_config = {
            "Mã lớp HP": (95, "center"),
            "Tên môn học": (190, "w"),
            "Lịch dạy": (150, "w"),
            "TC": (50, "center"),
            "Đã ĐK / Tối đa": (100, "center"),
            "Học kỳ": (120, "center"),
        }
        for c in cols:
            width, align = col_config.get(c, (100, "w"))
            self.ov_tree.heading(c, text=c)
            self.ov_tree.column(c, width=width, anchor=align)

        self.ov_tree.pack(side="left", fill="both", expand=True)
        ov_scroll.pack(side="right", fill="y")
        _configure_treeview_tags(self.ov_tree)
        self.ov_tree.bind("<Double-1>", lambda e: self._ov_go_to_grade())

        # Action bar under tree
        ov_actions = tk.Frame(left_card, bg="white", padx=14, pady=8)
        ov_actions.pack(fill="x")
        tk.Label(ov_actions, text="💡 Nhấp đúp vào lớp để mở bảng nhập điểm nhanh",
                 font=("Segoe UI", 9, "italic"), bg="white", fg="#64748B").pack(side="left")
        _make_btn(ov_actions, "📝 Vào điểm lớp này", self._ov_go_to_grade, bg=COLOR_PRIMARY, width=16).pack(side="right")

        # Right Card: Shortcuts & Guidelines
        right_card = tk.Frame(body_frame, bg="white", highlightbackground=COLOR_CARD_BD, highlightthickness=1)
        right_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        right_header = tk.Frame(right_card, bg="#F8FAFC", padx=16, pady=10)
        right_header.pack(fill="x")
        tk.Label(right_header, text="📌  Thông tin & Lối tắt", font=("Segoe UI", 11, "bold"),
                 bg="#F8FAFC", fg=COLOR_TEXT).pack(side="left")
        tk.Frame(right_card, bg="#E2E8F0", height=1).pack(fill="x")

        right_body = tk.Frame(right_card, bg="white", padx=16, pady=12)
        right_body.pack(fill="both", expand=True)

        # Info Box
        info_box = tk.Frame(right_body, bg="#F8FAFC", padx=12, pady=10, highlightbackground="#E2E8F0", highlightthickness=1)
        info_box.pack(fill="x", pady=(0, 12))
        tk.Label(info_box, text=f"Tài khoản: {self.username}", font=("Segoe UI", 11, "bold"),
                 bg="#F8FAFC", fg=COLOR_TEXT).pack(anchor="w")
        tk.Label(info_box, text="Vai trò: Giảng viên phụ trách môn", font=("Segoe UI", 9),
                 bg="#F8FAFC", fg="#475569").pack(anchor="w", pady=(2, 0))
        tk.Label(info_box, text="Trạng thái: Đang công tác", font=("Segoe UI", 9),
                 bg="#F8FAFC", fg="#16A34A").pack(anchor="w", pady=(2, 0))

        # Shortcuts
        tk.Label(right_body, text="Thao tác nhanh:", font=("Segoe UI", 10, "bold"),
                 bg="white", fg=COLOR_TEXT).pack(anchor="w", pady=(4, 6))
        _make_btn(right_body, "📚 Xem lớp học phần", lambda: self._show_page(1), bg="#2563EB", width=22).pack(fill="x", pady=3)
        _make_btn(right_body, "📝 Quản lý nhập điểm", lambda: self._show_page(2), bg=COLOR_PRIMARY, width=22).pack(fill="x", pady=3)
        _make_btn(right_body, "🔄 Làm mới dữ liệu", self.refresh_overview, bg="#4B5563", width=22).pack(fill="x", pady=3)

        # Policy & Note card
        tip_box = tk.Frame(right_body, bg="#EFF6FF", padx=12, pady=10, highlightbackground="#BFDBFE", highlightthickness=1)
        tip_box.pack(fill="x", pady=(14, 0))
        tk.Label(tip_box, text="💡 Lưu ý nhập điểm:", font=("Segoe UI", 9, "bold"), bg="#EFF6FF", fg="#1D4ED8").pack(anchor="w")
        tip_text = (
            "• Thang điểm chuẩn: 0.0 - 10.0.\n"
            "• Đạt học phần khi Điểm TB >= 4.0.\n"
            "• Nhấp đúp vào sinh viên để nhập điểm.\n"
            "• Có thể xuất bảng điểm ra file CSV."
        )
        tk.Label(tip_box, text=tip_text, font=("Segoe UI", 9), bg="#EFF6FF", fg="#1E40AF", justify="left").pack(anchor="w", pady=(4, 0))

        self.refresh_overview()

    def refresh_overview(self):
        for w in self.cards_frame.winfo_children():
            w.destroy()

        sections = db.list_sections(lecturer=self.username)
        num_sections = len(sections)
        num_students = db.count_students_of_lecturer(self.username)
        total_credits = sum(int(s.get('credits_snapshot', 0)) for s in sections)
        distinct_sems = len(set(s.get('semester_id') for s in sections if s.get('semester_id')))

        _make_card(self.cards_frame, "Lớp HP đang phụ trách", num_sections, 0, accent="#0F6E71")
        _make_card(self.cards_frame, "Tổng sinh viên giảng dạy", num_students, 1, accent="#2563EB")
        _make_card(self.cards_frame, "Tổng tín chỉ phụ trách", total_credits, 2, accent="#7C3AED")
        _make_card(self.cards_frame, "Số học kỳ tham gia", distinct_sems, 3, accent="#D97706")

        if hasattr(self, 'ov_tree'):
            for item in self.ov_tree.get_children():
                self.ov_tree.delete(item)
            for i, s in enumerate(sections[:12]):
                tag = "evenrow" if i % 2 == 0 else "oddrow"
                sched = _get_schedule_display(db, s['id'])
                enrolled = db.count_section_enrollments(s['id'])
                sem_display = _sem_display(s)
                self.ov_tree.insert("", "end", values=(
                    s['id'], s.get('subject_name', ''), sched,
                    s.get('credits_snapshot', ''), f"{enrolled} / {s.get('max_students', '')}",
                    sem_display
                ), tags=(tag,))
            check_empty_treeview(self.ov_tree, "Chưa được phân công lớp học phần nào")

    def _ov_go_to_grade(self):
        sel = self.ov_tree.selection()
        if not sel:
            messagebox.showinfo("Thông báo", "Vui lòng chọn một lớp học phần trong danh sách.")
            return
        vals = self.ov_tree.item(sel[0])['values']
        if not vals or any(k in str(vals[0]) for k in ("Chưa", "Không có", "Vui lòng")):
            return
        section_id = str(vals[0])
        self.go_to_grade_section(section_id)

    # ── 2. MY SECTIONS ───────────────────────────────────────────────────
    def build_my_sections(self, parent):
        _make_page_header(parent, "Danh sách lớp học phần phụ trách", "📚")

        container = tk.Frame(parent, bg=COLOR_BG)
        container.pack(fill="both", expand=True, padx=25, pady=15)

        # Filter & Action toolbar card
        card_toolbar = tk.Frame(container, bg="white", highlightbackground=COLOR_CARD_BD,
                                highlightthickness=1, padx=16, pady=12)
        card_toolbar.pack(fill="x", pady=(0, 12))

        # Left filter tools
        left_tools = tk.Frame(card_toolbar, bg="white")
        left_tools.pack(side="left")

        tk.Label(left_tools, text="📅  Học kỳ:", bg="white", font=FONT_LABEL).pack(side="left", padx=(0, 6))
        self.lect_sem_var = tk.StringVar(value="Tất cả")
        self.lect_sem_cb = ttk.Combobox(left_tools, textvariable=self.lect_sem_var, state="readonly", width=32)
        self.lect_sem_cb.pack(side="left", padx=(0, 8))
        sems = db.list_semesters()
        self.lect_sem_cb['values'] = ["Tất cả"] + [_sem_cb_value(s) for s in sems]
        self.lect_sem_cb.bind("<<ComboboxSelected>>", lambda e: self.refresh_my_sections())

        _make_btn(left_tools, "🔄 Làm mới", self.refresh_my_sections, bg="#4B5563", width=10).pack(side="left", padx=4)

        # Right action tools
        right_tools = tk.Frame(card_toolbar, bg="white")
        right_tools.pack(side="right")

        self.lect_count_lbl = tk.Label(right_tools, text="Tổng cộng: 0 lớp học phần",
                                       bg="white", font=("Segoe UI", 10, "bold"), fg="#475569")
        self.lect_count_lbl.pack(side="left", padx=(0, 14))

        _make_btn(right_tools, "📝 Vào điểm lớp này", self._sections_go_to_grade, bg=COLOR_PRIMARY, width=16).pack(side="left")

        # Treeview Card
        table_card = tk.Frame(container, bg="white", highlightbackground=COLOR_CARD_BD, highlightthickness=1)
        table_card.pack(fill="both", expand=True)

        cols = ("Mã lớp HP", "Tên môn học", "Thời khóa biểu / Lịch học", "Số TC", "Sĩ số tối đa", "Đã ĐK", "Học kỳ")
        tree_frame = tk.Frame(table_card, bg="white", padx=10, pady=10)
        tree_frame.pack(fill="both", expand=True)

        self.lect_tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
        lect_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.lect_tree.yview)
        self.lect_tree.configure(yscrollcommand=lect_scroll.set)

        col_config = {
            "Mã lớp HP": (110, "center"),
            "Tên môn học": (240, "w"),
            "Thời khóa biểu / Lịch học": (210, "w"),
            "Số TC": (70, "center"),
            "Sĩ số tối đa": (95, "center"),
            "Đã ĐK": (85, "center"),
            "Học kỳ": (140, "center"),
        }
        for c in cols:
            width, align = col_config.get(c, (120, "w"))
            self.lect_tree.heading(c, text=c)
            self.lect_tree.column(c, width=width, anchor=align)

        self.lect_tree.pack(side="left", fill="both", expand=True)
        lect_scroll.pack(side="right", fill="y")
        _configure_treeview_tags(self.lect_tree)
        self.lect_tree.bind("<Double-1>", lambda e: self._sections_go_to_grade())

        self.refresh_my_sections()

    def refresh_my_sections(self):
        if not hasattr(self, 'lect_tree'):
            return
        for t in self.lect_tree.get_children():
            self.lect_tree.delete(t)
        sem_sel = self.lect_sem_var.get() if hasattr(self, 'lect_sem_var') else ""
        sem_id = None
        if sem_sel and sem_sel != "Tất cả":
            sem_id = sem_sel.split(" - ")[0]

        sections = db.list_sections(lecturer=self.username, semester_id=sem_id)
        for i, s in enumerate(sections):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            sched = _get_schedule_display(db, s['id'])
            enrolled = db.count_section_enrollments(s['id'])
            sem_display = _sem_display(s)
            self.lect_tree.insert("", "end", values=(
                s['id'], s.get('subject_name', ''), sched,
                s['credits_snapshot'], s['max_students'], enrolled,
                sem_display
            ), tags=(tag,))

        check_empty_treeview(self.lect_tree, "Không có lớp học phần nào trong học kỳ này")
        if hasattr(self, 'lect_count_lbl'):
            self.lect_count_lbl.config(text=f"Tổng cộng: {len(sections)} lớp học phần")

    def _sections_go_to_grade(self):
        sel = self.lect_tree.selection()
        if not sel:
            messagebox.showinfo("Thông báo", "Vui lòng chọn một lớp học phần để vào điểm.")
            return
        vals = self.lect_tree.item(sel[0])['values']
        if not vals or any(k in str(vals[0]) for k in ("Chưa", "Không có", "Vui lòng")):
            return
        section_id = str(vals[0])
        self.go_to_grade_section(section_id)

    def go_to_grade_section(self, section_id):
        # Switch to Grade Entry page (page index 2)
        self._show_page(2)

        # Set semester to "Tất cả" to ensure the section appears in dropdown
        self.grade_sem_var.set("Tất cả")
        self._update_section_combo()

        # Find matching item in grade_section_cb values
        matching = None
        for val in self.grade_section_cb['values']:
            if val.startswith(f"{section_id} -") or val == section_id:
                matching = val
                break

        if matching:
            self.section_var.set(matching)
            self.load_students()
        else:
            self.section_var.set(section_id)
            self.load_students()

    # ── 3. GRADE ENTRY ───────────────────────────────────────────────────
    def build_grade_entry(self, parent):
        _make_page_header(parent, "Quản lý & Nhập điểm sinh viên", "📝")

        container = tk.Frame(parent, bg=COLOR_BG)
        container.pack(fill="both", expand=True, padx=25, pady=15)

        # Control Panel Card
        ctrl_card = tk.Frame(container, bg="white", highlightbackground=COLOR_CARD_BD,
                             highlightthickness=1, padx=16, pady=12)
        ctrl_card.pack(fill="x", pady=(0, 10))

        # Top row: filters
        row1 = tk.Frame(ctrl_card, bg="white")
        row1.pack(fill="x", pady=(0, 10))

        tk.Label(row1, text="📅  Học kỳ:", bg="white", font=FONT_LABEL).pack(side="left", padx=(0, 6))
        self.grade_sem_var = tk.StringVar(value="Tất cả")
        self.grade_sem_cb = ttk.Combobox(row1, textvariable=self.grade_sem_var, state="readonly", width=24)
        self.grade_sem_cb.pack(side="left", padx=(0, 15))
        sems = db.list_semesters()
        self.grade_sem_cb['values'] = ["Tất cả"] + [_sem_cb_value(s) for s in sems]
        self.grade_sem_cb.bind("<<ComboboxSelected>>", self._update_section_combo)

        tk.Label(row1, text="📚  Lớp học phần:", bg="white", font=FONT_LABEL).pack(side="left", padx=(0, 6))
        self.grade_section_cb = ttk.Combobox(row1, textvariable=self.section_var, state="readonly", width=34)
        self.grade_section_cb.pack(side="left", padx=(0, 12))
        self.grade_section_cb.bind("<<ComboboxSelected>>", lambda e: self.load_students())

        _make_btn(row1, "🔍 Tải danh sách", self.load_students, bg=COLOR_PRIMARY, width=13).pack(side="left", padx=4)

        # Separator inside card
        tk.Frame(ctrl_card, bg="#E2E8F0", height=1).pack(fill="x", pady=(0, 10))

        # Bottom row: Actions & Statistics
        row2 = tk.Frame(ctrl_card, bg="white")
        row2.pack(fill="x")

        # Action buttons
        btn_box = tk.Frame(row2, bg="white")
        btn_box.pack(side="left")

        _make_btn(btn_box, "✏️  Nhập điểm SV", self.enter_grade, bg="#2563EB", width=14).pack(side="left", padx=(0, 8))
        _make_btn(btn_box, "📥  Xuất file CSV", self.export_grades_csv, bg=COLOR_SUCCESS, width=13).pack(side="left", padx=(0, 8))
        _make_btn(btn_box, "🔄  Làm mới", self.load_students, bg="#4B5563", width=10).pack(side="left")

        # Stats summary label on the right
        self.grade_stats_lbl = tk.Label(row2, text="Tổng: 0 SV  |  Đã nhập: 0  |  Chưa nhập: 0  |  Điểm TB: —",
                                        bg="white", font=("Segoe UI", 10, "bold"), fg="#0F6E71")
        self.grade_stats_lbl.pack(side="right", padx=6)

        # Helpful guideline banner
        tip_frame = tk.Frame(container, bg="#EFF6FF", highlightbackground="#BFDBFE",
                             highlightthickness=1, padx=12, pady=8)
        tip_frame.pack(fill="x", pady=(0, 10))
        tk.Label(tip_frame, text="💡 Hướng dẫn:", font=("Segoe UI", 9, "bold"), bg="#EFF6FF", fg="#1D4ED8").pack(side="left", padx=(0, 6))
        tk.Label(tip_frame, text="Chọn sinh viên rồi nhấn 'Nhập điểm SV' (hoặc Nhấp đúp chuột vào hàng) để vào điểm Giữa kỳ & Cuối kỳ (thang điểm 0 - 10).",
                 font=("Segoe UI", 9), bg="#EFF6FF", fg="#1E40AF").pack(side="left")

        # Table Card
        table_card = tk.Frame(container, bg="white", highlightbackground=COLOR_CARD_BD, highlightthickness=1)
        table_card.pack(fill="both", expand=True)

        cols = ("STT", "MSSV", "Họ và tên", "Điểm GK", "Điểm CK", "Điểm TB", "Kết quả")
        tree_frame = tk.Frame(table_card, bg="white", padx=10, pady=10)
        tree_frame.pack(fill="both", expand=True)

        self.grade_tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
        grade_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.grade_tree.yview)
        self.grade_tree.configure(yscrollcommand=grade_scroll.set)

        col_config = {
            "STT": (50, "center"),
            "MSSV": (110, "center"),
            "Họ và tên": (230, "w"),
            "Điểm GK": (110, "center"),
            "Điểm CK": (110, "center"),
            "Điểm TB": (110, "center"),
            "Kết quả": (120, "center"),
        }
        for c in cols:
            width, align = col_config.get(c, (120, "w"))
            self.grade_tree.heading(c, text=c)
            self.grade_tree.column(c, width=width, anchor=align)

        self.grade_tree.pack(side="left", fill="both", expand=True)
        grade_scroll.pack(side="right", fill="y")
        _configure_treeview_tags(self.grade_tree)
        self.grade_tree.bind("<Double-1>", self.enter_grade)

        self._update_section_combo()

    def _update_section_combo(self, event=None):
        sem_sel = self.grade_sem_var.get() if hasattr(self, 'grade_sem_var') else ""
        sem_id = None
        if sem_sel and sem_sel != "Tất cả":
            sem_id = sem_sel.split(" - ")[0]
        sections = db.list_sections(lecturer=self.username, semester_id=sem_id)
        vals = [f"{s['id']} - {s.get('subject_name', '')}" for s in sections]
        self.grade_section_cb['values'] = vals
        self.loaded_section_id = None
        if hasattr(self, 'grade_tree'):
            for item in self.grade_tree.get_children():
                self.grade_tree.delete(item)
            check_empty_treeview(self.grade_tree, "Vui lòng chọn lớp học phần và bấm 'Tải danh sách'")
        if hasattr(self, 'grade_stats_lbl'):
            self.grade_stats_lbl.config(text="Tổng: 0 SV  |  Đã nhập: 0  |  Chưa nhập: 0  |  Điểm TB: —")

    def _section_changed(self, *_):
        self.loaded_section_id = None
        if hasattr(self, 'grade_tree'):
            for item in self.grade_tree.get_children():
                self.grade_tree.delete(item)
            check_empty_treeview(self.grade_tree, "Vui lòng bấm 'Tải danh sách' để xem sinh viên")
        if hasattr(self, 'grade_stats_lbl'):
            self.grade_stats_lbl.config(text="Tổng: 0 SV  |  Đã nhập: 0  |  Chưa nhập: 0  |  Điểm TB: —")

    def load_students(self):
        self.loaded_section_id = None
        for item in self.grade_tree.get_children():
            self.grade_tree.delete(item)

        sec_sel = self.section_var.get()
        if not sec_sel:
            messagebox.showinfo("Thông báo", "Vui lòng chọn một lớp học phần trong danh sách."); return
        section_id = sec_sel.split(" - ")[0]

        try:
            section = db.get_section(section_id)
            if not section or section['lecturer'] != self.username:
                raise ValueError("Bạn không được phân công lớp học phần này.")
            rows = db.get_section_students_with_grades(section_id)
        except Exception as exc:
            messagebox.showerror("Lỗi", str(exc)); return

        completed_count = 0
        total_avg_sum = 0.0
        for i, row in enumerate(rows):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            mid = row['midterm']
            fin = row['final_score']

            mid_disp = f"{float(mid):.1f}" if mid is not None else "—"
            fin_disp = f"{float(fin):.1f}" if fin is not None else "—"

            if mid is not None and fin is not None:
                completed_count += 1
                avg = round((float(mid) + float(fin)) / 2, 1)
                total_avg_sum += avg
                avg_disp = f"{avg:.1f}"
                status = "✅ Đạt" if avg >= 4.0 else "❌ Chưa đạt"
            elif mid is not None or fin is not None:
                avg_disp = "—"
                status = "⏳ Thiếu điểm"
            else:
                avg_disp = "—"
                status = "Chưa nhập"

            st_name = row.get('student_name') or "Chưa cập nhật"
            self.grade_tree.insert("", "end", values=(
                i + 1,
                row['mssv'],
                st_name,
                mid_disp,
                fin_disp,
                avg_disp,
                status
            ), tags=(tag,))

        self.loaded_section_id = section_id
        check_empty_treeview(self.grade_tree, "Lớp học phần này chưa có sinh viên đăng ký")

        total_sv = len(rows)
        unentered = total_sv - completed_count
        overall_avg = f"{(total_avg_sum / completed_count):.1f}" if completed_count > 0 else "—"
        if hasattr(self, 'grade_stats_lbl'):
            self.grade_stats_lbl.config(
                text=f"Tổng: {total_sv} SV  |  Đã nhập: {completed_count}  |  Chưa đủ điểm: {unentered}  |  Điểm TB lớp: {overall_avg}"
            )

    def enter_grade(self, event=None):
        item = self.grade_tree.selection()
        if not item:
            messagebox.showinfo("Thông báo", "Vui lòng chọn một sinh viên trong danh sách để nhập điểm.")
            return

        vals = self.grade_tree.item(item[0])['values']
        if not vals or len(vals) < 3 or any(k in str(vals[0]) for k in ("Chưa", "Vui lòng", "Lớp")):
            return

        section_id = self.loaded_section_id
        current_sel = self.section_var.get().split(" - ")[0] if self.section_var.get() else ""
        if not section_id or section_id != current_sel:
            messagebox.showerror("Danh sách đã thay đổi",
                                 "Vui lòng tải lại danh sách sinh viên trước khi nhập điểm.")
            return

        mssv = str(vals[1])
        st_name = mssv if str(vals[2]) in ("Chưa cập nhật", "None", "") else str(vals[2])

        curr_mid = None
        curr_fin = None
        try:
            if str(vals[3]) not in ("—", "", "None"):
                curr_mid = float(vals[3])
            if str(vals[4]) not in ("—", "", "None"):
                curr_fin = float(vals[4])
        except (ValueError, TypeError):
            pass

        midterm = simpledialog.askfloat(
            "Nhập điểm Giữa kỳ",
            f"Điểm giữa kỳ cho {st_name} ({mssv})\nLớp: {section_id} (thang điểm 0 - 10):",
            minvalue=0, maxvalue=10, initialvalue=curr_mid
        )
        if midterm is None:
            return

        final = simpledialog.askfloat(
            "Nhập điểm Cuối kỳ",
            f"Điểm cuối kỳ cho {st_name} ({mssv})\nLớp: {section_id} (thang điểm 0 - 10):",
            minvalue=0, maxvalue=10, initialvalue=curr_fin
        )
        if final is None:
            return

        current_sel = self.section_var.get().split(" - ")[0] if self.section_var.get() else ""
        if self.loaded_section_id != section_id or current_sel != section_id:
            messagebox.showerror("Danh sách đã thay đổi", "Lớp học phần đã thay đổi; vui lòng nhập lại.")
            return

        try:
            services.set_grade(db, mssv, section_id, midterm, final,
                               lecturer_username=self.username)
        except Exception as exc:
            messagebox.showerror("Không thể lưu điểm", str(exc))
            return

        self.load_students()
        messagebox.showinfo("Thành công", f"Đã lưu điểm cho sinh viên {st_name} ({mssv})!")

    def export_grades_csv(self):
        if not self.loaded_section_id:
            messagebox.showinfo("Thông báo", "Vui lòng chọn và tải danh sách lớp học phần trước khi xuất file.")
            return

        children = self.grade_tree.get_children()
        if not children:
            messagebox.showinfo("Thông báo", "Không có dữ liệu sinh viên để xuất.")
            return

        first_vals = self.grade_tree.item(children[0])['values']
        if not first_vals or any(k in str(first_vals[0]) for k in ("Chưa", "Vui lòng", "Lớp")):
            messagebox.showinfo("Thông báo", "Không có dữ liệu sinh viên hợp lệ để xuất.")
            return

        default_filename = f"BangDiem_{self.loaded_section_id}_{datetime.now().strftime('%Y%m%d')}.csv"
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=default_filename,
            filetypes=[("CSV file (*.csv)", "*.csv"), ("Tất cả tập tin (*.*)", "*.*")],
            title="Xuất bảng điểm lớp học phần"
        )
        if not file_path:
            return

        try:
            with open(file_path, mode="w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["STT", "MSSV", "Họ và tên", "Điểm GK", "Điểm CK", "Điểm TB", "Kết quả"])
                for item in children:
                    vals = self.grade_tree.item(item)['values']
                    writer.writerow(vals)
            messagebox.showinfo("Thành công", f"Đã xuất bảng điểm thành công!\nĐường dẫn: {file_path}")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể xuất file: {e}")


# START APP
if __name__ == "__main__":
    LoginWindow()
