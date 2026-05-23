# MultiCameraManagement-FacialRecognition

这是一个基于 PySide2 + OpenCV 的多摄像头人脸识别桌面系统。当前已包含登录/注册、摄像头显示、人脸录入、LBPH 训练、识别日志、考勤逻辑等基础能力，并逐步按 `prompt.md` 中的四层架构重构。

## 环境要求

推荐使用 Python 3.8-3.10。不要使用 Python 3.14 运行本项目，因为 PySide2 旧版本通常无法正常安装。

核心依赖：

- PySide2
- opencv-contrib-python
- opencv-python
- numpy
- Pillow
- PyMySQL

## 安装与运行

在项目根目录执行：

```powershell
cd D:\Coding_programs\Projects\Facical_reco_base\MultiCameraManagement-FacialRecognition
```

如果使用本机已有 Conda 环境，当前推荐环境是：

```text
D:\Anaconda_envs\envs\FaceReco
Python 3.8.20
```

在 PowerShell 中可以这样运行：

```powershell
conda activate D:\Anaconda_envs\envs\FaceReco
python tools\doctor.py
python run.py
```

也可以直接双击项目根目录下的：

```text
run_conda_facereco.bat
```

如果不用 Conda，也可以使用 Python 3.9 创建虚拟环境：

```powershell
C:\Python39\python.exe -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

如果 PowerShell 不允许激活虚拟环境，先执行：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

启动前自检：

```powershell
python tools\doctor.py
```

启动程序：

```powershell
python run.py
```

也可以直接运行旧入口：

```powershell
python main.py
```

## 登录账号

默认管理员账号：

```text
账号：admin
密码：admin
```

如果忘记密码或登录失败，可以重置管理员密码：

```powershell
python tools\doctor.py --reset-admin admin
```

然后重新使用：

```text
admin / admin
```

## 数据库说明

系统优先连接 MySQL。默认连接信息：

```text
host=localhost
port=3307
user=root
password=password
database=db_bishe
```

可以通过环境变量覆盖：

```powershell
$env:FACE_DB_HOST="localhost"
$env:FACE_DB_PORT="3307"
$env:FACE_DB_USER="root"
$env:FACE_DB_PASSWORD="password"
$env:FACE_DB_NAME="db_bishe"
```

初始化 MySQL：

```powershell
mysql -u root -p < init_db.sql
```

如果 MySQL 无法连接，系统会自动降级到本地 SQLite，并创建 `facial_system.db`，这样登录、日志、测试仍然可以运行。

## 测试

```powershell
python -m pytest tests -q
```

## 常见问题

如果提示缺少 `PySide2` 或 `cv2`，通常是没有激活虚拟环境，或者 Python 版本太新。请确认：

```powershell
python --version
python tools\doctor.py
```

如果当前是 Python 3.14，请改用 Python 3.9/3.10 创建虚拟环境。
