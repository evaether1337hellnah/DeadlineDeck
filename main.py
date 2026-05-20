import json
import os
import hashlib
import secrets
import base64
import re
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    from PIL import Image, ImageTk
    PIL_OK = True
except ImportError:
    PIL_OK = False

#настройки программы
TASK_STATUSES = ["Не начато", "В процессе", "Готово"]
TASK_PRIORITIES = ["Низкий", "Средний", "Высокий"]
SORT_TYPES = ["Без сортировки", "Дедлайн ближе", "Дедлайн дальше", "Приоритет высокий", "Приоритет низкий", "Статус", "Предмет", "Название"]
ACCOUNTS_FILE = "accounts.json"
SETTINGS_FILE = "settings.json"
LOGO_FILE = "logo.png"
SPLASH_TIME = 2000
HASH_ITERATIONS = 120000

#цвета интерфейса
LIGHT_THEME = {"bg": "#f6f7fb", "panel": "#ffffff", "text": "#1f2937", "muted": "#6b7280", "accent": "#6366f1", "entry": "#ffffff", "table": "#ffffff"}
DARK_THEME = {"bg": "#0f172a", "panel": "#1e3a5f", "text": "#ffffff", "muted": "#dbeafe", "accent": "#93c5fd", "entry": "#27466f", "table": "#111827"}


class Task:
    #класс хранит одно учебное задание
    def __init__(self, title, subject, deadline, priority, status, description):
        self.title = title
        self.subject = subject
        self.deadline = deadline
        self.priority = priority
        self.status = status
        self.description = description

    def to_dict(self):
        #переводим объект в словарь для json
        return self.__dict__

    @staticmethod
    def from_dict(data):
        #создаем объект из словаря
        return Task(
            data.get("title", ""),
            data.get("subject", ""),
            data.get("deadline", "Не указан"),
            data.get("priority", "Средний"),
            data.get("status", "Не начато"),
            data.get("description", ""),
        )


class UserManager:
    #класс отвечает за пользователей
    def __init__(self):
        self.users = self.load_users()

    def load_users(self):
        #загружаем аккаунты
        if not os.path.exists(ACCOUNTS_FILE):
            return {}
        try:
            with open(ACCOUNTS_FILE, "r", encoding="utf-8") as file:
                return json.load(file)
        except json.JSONDecodeError:
            return {}

    def save_users(self):
        #сохраняем аккаунты
        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as file:
            json.dump(self.users, file, ensure_ascii=False, indent=4)

    def make_hash(self, password, salt, iterations=HASH_ITERATIONS):
        #создаем хеш пароля
        return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()

    def make_key(self, password, salt, iterations=HASH_ITERATIONS):
        #создаем ключ для шифрования задач
        return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations)

    def check_login(self, login):
        #проверяем формат логина
        return bool(re.fullmatch(r"[A-Za-zА-Яа-я0-9_]{3,20}", login.strip()))

    def register(self, login, password):
        #создаем нового пользователя
        login = login.strip()
        if not self.check_login(login):
            return False, "Логин: 3-20 символов, буквы/цифры/_."
        if len(password) < 4:
            return False, "Пароль слишком короткий: минимум 4 символа."
        if login in self.users:
            return False, "Такой пользователь уже есть. Нажми Войти."

        salt = secrets.token_hex(16)
        self.users[login] = {"salt": salt, "password_hash": self.make_hash(password, salt)}
        self.save_users()
        return True, "Аккаунт создан. Теперь можно войти."

    def login(self, login, password):
        #проверяем вход пользователя
        login = login.strip()
        if login == "" or password == "":
            return False, "Введите логин и пароль.", None
        if login not in self.users:
            return False, "Пользователь не найден. Можно создать аккаунт.", None

        salt = self.users[login]["salt"]
        saved_hash = self.users[login]["password_hash"]

        #100000 оставлено для старых тестовых аккаунтов
        for iterations in [HASH_ITERATIONS, 100000]:
            if self.make_hash(password, salt, iterations) == saved_hash:
                return True, "Вход выполнен.", self.make_key(password, salt, iterations)
        return False, "Неверный пароль.", None


