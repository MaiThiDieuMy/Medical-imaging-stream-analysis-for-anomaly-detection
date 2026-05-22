import { FormEvent, useState } from "react";
import { login } from "../api/client";
import { Message } from "../components/Message";
import type { UserPublic } from "../types/api";

type LoginPageProps = {
  onLogin: (user: UserPublic) => void;
};

export function LoginPage({ onLogin }: LoginPageProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    try {
      setLoading(true);
      const response = await login({ username, password });
      onLogin(response.user);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Đăng nhập thất bại.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-screen">
      <form className="login-panel" onSubmit={handleSubmit}>
        <div className="brand-block login-brand">
          <div className="brand-mark">XR</div>
          <div>
            <h1>Medical Imaging Stream Analysis</h1>
            <span>Hệ thống phân tích ảnh X-quang lồng ngực</span>
          </div>
        </div>
        <div>
          <h2>Đăng nhập</h2>
          <p className="muted">
            Đăng nhập bằng tài khoản Bác sĩ/KTV hoặc Quản trị viên.
          </p>
        </div>
        {error && <Message tone="error">{error}</Message>}
        <label>
          Tên đăng nhập
          <input
            autoComplete="username"
            onChange={(event) => setUsername(event.target.value)}
            required
            value={username}
          />
        </label>
        <label>
          Mật khẩu
          <input
            autoComplete="current-password"
            onChange={(event) => setPassword(event.target.value)}
            required
            type="password"
            value={password}
          />
        </label>
        <button className="primary" disabled={loading} type="submit">
          {loading ? "Đang đăng nhập..." : "Đăng nhập"}
        </button>
      </form>
    </main>
  );
}
