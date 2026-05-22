import { FormEvent, useEffect, useState } from "react";
import { createUser, listUsers, updateUser } from "../api/client";
import { Message } from "../components/Message";
import { StatusBadge } from "../components/StatusBadge";
import type { UserPublic, UserRole } from "../types/api";
import { compactId } from "../utils/format";
import { roleLabel } from "../utils/navigation";

const roles: UserRole[] = ["user", "admin"];

export function UserManagementPage() {
  const [users, setUsers] = useState<UserPublic[]>([]);
  const [selectedUserId, setSelectedUserId] = useState<string>("");
  const [editFullName, setEditFullName] = useState("");
  const [editRole, setEditRole] = useState<UserRole>("user");
  const [editIsActive, setEditIsActive] = useState(true);
  const [editPassword, setEditPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function refreshUsers() {
    const loadedUsers = await listUsers();
    setUsers(loadedUsers);
    if (!selectedUserId && loadedUsers.length > 0) {
      selectUser(loadedUsers[0]);
    }
  }

  useEffect(() => {
    refreshUsers().catch((exc) =>
      setError(exc instanceof Error ? exc.message : "Không tải được người dùng."),
    );
  }, []);

  function selectUser(user: UserPublic) {
    setSelectedUserId(user.user_id);
    setEditFullName(user.full_name);
    setEditRole(user.role);
    setEditIsActive(user.is_active);
    setEditPassword("");
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    const formData = new FormData(event.currentTarget);
    try {
      setLoading(true);
      await createUser({
        username: String(formData.get("username") ?? ""),
        password: String(formData.get("password") ?? ""),
        full_name: String(formData.get("full_name") ?? ""),
        role: String(formData.get("role") ?? "user") as UserRole,
      });
      event.currentTarget.reset();
      setMessage("Đã tạo người dùng.");
      await refreshUsers();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không tạo được người dùng.");
    } finally {
      setLoading(false);
    }
  }

  async function handleUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedUserId) {
      return;
    }
    setError(null);
    setMessage(null);
    try {
      setLoading(true);
      await updateUser(selectedUserId, {
        full_name: editFullName,
        role: editRole,
        is_active: editIsActive,
        ...(editPassword.trim() ? { password: editPassword } : {}),
      });
      setMessage("Đã cập nhật người dùng.");
      setEditPassword("");
      await refreshUsers();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không cập nhật được người dùng.");
    } finally {
      setLoading(false);
    }
  }

  const selectedUser = users.find((user) => user.user_id === selectedUserId);

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h2>Người dùng</h2>
          <p>
            Tạo tài khoản demo, cập nhật vai trò và khóa/mở tài khoản Bác sĩ/KTV
            hoặc Quản trị viên.
          </p>
        </div>
        <span className="count-pill">{users.length} users</span>
      </div>

      {error && <Message tone="error">{error}</Message>}
      {message && <Message tone="success">{message}</Message>}

      <div className="split-layout">
        <form className="panel form-grid" onSubmit={handleCreate}>
          <div className="form-section span-2">
            <span className="step-badge">1</span>
            <div>
              <h3>Tạo người dùng</h3>
              <p className="muted">Tài khoản mới có thể đăng nhập ngay nếu active.</p>
            </div>
          </div>
          <label>
            Username
            <input name="username" required />
          </label>
          <label>
            Mật khẩu
            <input name="password" required type="password" />
          </label>
          <label>
            Họ tên
            <input name="full_name" required />
          </label>
          <label>
            Vai trò
            <select defaultValue="user" name="role">
              {roles.map((role) => (
                <option key={role} value={role}>
                  {roleLabel(role)}
                </option>
              ))}
            </select>
          </label>
          <button className="primary span-2" disabled={loading} type="submit">
            {loading ? "Đang tạo..." : "Tạo người dùng"}
          </button>
        </form>

        <form className="panel form-grid" onSubmit={handleUpdate}>
          <div className="form-section span-2">
            <span className="step-badge">2</span>
            <div>
              <h3>Cập nhật tài khoản</h3>
              <p className="muted">Khóa tài khoản sẽ ngăn user đăng nhập và dùng token mới.</p>
            </div>
          </div>
          {selectedUser ? (
            <>
              <label className="span-2">
                Người dùng
                <select
                  onChange={(event) => {
                    const user = users.find(
                      (item) => item.user_id === event.target.value,
                    );
                    if (user) {
                      selectUser(user);
                    }
                  }}
                  value={selectedUserId}
                >
                  {users.map((user) => (
                    <option key={user.user_id} value={user.user_id}>
                      {user.username} - {roleLabel(user.role)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Họ tên
                <input
                  onChange={(event) => setEditFullName(event.target.value)}
                  required
                  value={editFullName}
                />
              </label>
              <label>
                Vai trò
                <select
                  onChange={(event) => setEditRole(event.target.value as UserRole)}
                  value={editRole}
                >
                  {roles.map((role) => (
                    <option key={role} value={role}>
                      {roleLabel(role)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="span-2">
                Mật khẩu mới
                <input
                  onChange={(event) => setEditPassword(event.target.value)}
                  placeholder="Bỏ trống nếu không đổi"
                  type="password"
                  value={editPassword}
                />
              </label>
              <label className="toggle-row span-2">
                <input
                  checked={editIsActive}
                  onChange={(event) => setEditIsActive(event.target.checked)}
                  type="checkbox"
                />
                Tài khoản đang hoạt động
              </label>
              <button className="primary span-2" disabled={loading} type="submit">
                {loading ? "Đang lưu..." : "Lưu thay đổi"}
              </button>
            </>
          ) : (
            <div className="empty-state compact span-2">
              <strong>Chưa có người dùng</strong>
              <p>Tạo người dùng đầu tiên để bắt đầu quản trị tài khoản.</p>
            </div>
          )}
        </form>
      </div>

      <div className="panel">
        <h3>Danh sách người dùng</h3>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Username</th>
                <th>Họ tên</th>
                <th>Vai trò</th>
                <th>Trạng thái</th>
                <th>User ID</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.user_id}>
                  <td>{user.username}</td>
                  <td>{user.full_name}</td>
                  <td>{roleLabel(user.role)}</td>
                  <td>
                    <StatusBadge value={user.is_active ? "active" : "inactive"} />
                  </td>
                  <td title={user.user_id}>{compactId(user.user_id)}</td>
                </tr>
              ))}
              {users.length === 0 && (
                <tr>
                  <td colSpan={5}>Chưa có người dùng.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
