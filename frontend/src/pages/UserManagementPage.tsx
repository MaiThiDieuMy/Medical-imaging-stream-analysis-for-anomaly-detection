import { FormEvent, useEffect, useMemo, useState } from "react";
import { createUser, listUsers, updateUser } from "../api/client";
import { Message } from "../components/Message";
import { StatusBadge } from "../components/StatusBadge";
import type { UserPublic, UserRole } from "../types/api";
import { compactId, formatDateTime } from "../utils/format";
import { roleLabel } from "../utils/navigation";

const roles: UserRole[] = ["user", "admin"];

type PanelMode = "create" | "edit" | "view" | null;

type UserFormState = {
  username: string;
  password: string;
  full_name: string;
  role: UserRole;
};

const emptyForm: UserFormState = {
  username: "",
  password: "",
  full_name: "",
  role: "user",
};

export function UserManagementPage() {
  const [users, setUsers] = useState<UserPublic[]>([]);
  const [panelMode, setPanelMode] = useState<PanelMode>(null);
  const [activeUser, setActiveUser] = useState<UserPublic | null>(null);
  const [form, setForm] = useState<UserFormState>(emptyForm);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<"all" | UserRole>("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "inactive">("all");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function refreshUsers(nextActiveUserId?: string | null) {
    const loadedUsers = await listUsers();
    setUsers(loadedUsers);
    if (nextActiveUserId) {
      const refreshedUser =
        loadedUsers.find((user) => user.user_id === nextActiveUserId) ?? null;
      setActiveUser(refreshedUser);
      if (refreshedUser && panelMode === "edit") {
        setForm(formFromUser(refreshedUser));
      }
    }
  }

  useEffect(() => {
    refreshUsers().catch((exc) =>
      setError(exc instanceof Error ? exc.message : "Không tải được người dùng."),
    );
  }, []);

  const filteredUsers = useMemo(() => {
    const query = search.trim().toLowerCase();
    return users.filter((user) => {
      const matchesQuery =
        !query ||
        user.username.toLowerCase().includes(query) ||
        user.full_name.toLowerCase().includes(query);
      const matchesRole = roleFilter === "all" || user.role === roleFilter;
      const currentStatus = user.is_active ? "active" : "inactive";
      const matchesStatus =
        statusFilter === "all" || currentStatus === statusFilter;
      return matchesQuery && matchesRole && matchesStatus;
    });
  }, [roleFilter, search, statusFilter, users]);

  function openCreatePanel() {
    setError(null);
    setMessage(null);
    setActiveUser(null);
    setForm(emptyForm);
    setPanelMode("create");
  }

  function openViewPanel(user: UserPublic) {
    setError(null);
    setMessage(null);
    setActiveUser(user);
    setPanelMode("view");
  }

  function openEditPanel(user: UserPublic) {
    setError(null);
    setMessage(null);
    setActiveUser(user);
    setForm(formFromUser(user));
    setPanelMode("edit");
  }

  function closePanel() {
    setPanelMode(null);
    setActiveUser(null);
    setForm(emptyForm);
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    try {
      setLoading(true);
      const created = await createUser({
        username: form.username.trim(),
        password: form.password,
        full_name: form.full_name.trim(),
        role: form.role,
      });
      setMessage("Đã thêm người dùng.");
      setPanelMode("view");
      setActiveUser(created);
      setForm(emptyForm);
      await refreshUsers(created.user_id);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không tạo được người dùng.");
    } finally {
      setLoading(false);
    }
  }

  async function handleEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!activeUser) {
      return;
    }
    setError(null);
    setMessage(null);
    try {
      setLoading(true);
      const updated = await updateUser(activeUser.user_id, {
        full_name: form.full_name.trim(),
        role: form.role,
        ...(form.password.trim() ? { password: form.password } : {}),
      });
      setMessage("Đã lưu thay đổi người dùng.");
      setActiveUser(updated);
      setForm(formFromUser(updated));
      await refreshUsers(updated.user_id);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không cập nhật được người dùng.");
    } finally {
      setLoading(false);
    }
  }

  async function handleToggleActive(user: UserPublic) {
    const nextActive = !user.is_active;
    const verb = nextActive ? "mở khóa" : "khóa";
    if (
      !window.confirm(
        `Bạn muốn ${verb} tài khoản ${user.username}? Tài khoản bị khóa sẽ không thể đăng nhập.`,
      )
    ) {
      return;
    }

    setError(null);
    setMessage(null);
    try {
      setLoading(true);
      const updated = await updateUser(user.user_id, { is_active: nextActive });
      setMessage(
        nextActive ? "Đã mở khóa tài khoản." : "Đã khóa tài khoản. Dữ liệu người dùng vẫn được giữ.",
      );
      if (activeUser?.user_id === user.user_id) {
        setActiveUser(updated);
      }
      await refreshUsers(updated.user_id);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : `Không thể ${verb} tài khoản.`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="page user-management-page">
      <div className="page-header">
        <div>
          <h2>Quản lý người dùng</h2>
          <p>
            Quản trị viên tạo tài khoản, chỉnh vai trò và khóa/mở khóa người dùng.
            Không xóa cứng tài khoản khỏi hệ thống.
          </p>
        </div>
        <div className="actions">
          <span className="count-pill">{filteredUsers.length}/{users.length} người dùng</span>
          <button className="primary" onClick={openCreatePanel} type="button">
            Thêm người dùng
          </button>
        </div>
      </div>

      {error && <Message tone="error">{error}</Message>}
      {message && <Message tone="success">{message}</Message>}

      <div className="panel filter-panel user-filter-panel">
        <label>
          Tìm người dùng
          <input
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Nhập tên đăng nhập hoặc họ tên"
            value={search}
          />
        </label>
        <label>
          Vai trò
          <select
            onChange={(event) => setRoleFilter(event.target.value as "all" | UserRole)}
            value={roleFilter}
          >
            <option value="all">Tất cả</option>
            {roles.map((role) => (
              <option key={role} value={role}>
                {roleLabel(role)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Trạng thái
          <select
            onChange={(event) =>
              setStatusFilter(event.target.value as "all" | "active" | "inactive")
            }
            value={statusFilter}
          >
            <option value="all">Tất cả</option>
            <option value="active">Đang hoạt động</option>
            <option value="inactive">Đã khóa</option>
          </select>
        </label>
      </div>

      <div className="panel user-table-panel">
        <div className="section-heading">
          <div>
            <h3>Danh sách tài khoản</h3>
            <p className="muted">
              Thao tác quản trị nằm trực tiếp trên từng dòng để tránh nhầm tài khoản.
            </p>
          </div>
        </div>
        <div className="table-wrap user-table-wrap">
          <table className="user-management-table">
            <thead>
              <tr>
                <th>Tên đăng nhập</th>
                <th>Họ tên</th>
                <th>Vai trò</th>
                <th>Trạng thái</th>
                <th>Ngày tạo</th>
                <th>Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {filteredUsers.map((user) => (
                <tr
                  className={activeUser?.user_id === user.user_id ? "selected-row" : ""}
                  key={user.user_id}
                >
                  <td>{user.username}</td>
                  <td>{user.full_name}</td>
                  <td>{roleLabel(user.role)}</td>
                  <td>
                    <StatusBadge value={user.is_active ? "active" : "inactive"} />
                  </td>
                  <td>{formatDateTime(user.created_at)}</td>
                  <td>
                    <div className="row-actions">
                      <button onClick={() => openViewPanel(user)} type="button">
                        Xem
                      </button>
                      <button onClick={() => openEditPanel(user)} type="button">
                        Sửa
                      </button>
                      <button
                        className={user.is_active ? "danger" : "primary"}
                        disabled={loading}
                        onClick={() => void handleToggleActive(user)}
                        type="button"
                      >
                        {user.is_active ? "Khóa" : "Mở khóa"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {filteredUsers.length === 0 && (
                <tr>
                  <td colSpan={6}>Không có người dùng phù hợp bộ lọc.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {panelMode && (
        <div className="side-panel-backdrop" role="presentation">
          <aside
            aria-label="Bảng thao tác người dùng"
            className="side-panel"
            role="dialog"
          >
            <div className="side-panel-header">
              <div>
                <h3>{panelTitle(panelMode)}</h3>
                <p className="muted">{panelSubtitle(panelMode)}</p>
              </div>
              <button onClick={closePanel} type="button">
                Đóng
              </button>
            </div>

            {panelMode === "view" && activeUser && (
              <UserDetailPanel
                onEdit={() => openEditPanel(activeUser)}
                onToggleActive={() => void handleToggleActive(activeUser)}
                user={activeUser}
              />
            )}

            {panelMode === "create" && (
              <UserForm
                form={form}
                loading={loading}
                mode="create"
                onChange={setForm}
                onSubmit={handleCreate}
              />
            )}

            {panelMode === "edit" && activeUser && (
              <UserForm
                form={form}
                loading={loading}
                mode="edit"
                onChange={setForm}
                onSubmit={handleEdit}
                user={activeUser}
              />
            )}
          </aside>
        </div>
      )}
    </section>
  );
}

function UserForm({
  form,
  loading,
  mode,
  onChange,
  onSubmit,
  user,
}: {
  form: UserFormState;
  loading: boolean;
  mode: "create" | "edit";
  onChange: (next: UserFormState) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  user?: UserPublic;
}) {
  return (
    <form className="side-panel-form" onSubmit={onSubmit}>
      {mode === "edit" && user && (
        <label>
          Tên đăng nhập
          <input disabled value={user.username} />
        </label>
      )}
      {mode === "create" && (
        <label>
          Tên đăng nhập
          <input
            onChange={(event) => onChange({ ...form, username: event.target.value })}
            required
            value={form.username}
          />
        </label>
      )}
      <label>
        Họ tên
        <input
          onChange={(event) => onChange({ ...form, full_name: event.target.value })}
          required
          value={form.full_name}
        />
      </label>
      <label>
        Vai trò
        <select
          onChange={(event) =>
            onChange({ ...form, role: event.target.value as UserRole })
          }
          value={form.role}
        >
          {roles.map((role) => (
            <option key={role} value={role}>
              {roleLabel(role)}
            </option>
          ))}
        </select>
      </label>
      <label>
        {mode === "create" ? "Mật khẩu" : "Mật khẩu mới"}
        <input
          onChange={(event) => onChange({ ...form, password: event.target.value })}
          placeholder={mode === "edit" ? "Bỏ trống nếu không đổi" : undefined}
          required={mode === "create"}
          type="password"
          value={form.password}
        />
      </label>
      <button className="primary" disabled={loading} type="submit">
        {loading
          ? "Đang lưu..."
          : mode === "create"
            ? "Tạo người dùng"
            : "Lưu thay đổi"}
      </button>
    </form>
  );
}

function UserDetailPanel({
  onEdit,
  onToggleActive,
  user,
}: {
  onEdit: () => void;
  onToggleActive: () => void;
  user: UserPublic;
}) {
  return (
    <div className="user-detail-panel">
      <dl className="detail-list compact">
        <div>
          <dt>Tên đăng nhập</dt>
          <dd>{user.username}</dd>
        </div>
        <div>
          <dt>Họ tên</dt>
          <dd>{user.full_name}</dd>
        </div>
        <div>
          <dt>Vai trò</dt>
          <dd>{roleLabel(user.role)}</dd>
        </div>
        <div>
          <dt>Trạng thái</dt>
          <dd>
            <StatusBadge value={user.is_active ? "active" : "inactive"} />
          </dd>
        </div>
        <div>
          <dt>Mã người dùng</dt>
          <dd title={user.user_id}>{compactId(user.user_id)}</dd>
        </div>
        <div>
          <dt>Ngày tạo</dt>
          <dd>{formatDateTime(user.created_at)}</dd>
        </div>
      </dl>
      <div className="actions">
        <button className="primary" onClick={onEdit} type="button">
          Sửa
        </button>
        <button
          className={user.is_active ? "danger" : "primary"}
          onClick={onToggleActive}
          type="button"
        >
          {user.is_active ? "Khóa tài khoản" : "Mở khóa tài khoản"}
        </button>
      </div>
    </div>
  );
}

function formFromUser(user: UserPublic): UserFormState {
  return {
    username: user.username,
    password: "",
    full_name: user.full_name,
    role: user.role,
  };
}

function panelTitle(mode: PanelMode): string {
  if (mode === "create") {
    return "Thêm người dùng";
  }
  if (mode === "edit") {
    return "Sửa tài khoản";
  }
  return "Thông tin người dùng";
}

function panelSubtitle(mode: PanelMode): string {
  if (mode === "create") {
    return "Tạo tài khoản mới cho bác sĩ/KTV hoặc quản trị viên.";
  }
  if (mode === "edit") {
    return "Cập nhật họ tên, vai trò hoặc đặt mật khẩu mới nếu cần.";
  }
  return "Xem thông tin tài khoản, không hiển thị mật khẩu hay mã băm mật khẩu.";
}
