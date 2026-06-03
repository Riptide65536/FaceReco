export interface NavRouteMeta {
  path: string;
  label: string;
  eyebrow: string;
  description: string;
}

export const loginRoute = {
  path: "/login",
  label: "登录",
  eyebrow: "Access Control",
  description: "统一身份登录与操作台入口",
};

export const navRoutes: NavRouteMeta[] = [
  {
    path: "/overview",
    label: "监控总览",
    eyebrow: "Control Room",
    description: "多路视频、识别结果与告警汇聚视图",
  },
  {
    path: "/cameras",
    label: "摄像头管理",
    eyebrow: "Camera Fleet",
    description: "查看视频源状态、运行模式与启停动作",
  },
  {
    path: "/faces",
    label: "人脸库管理",
    eyebrow: "Face Registry",
    description: "维护人员档案、样本质量与重点关注对象",
  },
  {
    path: "/logs",
    label: "日志与考勤",
    eyebrow: "Audit Trail",
    description: "查询识别日志、考勤结果与导出报表",
  },
  {
    path: "/system",
    label: "系统状态",
    eyebrow: "Ops Health",
    description: "追踪服务健康、性能趋势与接口联通情况",
  },
];

export function findRouteMeta(pathname: string): NavRouteMeta {
  return (
    navRoutes.find((item) => pathname.startsWith(item.path)) ??
    navRoutes[0]
  );
}
