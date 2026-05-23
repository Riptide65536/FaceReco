id: codex-prompt
name: Codex 项目提示词
type: markdown
content: |-
  # 项目开发提示词：基于深度学习的人脸识别系统

  ## 项目背景与目标

  你是一名经验丰富的 Python 全栈工程师。请根据以下规格说明，从零开始构建一个**基于深度学习的人脸识别桌面应用系统**。该系统需集成人脸检测、身份识别、情绪分析、考勤打卡等核心功能，最终交付一个稳定、可运行的桌面软件。

  ---

  ## 零、有关于报告

  有关于这个项目的所需报告和如何实现在reports/文件夹下的一系列word文件中呈现，请务必查看这些word文档。

  ## 一、技术栈要求

  | 层次 | 技术选型 |
  |------|----------|
  | GUI 框架 | PySide2 |
  | 图像处理 | OpenCV (cv2) |
  | 人脸识别 | OpenCV LBPHFaceRecognizer + Haar 特征分类器 |
  | 情绪识别 | 预训练 CNN 深度学习模型（基于 Keras/TensorFlow） |
  | 数据库 | MySQL |
  | 并发处理 | Python threading 多线程 + threading.Lock |
  | 语言版本 | Python 3.8+ |

  ---

  ## 二、系统架构

  系统严格采用**四层架构**，各层职责如下：

  ### 1. 用户界面层（UI Layer）
  - 使用 PySide2 构建主窗口
  - 主界面布局：
    - **左侧**：摄像头配置面板（添加/删除/配置摄像头）
    - **中央**：2×2 网格多路视频实时显示区域（使用 QLabel 显示帧）
    - **底部**：功能控制栏（模式切换、操作按钮）
  - 界面风格：现代化扁平化设计，**主色调为橙色**
  - 支持多窗口操作

  ### 2. 业务逻辑层（Business Logic Layer）
  包含以下四个核心模块：

  #### (a) 摄像头管理模块 `CameraService`
  - 封装摄像头生命周期管理（添加、删除、配置）
  - 支持配置项：摄像头名称、型号、拉流地址（支持本地文件/RTSP）、安装位置
  - 支持三种显示模式（通过 `displaymode` 参数控制）：
    - `0`：纯显示模式
    - `1`：人脸检测模式
    - `2`：人脸识别模式
  - 每个摄像头独立运行于子线程，使用 `systemLock` 资源锁防止竞态条件

  #### (b) 人脸检测识别模块 `FaceRecognitionService`
  - 使用 `haarcascade_frontalface_default.xml` 进行人脸检测
  - 使用 `cv2.face.LBPHFaceRecognizer_create()` 进行身份识别
  - 处理流程：视频帧捕获 → 灰度化 → 人脸检测 → 特征提取 → 身份预测
  - 支持多人人脸同帧检测与批量识别
  - 识别置信度阈值可配置，低于阈值输出"未知"

  #### (c) 情绪识别模块 `EmotionRecognitionService`
  - 加载预训练 CNN 模型（.h5 格式）
  - 识别七种基本情绪：高兴、悲伤、愤怒、惊讶、恐惧、厌恶、中性
  - 预处理流程：人脸裁剪 → 48×48 缩放 → 像素归一化 → 模型推理 → softmax 概率输出
  - 引入**多帧融合机制**（对连续 N 帧结果加权平均）以提升稳定性

  #### (d) 人脸管理模块 `FaceManagementService`
  - 新用户人脸采集：默认采集 **10 张**人脸图片并存储
  - 训练 LBPHFaceRecognizer 模型并保存（`trainer.yml` + 标签映射文件）
  - 支持删除用户人脸数据及关联历史记录
  - 支持重置/重新训练模型

  #### (e) 日志与考勤模块 `AttendanceService`
  - 记录每次识别结果：人员姓名、地点、时间戳、摄像头位置、情绪状态
  - 考勤打卡类型：上班打卡、下班打卡、外出登记
  - 支持异常考勤自动检测：迟到、早退、缺勤
  - 提供考勤统计报表生成功能

  ### 3. 数据访问层（Data Access Layer）
  封装于 `SqlF` 类，提供以下核心方法：
  ```python
  class SqlF:
      def loginAccountPassword(self, username, password) -> bool
      def register(self, username, password) -> bool
      def getAllaccount(self) -> list
      def saveNameTimePic(self, name, location, time, emotion, attendance_type) -> bool
      def resetDB(self) -> bool
      def saveFaceFeature(self, name, feature_matrix) -> bool
      def getAttendanceReport(self, start_date, end_date) -> list
  ```

  **MySQL 数据库表结构**：
  ```sql
  -- 用户账户表
  CREATE TABLE accounts (
      id INT PRIMARY KEY AUTO_INCREMENT,
      username VARCHAR(50) UNIQUE NOT NULL,
      password VARCHAR(255) NOT NULL
  );

  -- 识别日志表
  CREATE TABLE recognition_logs (
      id INT PRIMARY KEY AUTO_INCREMENT,
      name VARCHAR(100),
      location VARCHAR(100),
      timestamp DATETIME,
      emotion VARCHAR(20),
      attendance_type VARCHAR(20),
      image_path VARCHAR(255)
  );

  -- 人脸特征表
  CREATE TABLE face_features (
      id INT PRIMARY KEY AUTO_INCREMENT,
      name VARCHAR(100),
      label INT,
      feature_path VARCHAR(255)
  );
  ```

  ### 4. 技术支撑层（Infrastructure Layer）
  - OpenCV VideoCapture 支持本地摄像头（索引）和 RTSP 流
  - `systemLock = threading.Lock()` 全局资源锁
  - 配置文件（`config.json`）存储摄像头信息，程序启动时自动加载

  ---

  ## 三、核心功能实现要求

  ### 3.1 多路视频流并发显示
  ```
  - 最多同时支持 4 路视频流（2×2 布局）
  - 每路视频独立线程，帧率目标 ≥ 25 FPS
  - 线程间通过 Qt 信号槽机制更新 UI（禁止在子线程直接操作 UI）
  - 使用 systemLock 防止多线程竞争显示窗口
  ```

  ### 3.2 人脸识别性能指标
  ```
  - 单次识别响应时间：≤ 1 秒
  - 识别准确率：≥ 95%
  - 支持弱光、遮挡（口罩）、快速移动等边界场景
  - 系统需支持 24 小时不间断稳定运行
  ```

  ### 3.3 考勤系统逻辑
  ```
  - 同一人同一天首次识别 → 上班打卡
  - 同一人当天再次识别（下班时间段）→ 下班打卡
  - 超过上班时间阈值（可配置，默认 09:00）→ 标记迟到
  - 早于下班时间阈值（可配置，默认 18:00）→ 标记早退
  - 每日定时任务检测缺勤人员
  ```

  ---

  ## 四、项目目录结构

  ```
  face_recognition_system/
  ├── main.py                    # 程序入口
  ├── config.json                # 摄像头及系统配置
  ├── requirements.txt           # 依赖清单
  ├── ui/
  │   ├── main_window.py         # 主窗口
  │   ├── camera_panel.py        # 摄像头配置面板
  │   ├── face_management_ui.py  # 人脸管理界面
  │   └── attendance_ui.py       # 考勤查询界面
  ├── services/
  │   ├── camera_service.py      # 摄像头管理服务
  │   ├── face_recognition_service.py  # 人脸检测识别服务
  │   ├── emotion_service.py     # 情绪识别服务
  │   ├── face_management_service.py   # 人脸管理服务
  │   └── attendance_service.py  # 考勤服务
  ├── data/
  │   ├── sql_helper.py          # SqlF 数据库封装类
  │   └── config_manager.py      # 配置文件管理
  ├── models/
  │   ├── trainer.yml            # LBPH 训练模型
  │   ├── labels.pkl             # 标签映射
  │   └── emotion_model.h5       # 情绪识别 CNN 模型
  ├── assets/
  │   ├── haarcascade_frontalface_default.xml
  │   └── icons/                 # UI 图标资源
  └── tests/
      ├── test_face_recognition.py
      └── test_attendance.py
  ```

  ---

  ## 五、关键代码规范

  1. **线程安全**：所有涉及共享资源的操作必须使用 `with systemLock:` 上下文管理器
  2. **Qt 信号槽**：子线程更新 UI 必须通过 `pyqtSignal` 发射信号，在主线程槽函数中更新
  3. **异常处理**：摄像头连接失败、模型加载失败等异常需捕获并在 UI 上给出提示
  4. **资源释放**：程序退出时需正确释放所有 VideoCapture 对象和数据库连接
  5. **日志记录**：使用 Python `logging` 模块记录关键操作和错误信息

  ---

  ## 六、交付要求

  - [ ] 完整可运行的源代码
  - [ ] `requirements.txt` 依赖文件
  - [ ] 数据库初始化 SQL 脚本（`init_db.sql`）
  - [ ] `README.md`（含环境配置、启动方式说明）
  - [ ] 核心模块单元测试（覆盖人脸识别、考勤逻辑）

  ---

  ## 七、开发优先级

  **P0（必须实现）**：
  1. 用户登录/注册
  2. 摄像头添加与多路视频显示
  3. 人脸注册与 LBPH 模型训练
  4. 实时人脸检测与身份识别
  5. 识别日志记录与查询

  **P1（重要功能）**：
  6. 情绪识别（七分类）
  7. 考勤打卡与异常检测
  8. 多人同帧识别

  **P2（增强功能）**：
  9. 考勤统计报表导出
  10. 弱光/遮挡场景优化
  11. 24 小时压力测试验证
