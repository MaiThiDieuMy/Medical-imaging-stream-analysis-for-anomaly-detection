import type { UserRole } from "../types/api";

export type PageKey =
  | "dashboard"
  | "analyze"
  | "cases"
  | "models"
  | "reviews"
  | "users"
  | "monitoring";

export type NavigationItem = {
  key: PageKey;
  label: string;
};

const doctorNavigation: NavigationItem[] = [
  { key: "dashboard", label: "Tổng quan" },
  { key: "analyze", label: "Phân tích ảnh" },
  { key: "cases", label: "Lịch sử ca chụp" },
  { key: "reviews", label: "Duyệt ca" },
];

const adminNavigation: NavigationItem[] = [
  { key: "dashboard", label: "Tổng quan" },
  { key: "users", label: "Người dùng" },
  { key: "models", label: "Mô hình AI" },
  { key: "reviews", label: "Duyệt ca" },
  { key: "cases", label: "Tất cả ca chụp" },
  { key: "monitoring", label: "Giám sát" },
];

export function getNavigationForRole(role: UserRole): NavigationItem[] {
  return role === "admin" ? adminNavigation : doctorNavigation;
}

export function defaultPageForRole(_role: UserRole): PageKey {
  return "dashboard";
}

export function roleLabel(role: UserRole): string {
  return role === "admin" ? "Quản trị viên" : "Bác sĩ/KTV";
}
