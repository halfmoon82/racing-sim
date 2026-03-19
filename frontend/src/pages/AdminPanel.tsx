import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useAuth } from '../contexts/AuthContext';
import { Shield, UserPlus, Trash2, AlertTriangle, CheckCircle, Key } from 'lucide-react';
import PasswordResetModal from '../components/PasswordResetModal';

import { API_BASE_URL } from '../lib/apiBase';

const API_URL = API_BASE_URL;

const AdminPanel: React.FC = () => {
  const { user, logout } = useAuth();
  const token = user?.token;
  const [teachers, setTeachers] = useState<any[]>([]);
  const [newTeacher, setNewTeacher] = useState({ username: '', password: '', display_name: '' });
  const [resetConfirm, setResetConfirm] = useState('');
  const [message, setMessage] = useState('');

  // Password Reset Modal State
  const [showResetModal, setShowResetModal] = useState(false);
  const [resetTeacherName, setResetTeacherName] = useState('');
  const [resetPassword, setResetPassword] = useState('');

  // 获取教师列表
  const fetchTeachers = async () => {
    if (!token) {
      console.log('No token, skipping fetch');
      return;
    }
    try {
      console.log('Fetching teachers with token');
      const res = await axios.get(`${API_URL}/api/admin/teachers`, { 
        headers: { Authorization: `Bearer ${token}` } 
      });
      console.log('Teachers:', res.data);
      setTeachers(res.data.teachers || []);
    } catch (e: any) {
      console.error('Failed to fetch teachers:', e?.response?.data || e);
    }
  };

  // 页面加载时获取教师列表
  useEffect(() => {
    fetchTeachers();
  }, [token]);

  const createTeacher = async () => {
    try {
      await axios.post(`${API_URL}/api/admin/teachers`, newTeacher, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });
      setMessage('Teacher created successfully');
      setNewTeacher({ username: '', password: '', display_name: '' });
      fetchTeachers();
    } catch (e: any) {
      setMessage(e.response?.data?.detail || 'Failed to create teacher');
    }
  };

  // 重置教师密码 - 使用专业弹窗组件
  const resetTeacherPassword = async (teacherId: number, teacherName: string) => {
    if (!confirm(`确定要重置教师 "${teacherName}" 的密码吗？\nAre you sure you want to reset password for "${teacherName}"?`)) {
      return;
    }

    try {
      const res = await axios.post(`${API_URL}/api/admin/teachers/${teacherId}/reset-password`, {}, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });
      const newPassword = res.data.new_password;
      
      // 打开弹窗显示密码
      setResetPassword(newPassword);
      setResetTeacherName(teacherName);
      setShowResetModal(true);
      
      setMessage('Password reset successful');
    } catch (e: any) {
      setMessage(e.response?.data?.detail || 'Failed to reset password');
    }
  };

  const handleCloseResetModal = () => {
    // 关闭时清除密码，确保不再显示
    setShowResetModal(false);
    setResetPassword('');
    setResetTeacherName('');
  };

  const resetSystem = async () => {
    if (resetConfirm !== 'CONFIRM RESET') {
      setMessage('Please type "CONFIRM RESET" to proceed');
      return;
    }
    
    if (!confirm('⚠️ DANGER: This will delete ALL data including records and rounds. This action cannot be undone. Continue?')) {
      return;
    }

    try {
      const res = await axios.post(`${API_URL}/api/admin/reset-system`, {
        confirmation: resetConfirm
      });
      setMessage(res.data.message);
      setResetConfirm('');
    } catch (e: any) {
      setMessage(e.response?.data?.detail || 'Reset failed');
    }
  };

  return (
    <div className="min-h-screen bg-racing-bg racing-shell">
      {/* Password Reset Modal */}
      <PasswordResetModal
        isOpen={showResetModal}
        onClose={handleCloseResetModal}
        userName={resetTeacherName}
        userType="教师 | Teacher"
        newPassword={resetPassword}
      />

      {/* Header */}
      <header className="bg-racing-card border-b border-gray-800">
        <div className="max-w-7xl mx-auto px-4 py-4 flex justify-between items-center">
          <div className="flex items-center gap-4">
            <Shield className="w-8 h-8 text-racing-red" />
            <div>
              <h1 className="text-xl font-bold text-white">系统管理 | Admin Panel</h1>
              <p className="text-sm text-racing-gray">{user?.display_name}</p>
            </div>
          </div>
          <button onClick={logout} className="racing-btn-secondary text-sm">
            退出 | Logout
          </button>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 py-6">
        {message && (
          <div className="mb-6 p-4 bg-green-900/20 border border-green-600 rounded-lg flex items-center gap-2 text-green-500">
            <CheckCircle className="w-5 h-5" />
            {message}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Teacher Management */}
          <div className="racing-card">
            <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
              <UserPlus className="w-5 h-5 text-racing-red" />
              Teacher 管理
            </h2>

            {/* Create Teacher */}
            <div className="space-y-4 mb-6">
              <input
                type="text"
                placeholder="Username"
                value={newTeacher.username}
                onChange={(e) => setNewTeacher({...newTeacher, username: e.target.value})}
                className="racing-input w-full"
              />
              <input
                type="password"
                placeholder="Password"
                value={newTeacher.password}
                onChange={(e) => setNewTeacher({...newTeacher, password: e.target.value})}
                className="racing-input w-full"
              />
              <input
                type="text"
                placeholder="Display Name"
                value={newTeacher.display_name}
                onChange={(e) => setNewTeacher({...newTeacher, display_name: e.target.value})}
                className="racing-input w-full"
              />
              <button onClick={createTeacher} className="racing-btn-primary w-full">
                创建 Teacher 账号
              </button>
            </div>

            {/* Teacher List */}
            <div className="space-y-2">
              <h3 className="text-sm font-medium text-racing-gray">现有账号</h3>
              {teachers.map((t) => (
                <div key={t.id} className="flex justify-between items-center p-3 bg-racing-dark rounded">
                  <div className="flex-1">
                    <div className="text-white font-medium">{t.display_name}</div>
                    <div className="text-xs text-racing-gray">{t.username}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs px-2 py-1 rounded ${t.is_active ? 'bg-green-900/50 text-green-500' : 'bg-gray-800 text-gray-500'}`}>
                      {t.is_active ? 'Active' : 'Inactive'}
                    </span>
                    <button
                      onClick={() => resetTeacherPassword(t.id, t.display_name)}
                      className="p-1.5 text-racing-gray hover:text-racing-red hover:bg-red-900/20 rounded transition-colors"
                      title="重置密码 | Reset Password"
                    >
                      <Key className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Danger Zone */}
          <div className="racing-card border-red-900/50 border-2">
            <h2 className="text-lg font-bold text-red-500 mb-4 flex items-center gap-2">
              <AlertTriangle className="w-5 h-5" />
              危险区域 | Danger Zone
            </h2>
            <p className="text-racing-gray mb-4">
              全局重置将删除所有测试数据和轮次记录，系统恢复到初始状态。此操作不可恢复！
            </p>
            <p className="text-racing-gray mb-4 text-sm">
              Global Reset will delete ALL records and rounds. System will return to initial state. This cannot be undone!
            </p>

            <div className="bg-red-950/30 p-4 rounded-lg space-y-4">
              <div>
                <label className="text-sm text-red-400 block mb-2">
                  输入 "CONFIRM RESET" 以确认
                </label>
                <input
                  type="text"
                  value={resetConfirm}
                  onChange={(e) => setResetConfirm(e.target.value)}
                  placeholder="CONFIRM RESET"
                  className="racing-input w-full border-red-900 focus:border-red-500"
                />
              </div>
              <button
                onClick={resetSystem}
                className="w-full py-3 bg-red-600 hover:bg-red-700 text-white rounded font-bold flex items-center justify-center gap-2"
              >
                <Trash2 className="w-5 h-5" />
                RESET ALL ROUNDS & DATA
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AdminPanel;
