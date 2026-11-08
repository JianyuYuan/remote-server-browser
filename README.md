# Remote Server Browser

一个深色界面的只读 SFTP 目录浏览器。输入服务器地址、端口和用户名，连接时输入密码，即可查看目录、文件大小和修改时间。支持输入路径、进入目录、返回上级和刷新。

## 运行

需要 Python 3.10 或更高版本（含 Tkinter）。

```bash
python -m pip install -r requirements.txt
python remote_browser.py
```

首次连接未知服务器时，程序显示 SSH 主机密钥的 SHA256 指纹。请通过可信渠道与服务器管理员确认后再接受；确认只对该次连接有效。已有系统 SSH known_hosts 中的密钥会自动核验，密钥不匹配时连接失败。

密码只用于当前连接，不写入项目文件。目录列表在进入或点击刷新时从服务器读取；界面没有上传、修改或删除功能。

运行测试：`python -m unittest -v`
