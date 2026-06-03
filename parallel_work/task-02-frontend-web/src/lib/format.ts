export function formatPercent(value: number) {
  return `${value.toFixed(value >= 100 ? 0 : 1)}%`;
}

export function formatLatency(value: number) {
  return `${Math.round(value)} ms`;
}

export function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(value));
}

export function formatRelativeTime(value: string) {
  const diffMs = Date.now() - new Date(value).getTime();
  const diffMin = Math.round(diffMs / 60000);
  if (diffMin < 1) {
    return "刚刚";
  }
  if (diffMin < 60) {
    return `${diffMin} 分钟前`;
  }
  const diffHour = Math.round(diffMin / 60);
  if (diffHour < 24) {
    return `${diffHour} 小时前`;
  }
  const diffDay = Math.round(diffHour / 24);
  return `${diffDay} 天前`;
}

export function toDateInputValue(offsetDays = 0) {
  const date = new Date();
  date.setDate(date.getDate() + offsetDays);
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function cn(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}
