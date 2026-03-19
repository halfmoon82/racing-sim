import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Flag, AlertTriangle } from 'lucide-react';

const LoginPage: React.FC = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const { login, user } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    const reason = sessionStorage.getItem('logout_reason');
    if (reason) {
      setInfo(reason);
      sessionStorage.removeItem('logout_reason');
    }
  }, []);

  useEffect(() => {
    if (user) {
      navigate(`/${user.role}`, { replace: true });
    }
  }, [user, navigate]);

  if (user) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      await login(username, password);
    } catch (err: any) {
      const data = err?.response?.data;
      const msg =
        (data && typeof data === 'object' && 'detail' in data ? (data as any).detail : null) ||
        (typeof data === 'string' ? data : null) ||
        `Login failed`;
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-racing-bg to-racing-dark flex items-center justify-center p-4 racing-shell">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="flex justify-center mb-4">
            <Flag className="w-16 h-16 text-racing-red" />
          </div>
          <h1 className="text-3xl font-bold text-white mb-2">
            赛车策略仿真实验室
          </h1>
          <p className="text-racing-gray text-sm">
            Racing Strategy Simulation Lab
          </p>
        </div>

        {/* Login Form */}
        <div className="racing-card">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-racing-gray mb-2">
                用户名 / Username
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="racing-input w-full"
                placeholder="Enter your username"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-racing-gray mb-2">
                密码 / Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="racing-input w-full"
                placeholder="Enter your password"
                required
              />
            </div>

            {info && (
              <div className="flex items-center gap-2 text-racing-gold text-sm bg-yellow-900/20 p-3 rounded">
                <AlertTriangle className="w-4 h-4" />
                <span>{info}</span>
              </div>
            )}

            {error && (
              <div className="flex items-center gap-2 text-racing-red text-sm bg-red-900/20 p-3 rounded">
                <AlertTriangle className="w-4 h-4" />
                <span>{error}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={isLoading}
              className="racing-btn-primary w-full"
            >
              {isLoading ? 'LOADING...' : 'ENTER COCKPIT / 进入驾驶舱'}
            </button>
          </form>
        </div>

        {/* Footer */}
        <div className="text-center mt-8 text-racing-gray text-xs">
          <p>Business School Racing Simulation v5.0</p>
          <p className="mt-1">广东国际赛车场 | GIC 2820m</p>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
