# Task-00 事件与数据结构契约

## 1. 命名冻结

并行阶段统一使用以下命名，后续任务不要再发明别名：

- `FramePacket`
- `DetectionResult`
- `RecognitionResult`
- `EmotionResult`
- `AlertResult`
- `VisionObservation`
- `EventEnvelope`
- `SystemStatus`

所有 JSON/YAML 字段统一使用 `snake_case`。

## 2. 公共约束

### 2.1 时间格式

- 所有对外时间统一使用 RFC3339 / ISO8601 字符串
- 例：`2026-06-03T14:05:01+08:00`

### 2.2 标识字段

- `camera_id`：逻辑摄像头 ID，字符串，前后端共享
- `slot_id`：前端布局槽位，可选，整数 1~4 兼容旧 UI
- `frame_id`：单摄像头递增帧号
- `track_id`：单摄像头内跟踪 ID；无跟踪结果时可为空

### 2.3 坐标字段

- `bbox` 统一表示为 `[x, y, w, h]`
- 单位为像素
- 基于当前帧左上角坐标系

## 3. FramePacket

用途：

- 表示一帧视频及其元数据
- 可用于 `/ws/stream/{camera_id}` 或调试快照

字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `camera_id` | `string` | 是 | 逻辑摄像头 ID |
| `slot_id` | `integer` | 否 | 兼容旧 1~4 槽位 |
| `frame_id` | `integer` | 是 | 该摄像头下递增帧号 |
| `captured_at` | `string(date-time)` | 是 | 采集时间 |
| `source_uri` | `string` | 是 | 视频源；集成摄像头兼容 `"0"` |
| `width` | `integer` | 是 | 帧宽 |
| `height` | `integer` | 是 | 帧高 |
| `color_space` | `string` | 是 | `bgr` / `rgb` / `gray` |
| `image_encoding` | `string` | 否 | `jpeg_base64` / `png_base64` / `none` |
| `image_data` | `string` | 否 | 编码后的图像数据；事件总线可省略 |
| `runtime_mode` | `string` | 是 | `realtime` / `balanced` / `accurate` |
| `backend_mode` | `string` | 是 | `deep` / `lbph` / `lite` / `unavailable` |

## 4. DetectionResult

用途：

- 表示检测与跟踪层输出
- 由 Task-03 / Task-05 / Task-07 共用

字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `camera_id` | `string` | 是 | 摄像头 ID |
| `frame_id` | `integer` | 是 | 帧号 |
| `track_id` | `integer` | 否 | 跟踪 ID |
| `bbox` | `array[4]` | 是 | `[x, y, w, h]` |
| `det_score` | `number` | 否 | 检测置信度，0~1 |
| `quality` | `string` | 是 | `good` / `weak` / `bad` |
| `detector` | `string` | 是 | `yolov8_face` / `insightface_det` / `haar` / `other` |
| `recognition_skipped` | `boolean` | 否 | 本轮仅检测未做识别时为 `true` |

## 5. RecognitionResult

用途：

- 表示识别层输出
- 与当前 `FaceRecognitionService.recognize_frame()` 语义对齐

字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `camera_id` | `string` | 是 | 摄像头 ID |
| `frame_id` | `integer` | 是 | 帧号 |
| `track_id` | `integer` | 否 | 跟踪 ID |
| `bbox` | `array[4]` | 是 | `[x, y, w, h]` |
| `label_id` | `integer` | 否 | 用户标签 ID |
| `name` | `string` | 是 | 识别名；未知统一为 `unknown` |
| `similarity` | `number` | 否 | 相似度，推荐 0~1 |
| `confidence` | `number` | 否 | 兼容当前实现，推荐 0~100 |
| `backend_mode` | `string` | 是 | `deep` / `lbph` / `lite` |
| `match_reason` | `string` | 否 | `fresh` / `steady` / `tracked` / `switch` / `pending_switch` / `hold` / `fallback` |

约束：

- 未识别时 `name` 必须为 `unknown`。
- 不允许使用 `Unknown`、`UNKNOWN`、`none` 等变体。

## 6. EmotionResult

用途：

- 表示情绪推理输出

字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `camera_id` | `string` | 是 | 摄像头 ID |
| `frame_id` | `integer` | 是 | 帧号 |
| `track_id` | `integer` | 否 | 跟踪 ID |
| `name` | `string` | 否 | 对应识别名 |
| `bbox` | `array[4]` | 否 | 对应 ROI |
| `emotion` | `string` | 是 | 当前情绪标签 |
| `confidence` | `number` | 是 | 0~1 |
| `quality` | `string` | 是 | `good` / `weak` / `bad` / `fallback` |
| `reason` | `string` | 是 | `model_vote` / `stable_window_vote` / `cache_hit` / `fallback_neutral` |

约束：

