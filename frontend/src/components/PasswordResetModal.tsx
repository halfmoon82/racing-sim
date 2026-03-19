import React, { useState } from 'react';
import { X, Copy, Eye, EyeOff, AlertTriangle } from 'lucide-react';

interface PasswordResetModalProps {
  isOpen: boolean;
  onClose: () => void;
  userName: string;
  userType: string;
  newPassword: string;
}

const PasswordResetModal: React.FC<PasswordResetModalProps> = ({ 
  isOpen, 
  onClose, 
  userName, 
  userType,
  newPassword 
}) => {
  const [showPassword, setShowPassword] = useState(false);
  const [copied, setCopied] = useState(false);

  if (!isOpen) return null;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(newPassword);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const handleClose = () => {
    // 关闭时清除密码显示状态
    setShowPassword(false);
    setCopied(false);
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-racing-card border border-racing-gray rounded-lg max-w-md w-full p-6 shadow-2xl">
        {/* Header */}
        <div className="flex justify-between items-start mb-4">
          <div className="flex items-center gap-2">
            <div className="p-2 bg-racing-red/20 rounded-lg">
              <AlertTriangle className="w-6 h-6 text-racing-red" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-white">密码重置成功</h3>
              <p className="text-xs text-racing-gray">Password Reset Successful</p>
            </div>
          </div>
          <button 
            onClick={handleClose} 
            className="text-racing-gray hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Warning Banner */}
        <div className="bg-yellow-900/30 border border-yellow-600/50 rounded-lg p-3 mb-4">
          <p className="text-yellow-500 text-sm">
            <strong>⚠️ 重要提示 | Important:</strong><br />
            此密码只显示一次，关闭后将无法再次查看！<br />
            <span className="text-xs">This password will only be shown once.</span>
          </p>
        </div>

        {/* User Info */}
        <div className="mb-4">
          <label className="text-xs text-racing-gray block mb-1">
            {userType} | User
          </label>
          <div className="text-white font-medium text-lg">{userName}</div>
        </div>

        {/* Password Display */}
        <div className="mb-6">
          <label className="text-xs text-racing-gray block mb-2">
            新密码 | New Password
          </label>
          <div className="flex items-center gap-2">
            <div className="flex-1 relative">
              <input
                type={showPassword ? 'text' : 'password'}
                value={newPassword}
                readOnly
                className="w-full bg-racing-dark border border-racing-gray rounded px-3 py-2.5 text-white font-mono text-sm focus:outline-none focus:border-racing-red"
              />
            </div>
            <button
              onClick={() => setShowPassword(!showPassword)}
              className="p-2.5 bg-racing-dark border border-racing-gray rounded text-racing-gray hover:text-white hover:border-racing-gray transition-colors"
              title={showPassword ? '隐藏密码 | Hide' : '显示密码 | Show'}
            >
              {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex gap-3">
          <button
            onClick={handleCopy}
            className={`flex-1 py-2.5 rounded font-medium flex items-center justify-center gap-2 transition-all ${
              copied
                ? 'bg-green-600 text-white'
                : 'bg-racing-gray hover:bg-gray-600 text-white'
            }`}
          >
            <Copy className="w-4 h-4" />
            {copied ? '已复制 | Copied!' : '复制密码 | Copy'}
          </button>
          <button
            onClick={handleClose}
            className="flex-1 py-2.5 bg-racing-red hover:bg-red-700 text-white rounded font-medium transition-colors"
          >
            关闭 | Close
          </button>
        </div>

        {/* Footer Warning */}
        <p className="mt-4 text-xs text-racing-gray text-center">
          关闭此窗口后密码将无法再次查看<br />
          Password cannot be viewed again after closing
        </p>
      </div>
    </div>
  );
};

export default PasswordResetModal;
