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

## 阶段四性能自检

可使用内置性能脚本快速检查识别耗时、95/99 分位延迟与有效帧率。

```powershell
# 检测模式（只做人脸检测）
python tools\perf_check.py --mode detect --source "1 Danny MacAskill’s Wee Day Out.flv" --frames 300

# 识别模式（Haar + LBPH）
python tools\perf_check.py --mode recognize --source 0 --frames 300

# 识别+情绪模式（若情绪模型不可用会自动降级）
python tools\perf_check.py --mode recognize_emotion --source 0 --frames 300

# 稳定性巡检模式：持续 10 分钟，每 30 秒打印一次，并输出 JSON 报告
python tools\perf_check.py --mode recognize --source 0 --duration-seconds 600 --report-interval 30 --output-json reports\perf_stability.json
```

关键指标说明：
- `avg_latency_ms`：平均每帧处理耗时
- `p95_latency_ms` / `p99_latency_ms`：95/99 分位耗时
- `effective_fps`：整段处理有效帧率
- `pass_single_response<=1000ms`：是否满足单次识别 ≤ 1 秒

阶段四一键检查（环境 + 单测 + 性能）：

```powershell
# 仅演练命令，不实际执行
python tools\stage4_check.py --dry-run

# 实际执行（默认会写 reports/stage4_check_report.json）
python tools\stage4_check.py --strict --perf-mode recognize --perf-source 0 --perf-frames 200

# 稳定性巡检 10 分钟
python tools\stage4_check.py --strict --perf-mode recognize --perf-source 0 --perf-duration-seconds 600 --perf-report-interval 30
```

## 常见问题

如果提示缺少 `PySide2` 或 `cv2`，通常是没有激活虚拟环境，或者 Python 版本太新。请确认：

```powershell
python --version
python tools\doctor.py
```

如果当前是 Python 3.14，请改用 Python 3.9/3.10 创建虚拟环境。