class TaskStorage:
    #класс сохраняет задания в зашифрованный json
    def __init__(self, login, key):
        self.key = key
        self.filename = "tasks_" + login + ".json"

    def key_stream(self, length):
        #создаем поток байтов для шифрования
        result = b""
        number = 0
        while len(result) < length:
            result += hashlib.sha256(self.key + number.to_bytes(4, "big")).digest()
            number += 1
        return result[:length]

    def crypt(self, data):
        #xor работает и на шифрование, и на расшифровку
        stream = self.key_stream(len(data))
        return bytes(data[i] ^ stream[i] for i in range(len(data)))

    def encrypt(self, text):
        #делаем текст нечитаемым
        return base64.b64encode(self.crypt(text.encode("utf-8"))).decode("utf-8")

    def decrypt(self, text):
        #возвращаем исходный текст
        return self.crypt(base64.b64decode(text.encode("utf-8"))).decode("utf-8")

    def load_tasks(self):
        #загружаем задания пользователя
        if not os.path.exists(self.filename):
            return []
        try:
            with open(self.filename, "r", encoding="utf-8") as file:
                data = json.load(file)
            if isinstance(data, dict) and data.get("encrypted"):
                data = json.loads(self.decrypt(data["data"]))
            return [Task.from_dict(item) for item in data]
        except Exception:
            messagebox.showerror("Ошибка", "Не удалось открыть файл с заданиями.")
            return []

    def save_tasks(self, tasks):
        #сохраняем задания пользователя
        text = json.dumps([task.to_dict() for task in tasks], ensure_ascii=False)
        data = {"encrypted": True, "data": self.encrypt(text)}
        with open(self.filename, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)


class TaskManager:
    #класс управляет списком заданий
    def __init__(self, storage):
        self.storage = storage
        self.tasks = self.storage.load_tasks()

    def save(self):
        self.storage.save_tasks(self.tasks)

    def add(self, task):
        self.tasks.append(task)
        self.save()

    def delete(self, index):
        if 0 <= index < len(self.tasks):
            self.tasks.pop(index)
            self.save()

    def update(self, index, task):
        if 0 <= index < len(self.tasks):
            self.tasks[index] = task
            self.save()

    def change_status(self, index, status):
        if 0 <= index < len(self.tasks):
            self.tasks[index].status = status
            self.save()

    def parse_date(self, text):
        #переводим дату из строки в объект даты
        try:
            return datetime.strptime(text, "%d.%m.%Y")
        except ValueError:
            return None

    def date_key(self, task, reverse=False):
        #задания без даты отправляются в конец списка
        date = self.parse_date(task.deadline)
        if date:
            return date
        return datetime.min if reverse else datetime.max

    def search(self, text, status, sort_type="Без сортировки"):
        #ищем, фильтруем и сортируем задания
        text = text.lower().strip()
        result = []
        for index, task in enumerate(self.tasks):
            has_text = text in task.title.lower() or text in task.subject.lower() or text in task.description.lower()
            has_status = status == "Все" or task.status == status
            if has_text and has_status:
                result.append((index, task))

        priority = {"Высокий": 0, "Средний": 1, "Низкий": 2}
        status_order = {"Не начато": 0, "В процессе": 1, "Готово": 2}

        if sort_type == "Дедлайн ближе":
            result.sort(key=lambda item: self.date_key(item[1]))
        elif sort_type == "Дедлайн дальше":
            result.sort(key=lambda item: self.date_key(item[1], True), reverse=True)
        elif sort_type == "Приоритет высокий":
            result.sort(key=lambda item: priority.get(item[1].priority, 9))
        elif sort_type == "Приоритет низкий":
            result.sort(key=lambda item: priority.get(item[1].priority, 9), reverse=True)
        elif sort_type == "Статус":
            result.sort(key=lambda item: status_order.get(item[1].status, 9))
        elif sort_type == "Предмет":
            result.sort(key=lambda item: item[1].subject.lower())
        elif sort_type == "Название":
            result.sort(key=lambda item: item[1].title.lower())

        return result