- 模型不可用时统一返回 `emotion="中性"`，`quality="fallback"`。

## 7. AlertResult

用途：

- 统一未来功能包、稳定性模块和系统页的告警结构
- 当前主工程没有独立告警总线，因此这是并行改造新增契约

字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `alert_id` | `string` | 是 | 告警 ID |
| `camera_id` | `string` | 否 | 摄像头级告警时必填 |
| `frame_id` | `integer` | 否 | 与帧绑定时填写 |
| `track_id` | `integer` | 否 | 与人脸轨迹绑定时填写 |
| `alert_type` | `string` | 是 | `unknown_face` / `camera_offline` / `backend_degraded` / `model_pending` / `attendance_absence` / `stream_error` |
| `severity` | `string` | 是 | `info` / `warning` / `critical` |
| `status` | `string` | 是 | `open` / `acknowledged` / `resolved` |
| `title` | `string` | 是 | 短标题 |
| `message` | `string` | 是 | 人类可读说明 |
| `occurred_at` | `string(date-time)` | 是 | 告警触发时间 |
| `evidence` | `object` | 否 | 可选证据，如 `bbox`、截图引用、异常码 |

## 8. VisionObservation

用途：

- 统一一帧或一个观察窗口内的多结果聚合
- 供 Task-01、Task-02、Task-05、Task-06、Task-07 共用

结构：

```json
{
  "frame": {},
  "detections": [],
  "recognitions": [],
  "emotions": [],
  "alerts": [],
  "system_status": {}
}
```

字段说明：

- `frame`：`FramePacket`
- `detections`：`DetectionResult[]`
- `recognitions`：`RecognitionResult[]`
- `emotions`：`EmotionResult[]`
- `alerts`：`AlertResult[]`
- `system_status`：`SystemStatus`

## 9. SystemStatus

字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `runtime_mode` | `string` | 是 | `realtime` / `balanced` / `accurate` |
| `backend_mode` | `string` | 是 | `deep` / `lbph` / `lite` / `unavailable` |
| `provider_chain` | `array[string]` | 否 | 例如 `["CUDAExecutionProvider", "CPUExecutionProvider"]` |
| `provider_display` | `string` | 否 | 例如 `ArcFace：CUDA（回退 CPU）` |
| `model_pending` | `boolean` | 是 | 是否待更新模型 |
| `fps_overlay_enabled` | `boolean` | 是 | 是否显示 FPS |
| `active_cameras` | `integer` | 是 | 当前活动摄像头数 |
| `registered_users` | `integer` | 是 | 当前已登记用户数 |
| `degraded` | `boolean` | 是 | 是否处于降级状态 |

## 10. EventEnvelope

所有 `/ws/events` 消息统一包裹成：

```json
{
  "event_type": "vision.observation",
  "event_version": "v1",
  "emitted_at": "2026-06-03T14:05:01+08:00",
  "payload": {}
}
```

字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `event_type` | `string` | 是 | 事件类型 |
| `event_version` | `string` | 是 | 当前固定 `v1` |
| `emitted_at` | `string(date-time)` | 是 | 事件发送时间 |
| `payload` | `object` | 是 | 事件体 |

## 11. 推荐事件类型

### 11.1 `vision.observation`

- `payload` 类型：`VisionObservation`
- 适合 `/ws/events`

### 11.2 `camera.state`

建议字段：

- `camera_id`
- `state`: `starting / running / stopping / stopped / error / offline`
- `message`

### 11.3 `system.status`

- `payload` 类型：`SystemStatus`

### 11.4 `alert.raised`

- `payload` 类型：`AlertResult`

## 12. 与旧工程的对齐说明

- `RecognitionResult.name` 对齐当前 `FaceRecognitionService.recognize_frame()`。
- `RecognitionResult.confidence` 对齐当前 0~100 表示。
- `EmotionResult.emotion` 对齐当前情绪服务输出。
- `SystemStatus.runtime_mode` 对齐当前 `AppState.realtime_mode`。
- `SystemStatus.fps_overlay_enabled` 对齐当前 `AppState.show_fps_overlay`。

## 13. 给 Task-01 ~ Task-09 的使用建议

- Task-01：REST 返回列表时，内部对象名称就按本文件，不要在 API 层临时翻译。
- Task-02：前端类型定义直接照抄本文件字段即可。
- Task-03：若新增 tracking 字段，只能扩展，不要改掉已有键名。
- Task-04：情绪质量判定必须填 `quality` 和 `reason`。
- Task-05：`frame_id` 必须单摄像头递增，不能随机。
- Task-06：任何新告警都先映射到 `AlertResult`。
- Task-07：系统降级既可以发 `system.status`，也可以额外发 `alert.raised`。
- Task-08：集成时优先做字段透传，避免改名。
- Task-09：回归测试请以这些结构为断言目标。
