import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useAuth } from '../contexts/AuthContext';
import { 
  Users, Play, Square, Settings, RefreshCw, 
  ChevronRight, Circle, Trophy, ArrowUpDown, ArrowUp, ArrowDown, Key
} from 'lucide-react';
import PasswordResetModal from '../components/PasswordResetModal';

import { API_BASE_URL } from '../lib/apiBase';

const API_URL = API_BASE_URL;

const TeacherDashboard: React.FC = () => {
  const { user, logout } = useAuth();
  const [dashboard, setDashboard] = useState<any>(null);
  const [roundName, setRoundName] = useState('');
  const [maxAttempts, setMaxAttempts] = useState(5);
  const [isCreating, setIsCreating] = useState(false);
  const [roundSummary, setRoundSummary] = useState<any>(null);
  const [summaryExpanded, setSummaryExpanded] = useState(false);

  // Sorting state
  const [monitorSortBy, setMonitorSortBy] = useState<'status' | 'driver' | 'attempts' | 'best'>("best");
  const [monitorSortOrder, setMonitorSortOrder] = useState<'asc' | 'desc'>("asc");

  const [summarySortBy, setSummarySortBy] = useState<'student' | 'attempts' | 'best'>("best");
  const [summarySortOrder, setSummarySortOrder] = useState<'asc' | 'desc'>("asc");

  // Password Reset Modal State
  const [showResetModal, setShowResetModal] = useState(false);
  const [resetStudentName, setResetStudentName] = useState('');
  const [resetPassword, setResetPassword] = useState('');

  useEffect(() => {
    fetchDashboard();
    fetchRoundSummary();
    const interval = setInterval(fetchDashboard, 5000);
    return () => clearInterval(interval);
  }, []);

  const fetchDashboard = async () => {
    try {
      const res = await axios.get(`${API_URL}/api/teacher/dashboard`);
      setDashboard(res.data);
    } catch (err: any) {
      const statusCode = err.response?.status;
      if (statusCode === 401) {
        // teacher session invalidated (e.g., sessions table cleared) → force logout
        sessionStorage.setItem('logout_reason', '当前会话被终止');
        await logout();
        return;
      }
      console.error('Failed to fetch dashboard');
    }
  };

  const fetchRoundSummary = async () => {
    try {
      const res = await axios.get(`${API_URL}/api/teacher/rounds/summary`);
      setRoundSummary(res.data);
    } catch (err: any) {
      const statusCode = err.response?.status;
      if (statusCode === 401) {
        sessionStorage.setItem('logout_reason', '当前会话被终止');
        await logout();
        return;
      }
      console.error('Failed to fetch round summary');
    }
  };

  const downloadBestStrategy = async (recordId: number, filenameHint: string) => {
    try {
      const res = await axios.get(`${API_URL}/api/teacher/records/${recordId}/best-strategy`, {
        responseType: 'blob'
      });
      const blob = new Blob([res.data], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filenameHint || `best_strategy_record_${recordId}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert('下载策略失败');
    }
  };

  const toggleMonitorSort = (field: 'status' | 'driver' | 'attempts' | 'best') => {
    if (monitorSortBy === field) {
      setMonitorSortOrder(prev => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setMonitorSortBy(field);
      // default orders
      setMonitorSortOrder(field === 'driver' ? 'asc' : 'asc');
    }
  };

  const toggleSummarySort = (field: 'student' | 'attempts' | 'best') => {
    if (summarySortBy === field) {
      setSummarySortOrder(prev => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSummarySortBy(field);
      setSummarySortOrder(field === 'student' ? 'asc' : 'asc');
    }
  };

  const sortedMonitorStudents = React.useMemo(() => {
    const arr = [...(dashboard?.students || [])];

    const getBest = (s: any) => (typeof s?.best_time === 'number' ? s.best_time : null);
    const getAttempts = (s: any) => Number(s?.used_attempts ?? 0);
    const getDriver = (s: any) => String(s?.display_name ?? s?.username ?? '');
    const getStatus = (s: any) => (s?.online ? 1 : 0); // online first when desc

    arr.sort((a, b) => {
      let av: any, bv: any;
      switch (monitorSortBy) {
        case 'status':
          av = getStatus(a); bv = getStatus(b);
          break;
        case 'driver':
          av = getDriver(a).toLowerCase(); bv = getDriver(b).toLowerCase();
          break;
        case 'attempts':
          av = getAttempts(a); bv = getAttempts(b);
          break;
        case 'best':
        default:
          // best: nulls last
          av = getBest(a); bv = getBest(b);
          av = av === null ? Infinity : av;
          bv = bv === null ? Infinity : bv;
          break;
      }
      if (av < bv) return monitorSortOrder === 'asc' ? -1 : 1;
      if (av > bv) return monitorSortOrder === 'asc' ? 1 : -1;
      return 0;
    });

    return arr;
  }, [dashboard?.students, monitorSortBy, monitorSortOrder]);

  const sortIcon = (active: boolean, order: 'asc' | 'desc') => {
    if (!active) return <ArrowUpDown className="w-3 h-3" />;
    return order === 'asc' ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />;
  };

  const createRound = async () => {
    setIsCreating(true);
    try {
      await axios.post(`${API_URL}/api/teacher/rounds`, {
        name: roundName || `Round ${(dashboard?.current_round?.number || 0) + 1}`,
        max_attempts: maxAttempts
      });
      setRoundName('');
      fetchDashboard();
    } catch (e) {
      alert('Failed to create round');
    } finally {
      setIsCreating(false);
    }
  };

  const stopRound = async () => {
    if (!confirm('确定要停止当前轮次吗？所有进行中的提交将被终止。')) return;
    try {
      await axios.post(`${API_URL}/api/teacher/rounds/${dashboard.current_round.id}/stop`);
      fetchDashboard();
    } catch (e) {
      alert('Failed to stop round');
    }
  };

  // 重置学生密码 - 使用PasswordResetModal
  const resetStudentPassword = async (studentId: number, studentName: string) => {
    if (!confirm(`确定要重置学生 "${studentName}" 的密码吗？\nAre you sure you want to reset password for "${studentName}"?`)) {
      return;
    }

    try {
      const res = await axios.post(`${API_URL}/api/teacher/students/${studentId}/reset-password`);
      const newPassword = res.data.new_password;
      
      // 打开弹窗显示密码
      setResetPassword(newPassword);
      setResetStudentName(studentName);
      setShowResetModal(true);
    } catch (e: any) {
      alert(e.response?.data?.detail || '重置密码失败');
    }
  };

  const handleCloseResetModal = () => {
    setShowResetModal(false);
    setResetPassword('');
    setResetStudentName('');
  };

  return (
    <div className="min-h-screen bg-racing-bg racing-shell">
      {/* Password Reset Modal */}
      <PasswordResetModal
        isOpen={showResetModal}
        onClose={handleCloseResetModal}
        userName={resetStudentName}
        userType="学生 | Student"
        newPassword={resetPassword}
      />

      {/* Header */}
      <header className="bg-racing-card border-b border-gray-800">
        <div className="max-w-7xl mx-auto px-4 py-4 flex justify-between items-center">
          <div className="flex items-center gap-4">
            <Settings className="w-8 h-8 text-racing-red" />
            <div>
              <h1 className="text-xl font-bold text-white">赛事控制中心 | Race Control</h1>
              <p className="text-sm text-racing-gray">{user?.display_name}</p>
            </div>
          </div>
          <button onClick={logout} className="racing-btn-secondary text-sm">
            退出 | Logout
          </button>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Round Control */}
          <div className="lg:col-span-1 space-y-4">
            <div className="racing-card">
              <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                <Play className="w-5 h-5 text-racing-red" />
                轮次管理 | Round Control
              </h2>

              {dashboard?.current_round?.is_active ? (
                <div className="space-y-4">
                  <div className="bg-racing-dark p-4 rounded-lg">
                    <div className="text-sm text-racing-gray">当前轮次 | Current</div>
                    <div className="text-2xl font-bold text-white">
                      Round {dashboard.current_round.number}
                    </div>
                    <div className="text-racing-red font-medium">{dashboard.current_round.name}</div>
                    <div className="mt-2 flex items-center gap-2">
                      <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                      <span className="text-green-500 text-sm">进行中 | ACTIVE</span>
                    </div>
                  </div>
                  <button
                    onClick={stopRound}
                    className="w-full racing-btn bg-red-600 hover:bg-red-700 text-white py-3 flex items-center justify-center gap-2"
                  >
                    <Square className="w-4 h-4" />
                    强制停止 | STOP SESSION
                  </button>
                </div>
              ) : (
                <div className="space-y-4">
                  <div>
                    <label className="text-sm text-racing-gray block mb-2">轮次名称 | Name</label>
                    <input
                      type="text"
                      value={roundName}
                      onChange={(e) => setRoundName(e.target.value)}
                      placeholder={`Round ${(dashboard?.current_round?.number || 0) + 1}`}
                      className="racing-input w-full"
                    />
                  </div>
                  <div>
                    <label className="text-sm text-racing-gray block mb-2">
                      最大尝试次数 | Max Attempts
                    </label>
                    <input
                      type="number"
                      value={maxAttempts}
                      onChange={(e) => setMaxAttempts(parseInt(e.target.value))}
                      min={1}
                      max={20}
                      className="racing-input w-full"
                    />
                  </div>
                  <button
                    onClick={createRound}
                    disabled={isCreating}
                    className="w-full racing-btn-primary py-3 flex items-center justify-center gap-2"
                  >
                    <Play className="w-4 h-4" />
                    {isCreating ? '创建中...' : '开启新轮次 | START ROUND'}
                  </button>
                </div>
              )}
            </div>

            {/* Quick Stats */}
            <div className="racing-card">
              <h3 className="text-white font-bold mb-4">实时统计 | Live Stats</h3>
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-racing-dark p-3 rounded-lg text-center">
                  <div className="text-2xl font-bold text-racing-gold">
                    {dashboard?.students?.filter((s: any) => s.online).length || 0}
                  </div>
                  <div className="text-xs text-racing-gray">在线 | Online</div>
                </div>
                <div className="bg-racing-dark p-3 rounded-lg text-center">
                  <div className="text-2xl font-bold text-white">
                    {dashboard?.students?.length || 0}
                  </div>
                  <div className="text-xs text-racing-gray">总人数 | Total</div>
                </div>
              </div>
            </div>
          </div>

          {/* Student Monitor */}
          <div className="lg:col-span-2 space-y-4">

            {/* Round Summary */}
            <div className="racing-card">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-bold text-white flex items-center gap-2">
                  <Trophy className="w-5 h-5 text-racing-gold" />
                  历史轮次总结 | Round Summary
                </h2>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setSummaryExpanded(v => !v)}
                    className="racing-btn-secondary text-sm"
                  >
                    {summaryExpanded ? '收起 | Collapse' : '展开 | Expand'}
                  </button>
                  <button
                    onClick={fetchRoundSummary}
                    className="racing-btn-secondary text-sm flex items-center gap-2"
                    title="刷新"
                  >
                    <RefreshCw className="w-4 h-4" />
                    刷新
                  </button>
                </div>
              </div>

              {!summaryExpanded ? (
                <div className="text-racing-gray text-sm">已加载 {roundSummary?.rounds?.length || 0} 轮。点击展开查看每轮每位学生统计。</div>
              ) : (
                <div className="space-y-4">
                  {(roundSummary?.rounds || []).map((r: any) => (
                    <div key={r.round_id} className="bg-racing-dark border border-gray-800 rounded-lg p-3">
                      <div className="flex items-center justify-between mb-3">
                        <div>
                          <div className="text-white font-bold">Round {r.round_number}</div>
                          <div className="text-xs text-racing-gray">max_attempts: {r.max_attempts} {r.is_active ? '🟢 ACTIVE' : '🔴 ENDED'}</div>
                        </div>
                      </div>

                      <div className="overflow-x-auto">
                        <table className="w-full">
                          <thead>
                            <tr className="text-left text-racing-gray text-xs border-b border-gray-800">
                              <th className="pb-2 px-2">
                                <button
                                  onClick={() => toggleSummarySort('student')}
                                  className={`flex items-center gap-1 ${summarySortBy === 'student' ? 'text-white' : ''}`}
                                >
                                  学生
                                  {sortIcon(summarySortBy === 'student', summarySortOrder)}
                                </button>
                              </th>
                              <th className="pb-2 px-2">
                                <button
                                  onClick={() => toggleSummarySort('attempts')}
                                  className={`flex items-center gap-1 ${summarySortBy === 'attempts' ? 'text-white' : ''}`}
                                >
                                  Attempts
                                  {sortIcon(summarySortBy === 'attempts', summarySortOrder)}
                                </button>
                              </th>
                              <th className="pb-2 px-2">
                                <button
                                  onClick={() => toggleSummarySort('best')}
                                  className={`flex items-center gap-1 ${summarySortBy === 'best' ? 'text-white' : ''}`}
                                >
                                  Best Lap
                                  {sortIcon(summarySortBy === 'best', summarySortOrder)}
                                </button>
                              </th>
                              <th className="pb-2 px-2">Best Strategy</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(() => {
                              const students = [...(r.students || [])];
                              students.sort((a: any, b: any) => {
                                let av: any, bv: any;
                                if (summarySortBy === 'student') {
                                  av = String(a.display_name || a.username || '').toLowerCase();
                                  bv = String(b.display_name || b.username || '').toLowerCase();
                                } else if (summarySortBy === 'attempts') {
                                  av = Number(a.attempts ?? 0);
                                  bv = Number(b.attempts ?? 0);
                                } else {
                                  // best: nulls last
                                  av = (a.best_time === null || a.best_time === undefined) ? Infinity : Number(a.best_time);
                                  bv = (b.best_time === null || b.best_time === undefined) ? Infinity : Number(b.best_time);
                                }
                                if (av < bv) return summarySortOrder === 'asc' ? -1 : 1;
                                if (av > bv) return summarySortOrder === 'asc' ? 1 : -1;
                                return 0;
                              });
                              return students.map((s: any) => (
                              <tr key={`${r.round_id}-${s.student_id}`} className="border-b border-gray-800/50">
                                <td className="py-2 px-2">
                                  <div className="text-white text-sm">{s.display_name}</div>
                                  <div className="text-xs text-racing-gray">{s.username}</div>
                                </td>
                                <td className="py-2 px-2 text-white text-sm">{s.attempts}</td>
                                <td className="py-2 px-2">
                                  {s.best_time ? (
                                    <span className="text-racing-gold font-mono text-sm">{Number(s.best_time).toFixed(2)}s</span>
                                  ) : (
                                    <span className="text-gray-600 text-sm">-</span>
                                  )}
                                </td>
                                <td className="py-2 px-2">
                                  {s.best_record_id ? (
                                    <button
                                      onClick={() => downloadBestStrategy(s.best_record_id, `BestStrategy-${s.username}-Round_${r.round_number}.csv`)}
                                      className="racing-btn-secondary text-xs px-2 py-1"
                                    >
                                      下载策略
                                    </button>
                                  ) : (
                                    <span className="text-gray-600 text-sm">-</span>
                                  )}
                                </td>
                              </tr>
                            ));
                            })()}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="racing-card">
              <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                <Users className="w-5 h-5 text-racing-red" />
                车手监控墙 | Driver Monitor
              </h2>

              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="text-left text-racing-gray text-sm border-b border-gray-800">
                      <th className="pb-3 px-3">
                        <button
                          onClick={() => toggleMonitorSort('status')}
                          className={`flex items-center gap-1 ${monitorSortBy === 'status' ? 'text-white' : ''}`}
                        >
                          状态
                          {sortIcon(monitorSortBy === 'status', monitorSortOrder)}
                        </button>
                      </th>
                      <th className="pb-3 px-3">
                        <button
                          onClick={() => toggleMonitorSort('driver')}
                          className={`flex items-center gap-1 ${monitorSortBy === 'driver' ? 'text-white' : ''}`}
                        >
                          车手 | Driver
                          {sortIcon(monitorSortBy === 'driver', monitorSortOrder)}
                        </button>
                      </th>
                      <th className="pb-3 px-3">
                        <button
                          onClick={() => toggleMonitorSort('attempts')}
                          className={`flex items-center gap-1 ${monitorSortBy === 'attempts' ? 'text-white' : ''}`}
                        >
                          提交次数 | Attempts
                          {sortIcon(monitorSortBy === 'attempts', monitorSortOrder)}
                        </button>
                      </th>
                      <th className="pb-3 px-3">
                        <button
                          onClick={() => toggleMonitorSort('best')}
                          className={`flex items-center gap-1 ${monitorSortBy === 'best' ? 'text-white' : ''}`}
                        >
                          最佳圈速 | Best Lap
                          {sortIcon(monitorSortBy === 'best', monitorSortOrder)}
                        </button>
                      </th>
                      <th className="pb-3 px-3">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedMonitorStudents.map((student: any) => (
                      <tr key={student.id} className="border-b border-gray-800/50">
                        <td className="py-3 px-3">
                          {student.online ? (
                            <div className="flex items-center gap-2 text-green-500">
                              <Circle className="w-3 h-3 fill-current" />
                              <span className="text-sm">在线</span>
                            </div>
                          ) : (
                            <div className="flex items-center gap-2 text-gray-600">
                              <Circle className="w-3 h-3" />
                              <span className="text-sm">离线</span>
                            </div>
                          )}
                        </td>
                        <td className="py-3 px-3">
                          <div className="text-white font-medium">{student.display_name}</div>
                          <div className="text-xs text-racing-gray">{student.username}</div>
                        </td>
                        <td className="py-3 px-3">
                          <div className="text-white">
                            {student.used_attempts} / {dashboard?.current_round?.max_attempts || '-'}
                          </div>
                          <div className="w-24 h-1 bg-gray-800 rounded-full mt-1">
                            <div 
                              className="h-full bg-racing-red rounded-full"
                              style={{ 
                                width: `${(student.used_attempts / (dashboard?.current_round?.max_attempts || 1)) * 100}%` 
                              }}
                            />
                          </div>
                        </td>
                        <td className="py-3 px-3">
                          {student.best_time ? (
                            <div className="flex items-center gap-2">
                              <Trophy className="w-4 h-4 text-racing-gold" />
                              <span className="text-racing-gold font-mono font-bold">
                                {student.best_time.toFixed(2)}s
                              </span>
                            </div>
                          ) : (
                            <span className="text-gray-600">-</span>
                          )}
                        </td>
                        <td className="py-3 px-3">
                          <div className="flex flex-wrap gap-2">
                            <button
                              onClick={() => resetStudentPassword(student.id, student.display_name)}
                              className="text-xs racing-btn-secondary py-1 px-2 flex items-center gap-1"
                              title="重置密码 | Reset Password"
                            >
                              <Key className="w-3 h-3" />
                              重置密码
                            </button>

                            <button
                              onClick={async () => {
                                if (!confirm(`确定释放 ${student.display_name} 的驾驶舱占用态吗？`)) return;
                                try {
                                  await axios.post(`${API_URL}/api/teacher/students/${student.id}/release-session`);
                                  alert('已释放');
                                  fetchDashboard();
                                } catch (e: any) {
                                  const msg = e?.response?.data?.detail || '释放失败';
                                  alert(msg);
                                }
                              }}
                              className="text-xs racing-btn-secondary py-1 px-2"
                            >
                              释放登录态
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TeacherDashboard;