class RoundButton(tk.Canvas):
    #простая округлая кнопка
    def __init__(self, parent, text, command, colors, width=120, height=34, accent=False):
        super().__init__(parent, width=width, height=height, highlightthickness=0, bd=0, bg=colors["bg"])
        self.text = text
        self.command = command
        self.colors = colors
        self.width = width
        self.height = height
        self.accent = accent
        self.draw()
        self.bind("<Button-1>", lambda event: self.command())
        self.bind("<Enter>", lambda event: self.config(cursor="hand2"))

    def draw(self):
        #рисуем кнопку вручную
        self.delete("all")
        bg = self.colors["accent"] if self.accent else self.colors["panel"]
        fg = "#ffffff" if self.accent else self.colors["text"]
        r, x1, y1, x2, y2 = 14, 2, 2, self.width - 2, self.height - 2
        points = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r, x2,y2-r, x2,y2, x2-r,y2, x1+r,y2, x1,y2, x1,y2-r, x1,y1+r, x1,y1]
        self.create_polygon(points, smooth=True, fill=bg, outline=bg)
        self.create_text(self.width // 2, self.height // 2, text=self.text, fill=fg, font=("Arial", 10, "bold" if self.accent else "normal"))


class LoginWindow:
    #окно входа и регистрации
    def __init__(self, root, open_main_app):
        self.root = root
        self.open_main_app = open_main_app
        self.user_manager = UserManager()
        self.colors = DARK_THEME
        self.window = tk.Toplevel(root)
        self.window.title("Deadline Deck - вход")
        self.window.geometry("380x320")
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", root.destroy)
        self.create_widgets()

    def label(self, parent, text, size=10, color="text", bold=False):
        #создаем текстовую подпись
        font = ("Arial", size, "bold") if bold else ("Arial", size)
        return tk.Label(parent, text=text, bg=self.colors["bg"], fg=self.colors[color], font=font)

    def entry(self, parent, show=None):
        #создаем поле ввода с цветами окна входа
        return tk.Entry(parent, show=show, bg=self.colors["entry"], fg=self.colors["text"], insertbackground=self.colors["text"], relief=tk.FLAT)

    def create_widgets(self):
        #собираем окно входа
        self.window.configure(bg=self.colors["bg"])
        frame = tk.Frame(self.window, bg=self.colors["bg"], padx=28, pady=26)
        frame.pack(fill=tk.BOTH, expand=True)

        self.label(frame, "Deadline Deck", 22, "accent", True).pack(anchor=tk.W)
        self.label(frame, "вход или создание учетной записи", color="muted").pack(anchor=tk.W, pady=(0, 18))

        self.label(frame, "Логин:").pack(anchor=tk.W)
        self.login_entry = self.entry(frame)
        self.login_entry.pack(fill=tk.X, pady=(3, 10), ipady=4)

        self.label(frame, "Пароль:").pack(anchor=tk.W)
        self.password_entry = self.entry(frame, show="*")
        self.password_entry.pack(fill=tk.X, pady=(3, 15), ipady=4)

        buttons = tk.Frame(frame, bg=self.colors["bg"])
        buttons.pack(fill=tk.X)
        RoundButton(buttons, "Войти", self.login, self.colors, 105, accent=True).pack(side=tk.LEFT, padx=(0, 8))
        RoundButton(buttons, "Создать", self.register, self.colors, 105).pack(side=tk.LEFT)

        self.info_label = self.label(frame, "Введите логин и пароль.", color="muted")
        self.info_label.pack(anchor=tk.W, pady=(15, 0))

        self.login_entry.bind("<KeyRelease>", self.check_input)
        self.password_entry.bind("<KeyRelease>", self.check_input)
        self.window.bind("<Return>", lambda event: self.login())
        self.login_entry.focus()

    def get_data(self):
        #берем данные из полей
        return self.login_entry.get().strip(), self.password_entry.get()

    def check_input(self, event=None):
        #показываем подсказки во время ввода
        login, password = self.get_data()
        if login == "":
            text = "Введите логин."
        elif len(login) < 3:
            text = "Логин слишком короткий: минимум 3 символа."
        elif not re.fullmatch(r"[A-Za-zА-Яа-я0-9_]*", login):
            text = "В логине можно буквы, цифры и _."
        elif password == "":
            text = "Введите пароль."
        elif len(password) < 4:
            text = "Пароль слишком короткий: минимум 4 символа."
        elif login in self.user_manager.users:
            text = "Аккаунт найден. Можно войти."
        else:
            text = "Аккаунта нет. Можно создать."
        self.info_label.config(text=text)

    def register(self):
        #создаем аккаунт
        ok, message = self.user_manager.register(*self.get_data())
        self.info_label.config(text=message)

    def login(self):
        #входим в аккаунт
        login, password = self.get_data()
        ok, message, key = self.user_manager.login(login, password)
        if ok:
            self.window.destroy()
            self.open_main_app(login, key)
        else:
            self.info_label.config(text=message)


class App:
    #главное окно программы
    def __init__(self, root, login, key):
        self.root = root
        self.login = login
        self.key = key
        self.theme = self.load_theme()
        self.visible_indexes = []
        self.current_tasks = []
        self.root.title("Deadline Deck - " + login)
        self.root.geometry("1050x650")
        self.root.minsize(900, 560)
        self.manager = TaskManager(TaskStorage(login, key))
        self.set_style()
        self.create_widgets()
        self.refresh_table()

    def load_theme(self):
        #загружаем тему
        if not os.path.exists(SETTINGS_FILE):
            return "light"
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as file:
                return json.load(file).get("theme", "light")
        except json.JSONDecodeError:
            return "light"

    def save_theme(self):
        #сохраняем тему
        with open(SETTINGS_FILE, "w", encoding="utf-8") as file:
            json.dump({"theme": self.theme}, file, ensure_ascii=False, indent=4)

    def colors(self):
        #возвращаем цвета темы
        return DARK_THEME if self.theme == "dark" else LIGHT_THEME

    def set_style(self):
        #настраиваем цвета стандартных элементов
        color = self.colors()
        self.root.configure(bg=color["bg"])
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=color["bg"])
        style.configure("TLabel", background=color["bg"], foreground=color["text"], font=("Arial", 10))
        style.configure("TLabelframe", background=color["panel"], foreground=color["text"], bordercolor=color["panel"], lightcolor=color["panel"], darkcolor=color["panel"])
        style.configure("TLabelframe.Label", background=color["panel"], foreground=color["text"], font=("Arial", 10, "bold"))
        style.configure("TEntry", fieldbackground=color["entry"], foreground=color["text"], insertcolor=color["text"], bordercolor=color["accent"])
        style.configure("TCombobox", fieldbackground=color["entry"], background=color["entry"], foreground=color["text"], arrowcolor=color["text"], bordercolor=color["accent"])
        style.map("TCombobox", fieldbackground=[("readonly", color["entry"])], foreground=[("readonly", color["text"])], background=[("readonly", color["entry"])])
        style.configure("Treeview", background=color["table"], fieldbackground=color["table"], foreground=color["text"], rowheight=28, bordercolor=color["accent"])
        style.configure("Treeview.Heading", background=color["entry"], foreground=color["text"], font=("Arial", 10, "bold"))
        style.map("Treeview", background=[("selected", color["accent"])], foreground=[("selected", "#ffffff")])
        self.root.option_add("*TCombobox*Listbox.background", color["entry"])
        self.root.option_add("*TCombobox*Listbox.foreground", color["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", color["accent"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

    def round_button(self, parent, text, command, width=120, accent=False):
        #создаем округлую кнопку
        return RoundButton(parent, text, command, self.colors(), width=width, accent=accent)

    def add_label_entry(self, parent, text, row, col, width):
        #создаем подпись и поле ввода
        ttk.Label(parent, text=text).grid(row=row, column=col, sticky=tk.W, padx=5, pady=5)
        entry = ttk.Entry(parent, width=width)
        entry.grid(row=row, column=col + 1, padx=5, pady=5)
        return entry

    def add_label_box(self, parent, text, row, col, values, width):
        #создаем подпись и список
        ttk.Label(parent, text=text).grid(row=row, column=col, sticky=tk.W, padx=5, pady=5)
        box = ttk.Combobox(parent, values=values, state="readonly", width=width)
        box.grid(row=row, column=col + 1, padx=5, pady=5)
        box.set(values[0])
        return box

    def create_widgets(self):
        #создаем элементы главного окна
        color = self.colors()
        main = ttk.Frame(self.root, padding=15)
        main.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(main)
        top.pack(fill=tk.X, pady=(0, 10))
        title_box = ttk.Frame(top)
        title_box.pack(side=tk.LEFT)
        ttk.Label(title_box, text="Deadline Deck", font=("Arial", 20, "bold"), foreground=color["accent"]).pack(anchor=tk.W)
        ttk.Label(title_box, text="Пользователь: " + self.login).pack(anchor=tk.W)
        self.round_button(top, "Выйти", self.logout, 90).pack(side=tk.RIGHT, padx=(8, 0))
        self.round_button(top, "Светлая / темная", self.change_theme, 150).pack(side=tk.RIGHT)

        form = ttk.LabelFrame(main, text="Данные задания", padding=12)
        form.pack(fill=tk.X)
        self.title_entry = self.add_label_entry(form, "Название:", 0, 0, 35)
        self.subject_entry = self.add_label_entry(form, "Предмет:", 0, 2, 25)
        self.deadline_entry = self.add_label_entry(form, "Дедлайн:", 0, 4, 18)
        self.deadline_entry.insert(0, "дд.мм.гггг")
        self.deadline_entry.bind("<FocusIn>", self.clear_deadline_hint)
        self.deadline_entry.bind("<FocusOut>", self.return_deadline_hint)
        self.deadline_entry.bind("<KeyRelease>", self.format_deadline)
        self.priority_box = self.add_label_box(form, "Приоритет:", 1, 0, TASK_PRIORITIES, 32)
        self.status_box = self.add_label_box(form, "Статус:", 1, 2, TASK_STATUSES, 22)

        ttk.Label(form, text="Описание:").grid(row=2, column=0, sticky=tk.NW, padx=5, pady=5)
        self.description_text = tk.Text(form, height=3, width=80, bg=color["entry"], fg=color["text"], insertbackground=color["text"])
        self.description_text.grid(row=2, column=1, columnspan=5, sticky=tk.W, padx=5, pady=5)

        buttons = ttk.Frame(main)
        buttons.pack(fill=tk.X, pady=12)
        actions = [("Добавить", self.add_task, 110, True), ("Обновить", self.update_task, 110, False), ("Удалить", self.delete_task, 100, False), ("В процессе", lambda: self.set_status("В процессе"), 120, False), ("Готово", lambda: self.set_status("Готово"), 95, False), ("Очистить", self.clear_form, 105, False), ("Экспорт Excel", self.export_excel, 130, False)]
        for text, command, width, accent in actions:
            self.round_button(buttons, text, command, width, accent).pack(side=tk.LEFT, padx=4)

        search_frame = ttk.LabelFrame(main, text="Поиск, фильтр и сортировка", padding=10)
        search_frame.pack(fill=tk.X)
        ttk.Label(search_frame, text="Поиск:").pack(side=tk.LEFT, padx=5)
        self.search_entry = ttk.Entry(search_frame, width=28)
        self.search_entry.pack(side=tk.LEFT, padx=5)
        self.search_entry.bind("<KeyRelease>", lambda event: self.refresh_table())
        self.filter_box = self.add_pack_box(search_frame, "Статус:", ["Все"] + TASK_STATUSES, "Все", 16)
        self.sort_box = self.add_pack_box(search_frame, "Сортировка:", SORT_TYPES, "Без сортировки", 20)
        self.round_button(search_frame, "Сбросить", self.reset_filter, 100).pack(side=tk.LEFT, padx=5)

        self.create_table(main)
        self.info_label = ttk.Label(main, text="")
        self.info_label.pack(anchor=tk.W)

    def add_pack_box(self, parent, text, values, default, width):
        #создаем список в строке поиска
        ttk.Label(parent, text=text).pack(side=tk.LEFT, padx=5)
        box = ttk.Combobox(parent, values=values, state="readonly", width=width)
        box.pack(side=tk.LEFT, padx=5)
        box.set(default)
        box.bind("<<ComboboxSelected>>", lambda event: self.refresh_table())
        return box

    def create_table(self, parent):
        #создаем таблицу заданий
        table_frame = ttk.Frame(parent)
        table_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        columns = ("title", "subject", "deadline", "priority", "status", "description")
        names = ("Название", "Предмет", "Дедлайн", "Приоритет", "Статус", "Описание")
        widths = (180, 130, 100, 90, 110, 330)
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings")
        for column, name, width in zip(columns, names, widths):
            self.table.heading(column, text=name)
            self.table.column(column, width=width)
        scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.table.bind("<<TreeviewSelect>>", self.put_selected_to_form)

    def get_task_from_form(self):
        #создаем задание из формы
        title = self.title_entry.get().strip()
        subject = self.subject_entry.get().strip() or "Без предмета"
        deadline = self.deadline_entry.get().strip()
        description = self.description_text.get("1.0", tk.END).strip()
        if title == "":
            messagebox.showerror("Ошибка", "Введите название задания.")
            return None
        if deadline == "" or deadline == "дд.мм.гггг":
            deadline = "Не указан"
        return Task(title, subject, deadline, self.priority_box.get(), self.status_box.get(), description)

    def selected_index(self):
        #получаем индекс выбранной строки
        selected = self.table.selection()
        return None if not selected else self.visible_indexes[int(selected[0])]

    def add_task(self):
        #добавляем задание
        task = self.get_task_from_form()
        if task:
            self.manager.add(task)
            self.clear_form()
            self.refresh_table()

    def update_task(self):
        #обновляем задание
        index = self.selected_index()
        task = self.get_task_from_form()
        if index is None:
            messagebox.showwarning("Ошибка", "Выберите задание.")
        elif task:
            self.manager.update(index, task)
            self.refresh_table()

    def delete_task(self):
        #удаляем задание
        index = self.selected_index()
        if index is None:
            messagebox.showwarning("Ошибка", "Выберите задание.")
        elif messagebox.askyesno("Удаление", "Удалить выбранное задание?"):
            self.manager.delete(index)
            self.clear_form()
            self.refresh_table()

    def set_status(self, status):
        #меняем статус
        index = self.selected_index()
        if index is None:
            messagebox.showwarning("Ошибка", "Выберите задание.")
        else:
            self.manager.change_status(index, status)
            self.refresh_table()

    def put_selected_to_form(self, event=None):
        #переносим выбранную строку в форму
        index = self.selected_index()
        if index is None:
            return
        task = self.manager.tasks[index]
        self.clear_form()
        self.title_entry.insert(0, task.title)
        self.subject_entry.insert(0, task.subject)
        self.deadline_entry.insert(0, task.deadline)
        self.priority_box.set(task.priority)
        self.status_box.set(task.status)
        self.description_text.insert("1.0", task.description)

    def refresh_table(self):
        #обновляем таблицу
        for item in self.table.get_children():
            self.table.delete(item)
        self.current_tasks = self.manager.search(self.search_entry.get(), self.filter_box.get(), self.sort_box.get())
        self.visible_indexes = []
        for visible_index, (real_index, task) in enumerate(self.current_tasks):
            self.visible_indexes.append(real_index)
            self.table.insert("", tk.END, iid=str(visible_index), values=(task.title, task.subject, task.deadline, task.priority, task.status, task.description))
        total = len(self.manager.tasks)
        done = sum(1 for task in self.manager.tasks if task.status == "Готово")
        self.info_label.config(text=f"Всего заданий: {total} | Выполнено: {done} | Показано: {len(self.current_tasks)}")

    def export_excel(self):
        #экспортируем текущую таблицу в excel
        try:
            from openpyxl import Workbook
        except ImportError:
            messagebox.showerror("Ошибка", "Для экспорта установи openpyxl:\npython -m pip install openpyxl")
            return
        if not self.current_tasks:
            messagebox.showinfo("Экспорт", "Нет заданий для экспорта.")
            return
        filename = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel файл", "*.xlsx")], initialfile="tasks_" + self.login + ".xlsx")
        if not filename:
            return
        book = Workbook()
        sheet = book.active
        sheet.title = "Задания"
        sheet.append(["Название", "Предмет", "Дедлайн", "Приоритет", "Статус", "Описание"])
        for _, task in self.current_tasks:
            sheet.append([task.title, task.subject, task.deadline, task.priority, task.status, task.description])
        for column, width in zip(["A", "B", "C", "D", "E", "F"], [25, 20, 14, 14, 16, 45]):
            sheet.column_dimensions[column].width = width
        book.save(filename)
        messagebox.showinfo("Экспорт", "Файл Excel сохранен.")

    def clear_form(self):
        #очищаем форму
        for entry in [self.title_entry, self.subject_entry, self.deadline_entry]:
            entry.delete(0, tk.END)
        self.deadline_entry.insert(0, "дд.мм.гггг")
        self.priority_box.set("Средний")
        self.status_box.set("Не начато")
        self.description_text.delete("1.0", tk.END)

    def reset_filter(self):
        #сбрасываем поиск, фильтр и сортировку
        self.search_entry.delete(0, tk.END)
        self.filter_box.set("Все")
        self.sort_box.set("Без сортировки")
        self.refresh_table()

    def clear_deadline_hint(self, event=None):
        #убираем подсказку даты
        if self.deadline_entry.get() == "дд.мм.гггг":
            self.deadline_entry.delete(0, tk.END)

    def return_deadline_hint(self, event=None):
        #возвращаем подсказку даты
        if self.deadline_entry.get().strip() == "":
            self.deadline_entry.insert(0, "дд.мм.гггг")

    def format_deadline(self, event=None):
        #ставим точки в дате автоматически
        if event.keysym in ["BackSpace", "Delete", "Left", "Right", "Tab"]:
            return
        digits = "".join(symbol for symbol in self.deadline_entry.get() if symbol.isdigit())[:8]
        if len(digits) <= 2:
            result = digits
        elif len(digits) <= 4:
            result = digits[:2] + "." + digits[2:]
        else:
            result = digits[:2] + "." + digits[2:4] + "." + digits[4:]
        self.deadline_entry.delete(0, tk.END)
        self.deadline_entry.insert(0, result)
        self.deadline_entry.icursor(tk.END)

    def change_theme(self):
        #переключаем тему
        self.theme = "dark" if self.theme == "light" else "light"
        self.save_theme()
        self.manager.save()
        self.restart_window()

    def logout(self):
        #выходим из аккаунта
        if messagebox.askyesno("Выход", "Выйти из аккаунта?"):
            self.manager.save()
            self.restart_to_login()

    def restart_window(self):
        #пересоздаем главное окно
        for widget in self.root.winfo_children():
            widget.destroy()
        App(self.root, self.login, self.key)

    def restart_to_login(self):
        #возвращаемся ко входу
        for widget in self.root.winfo_children():
            widget.destroy()
        self.root.withdraw()
        LoginWindow(self.root, open_main_app)


class SplashScreen:
    #заставка при запуске
    def __init__(self, root):
        self.logo = None
        self.window = tk.Toplevel(root)
        self.window.overrideredirect(True)
        self.window.configure(bg="#111827")
        self.create_widgets()

    def create_widgets(self):
        #создаем заставку
        width, height = 500, 400
        x = (self.window.winfo_screenwidth() - width) // 2
        y = (self.window.winfo_screenheight() - height) // 2
        self.window.geometry(f"{width}x{height}+{x}+{y}")
        frame = tk.Frame(self.window, bg="#111827")
        frame.pack(fill=tk.BOTH, expand=True)

        if os.path.exists(LOGO_FILE):
            self.logo = self.load_logo()
            if self.logo:
                tk.Label(frame, image=self.logo, bg="#111827").pack(pady=(35, 10))
        tk.Label(frame, text="Deadline Deck", bg="#111827", fg="#93c5fd", font=("Arial", 24, "bold")).pack()
        tk.Label(frame, text="учебные задания под контролем", bg="#111827", fg="#e5e7eb", font=("Arial", 11)).pack(pady=(5, 0))

    def load_logo(self):
        #загружаем логотип
        try:
            if PIL_OK:
                image = Image.open(LOGO_FILE)
                image.thumbnail((270, 270))
                return ImageTk.PhotoImage(image)
            return tk.PhotoImage(file=LOGO_FILE)
        except Exception:
            return None

    def close(self):
        #закрываем заставку
        self.window.destroy()


#точка запуска программы
def open_main_app(login, key):
    root.deiconify()
    App(root, login, key)


def open_login():
    splash.close()
    LoginWindow(root, open_main_app)


root = tk.Tk()
root.withdraw()
splash = SplashScreen(root)
root.after(SPLASH_TIME, open_login)
root.mainloop()
