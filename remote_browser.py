"""Read-only SFTP directory browser."""
import base64
import hashlib
import os
import posixpath
import stat
import sys
import threading
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import paramiko

def format_size(size):
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size < 1024 or unit == 'TB':
            return f'{size} B' if unit == 'B' else f'{size:.1f} {unit}'
        size /= 1024

def parent_path(path):
    return posixpath.dirname(path.rstrip('/')) or '/'

class ConfirmHostKey(paramiko.MissingHostKeyPolicy):
    def __init__(self, root):
        self.root = root

    def missing_host_key(self, client, hostname, key):
        fingerprint = base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')
        done = threading.Event()
        answer = [False]
        def ask():
            try:
                answer[0] = messagebox.askyesno('确认服务器身份', f'首次连接 {hostname}。\n\n密钥类型：{key.get_name()}\nSHA256:{fingerprint}\n\n请通过可信渠道核对指纹，确认匹配后再继续。\n本次确认仅对当前连接有效。', parent=self.root)
            finally:
                done.set()
        self.root.after(0, ask)
        done.wait()
        if not answer[0]:
            raise paramiko.SSHException('未确认服务器密钥。')

class Browser:
    def __init__(self, root):
        self.root = root
        self.client = None
        self.sftp = None
        self.path = '.'
        root.title('服务器目录浏览器 — 只读')
        root.geometry('1040x680')
        root.minsize(720, 420)
        root.configure(background='#101216')
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('.', background='#101216', foreground='#e8ebf0', font=('Microsoft YaHei UI', 10))
        style.configure('TFrame', background='#101216')
        style.configure('Title.TLabel', background='#101216', foreground='#f5f7fa', font=('Microsoft YaHei UI', 18, 'bold'))
        style.configure('Muted.TLabel', background='#101216', foreground='#929ba9', font=('Microsoft YaHei UI', 9))
        style.configure('TButton', background='#252b35', foreground='#e8ebf0', borderwidth=0, padding=(14, 8))
        style.map('TButton', background=[('active', '#374151'), ('pressed', '#1d232c')])
        style.configure('Accent.TButton', background='#397be8', foreground='#ffffff', padding=(16, 8))
        style.map('Accent.TButton', background=[('active', '#528ff0'), ('pressed', '#2865c7')])
        style.configure('TEntry', fieldbackground='#1c2129', foreground='#f0f2f6', insertcolor='#ffffff', bordercolor='#343c49', lightcolor='#343c49', darkcolor='#343c49', padding=8)
        style.configure('Treeview', background='#171b22', fieldbackground='#171b22', foreground='#e2e7ee', rowheight=34, borderwidth=0, font=('Microsoft YaHei UI', 10))
        style.map('Treeview', background=[('selected', '#29466d')], foreground=[('selected', '#ffffff')])
        style.configure('Treeview.Heading', background='#222832', foreground='#aeb8c7', borderwidth=0, relief='flat', padding=(10, 10), font=('Microsoft YaHei UI', 9, 'bold'))
        style.map('Treeview.Heading', background=[('active', '#2b3441')])
        header = ttk.Frame(root, padding=(20, 20, 20, 4))
        header.pack(fill='x')
        ttk.Label(header, text='服务器文件', style='Title.TLabel').pack(anchor='w')
        ttk.Label(header, text='SFTP  ·  只读浏览', style='Muted.TLabel').pack(anchor='w', pady=(4, 0))
        connection = ttk.Frame(root, padding=(20, 12, 20, 0))
        connection.pack(fill='x')
        self.host = tk.StringVar()
        self.port = tk.StringVar(value='22')
        self.username = tk.StringVar()
        for label, value, width in (('服务器 IP / 域名', self.host, 26), ('端口', self.port, 7), ('用户名', self.username, 18)):
            ttk.Label(connection, text=label, style='Muted.TLabel').pack(side='left', padx=(0, 6))
            ttk.Entry(connection, textvariable=value, width=width).pack(side='left', padx=(0, 14))
        bar = ttk.Frame(root, padding=(20, 18, 20, 14))
        bar.pack(fill='x')
        ttk.Button(bar, text='连接服务器', style='Accent.TButton', command=self.connect).pack(side='left')
        ttk.Button(bar, text='上一级', command=lambda: self.load(parent_path(self.path))).pack(side='left', padx=4)
        ttk.Button(bar, text='刷新', command=lambda: self.load(self.path)).pack(side='left')
        self.address = tk.StringVar(value=self.path)
        entry = ttk.Entry(bar, textvariable=self.address)
        entry.pack(side='left', fill='x', expand=True, padx=8)
        entry.bind('<Return>', lambda _: self.load(self.address.get()))
        ttk.Button(bar, text='前往', command=lambda: self.load(self.address.get())).pack(side='left')
        self.tree = ttk.Treeview(root, columns=('type', 'size', 'time'), show='tree headings')
        for col, title, width in (('#0','名称',450),('type','类型',100),('size','大小',120),('time','修改时间',180)):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, stretch=(col == '#0'))
        self.tree.pack(fill='both', expand=True, padx=20)
        self.tree.bind('<Double-1>', self.open_item)
        self.status = tk.StringVar(value='点击连接；双击目录进入。')
        ttk.Label(root, textvariable=self.status, style='Muted.TLabel', padding=(20, 12)).pack(fill='x')
        root.protocol('WM_DELETE_WINDOW', self.close)

    def connect(self):
        host, username = self.host.get().strip(), self.username.get().strip()
        try:
            port = int(self.port.get())
            if not host or not username or not 1 <= port <= 65535:
                raise ValueError()
        except ValueError:
            self.error('请输入服务器地址、用户名和有效端口（1–65535）。')
            return
        password = simpledialog.askstring('服务器密码', f'输入 {username}@{host} 的密码：', show='*', parent=self.root)
        if password is None:
            return
        self.status.set('正在连接…')
        def work():
            client = paramiko.SSHClient()
            try:
                client.load_system_host_keys()
                client.set_missing_host_key_policy(ConfirmHostKey(self.root))
                client.connect(host, port=port, username=username, password=password, timeout=12, allow_agent=False, look_for_keys=False)
                sftp = client.open_sftp()
                self.root.after(0, lambda: self.connected(client, sftp))
            except Exception as exc:
                client.close()
                msg = str(exc)
                self.root.after(0, lambda: self.error(msg))
        threading.Thread(target=work, daemon=True).start()

    def connected(self, client, sftp):
        if self.client:
            self.client.close()
        self.client, self.sftp = client, sftp
        self.load(self.path)

    def error(self, msg):
        self.status.set('操作失败')
        messagebox.showerror('连接或读取失败', msg, parent=self.root)

    def load(self, path):
        if not self.sftp:
            self.status.set('请先连接服务器')
            return
        try:
            path = self.sftp.normalize(path)
            entries = self.sftp.listdir_attr(path)
            self.tree.delete(*self.tree.get_children())
            for item in sorted(entries, key=lambda e: (not stat.S_ISDIR(e.st_mode), e.filename.casefold())):
                kind = '目录' if stat.S_ISDIR(item.st_mode) else ('链接' if stat.S_ISLNK(item.st_mode) else '文件')
                self.tree.insert('', 'end', text=item.filename, values=(kind, '' if kind == '目录' else format_size(item.st_size), datetime.fromtimestamp(item.st_mtime).strftime('%Y-%m-%d %H:%M')))
            self.path = path
            self.address.set(path)
            self.status.set(f'{len(entries)} 项；双击目录或链接进入，按刷新读取最新内容。')
        except Exception as exc:
            self.error(str(exc))

    def open_item(self, _event):
        selected = self.tree.selection()
        if selected:
            item = self.tree.item(selected[0])
            if item['values'][0] in ('目录', '链接'):
                self.load(posixpath.join(self.path, item['text']))

    def close(self):
        if self.client:
            self.client.close()
        self.root.destroy()

if __name__ == '__main__':
    root = tk.Tk()
    Browser(root)
    root.mainloop()
