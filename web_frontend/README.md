# FaceReco Web Frontend

这是基于当前桌面版功能整理出的网页端前端，入口为 `index.html`。当前版本不修改原有 PySide2、OpenCV、人脸识别、情绪识别、考勤和数据库逻辑。

## 覆盖功能

- 登录、注册入口
- 四路监控窗口
- 添加 / 删除摄像头
- 保存配置 / 立刻应用
- 显示模式：人脸识别、人脸检测、纯显示
- 识别策略：实时优先、平衡模式、高精度
- FPS 显示开关
- 自定义签到开始 / 结束
- 人脸录入、样本进度、更新模型、重置模型、删除人脸
- 日志查询、清空数据库、当日缺勤、考勤汇总、导出 CSV

## 后端接入

前端在 `app.js` 中预留了 `window.FaceRecoApiBase`。如果后续新增 Web 后端，只需要在页面加载前设置：

```html
<script>
  window.FaceRecoApiBase = "http://127.0.0.1:8000";
</script>
```

视频流建议使用 MJPEG、WebSocket 或 WebRTC，把当前 `canvas` 中的演示渲染替换为真实帧绘制即可。现有动态渲染使用 `requestAnimationFrame`，不会阻塞人脸识别线程。
