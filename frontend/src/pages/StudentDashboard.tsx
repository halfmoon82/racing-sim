import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useAuth } from '../contexts/AuthContext';
import { 
  Trophy, Clock, Zap, Activity, AlertCircle, 
  Upload, Plus, Minus, Download, History, ArrowUpDown, ArrowUp, ArrowDown
} from 'lucide-react';

import { API_BASE_URL } from '../lib/apiBase';

const API_URL = API_BASE_URL;

interface LeaderboardEntry {
  rank: number;
  name: string;
  time: number;
}

interface Segment {
  now_pos: number;
  strategy: 'a' | 'b' | 'c';
  is_corner: boolean;
  turn_id?: string;
  steer_LR?: 'L' | 'R';
  steer_degree?: number;
}

const StudentDashboard: React.FC = () => {
  const { user, logout } = useAuth();
  const [status, setStatus] = useState<any>(null);
  const [segments, setSegments] = useState<Segment[]>([
    { now_pos: 0, strategy: 'a', is_corner: false }
  ]);
  const [result, setResult] = useState<any>(null);
  const [lastAttemptNumber, setLastAttemptNumber] = useState<number | null>(null);
  const [lastJobId, setLastJobId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [sortBy, setSortBy] = useState<'time' | 'lap'>('time');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  useEffect(() => {
    fetchStatus();
    fetchHistory();
    const interval = setInterval(fetchStatus, 10000);
    return () => clearInterval(interval);
  }, []);

  const fetchStatus = async () => {
    try {
      const res = await axios.get(`${API_URL}/api/student/status`);
      setStatus(res.data);
    } catch (err: any) {
      const statusCode = err.response?.status;
      const detail = err.response?.data?.detail;
      // If teacher released the session, backend will mark session inactive => 401
      if (statusCode === 401) {
        setError('当前会话被终止');
        sessionStorage.setItem('logout_reason', '当前会话被终止');
        setTimeout(() => logout(), 300);
        return;
      }
      console.error('Failed to fetch status', detail || err?.message || err);
    }
  };

  const fetchHistory = async () => {
    try {
      const res = await axios.get(`${API_URL}/api/student/history`);
      setHistory(res.data?.history || []);
    } catch (err: any) {
      const statusCode = err.response?.status;
      if (statusCode === 401) {
        setError('当前会话被终止');
        sessionStorage.setItem('logout_reason', '当前会话被终止');
        setTimeout(() => logout(), 300);
        return;
      }
      // history is non-critical
    }
  };

  const sortedHistory = React.useMemo(() => {
    const sorted = [...history];
    sorted.sort((a, b) => {
      if (sortBy === 'time') {
        const dateA = new Date(a.created_at || 0).getTime();
        const dateB = new Date(b.created_at || 0).getTime();
        return sortOrder === 'asc' ? dateA - dateB : dateB - dateA;
      } else {
        // Sort by lap time: DNF goes to bottom, then by time
        const timeA = a.is_dnf ? Infinity : (a.result_time ?? Infinity);
        const timeB = b.is_dnf ? Infinity : (b.result_time ?? Infinity);
        return sortOrder === 'asc' ? timeA - timeB : timeB - timeA;
      }
    });
    return sorted;
  }, [history, sortBy, sortOrder]);

  const toggleSort = (field: 'time' | 'lap') => {
    if (sortBy === field) {
      setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(field);
      setSortOrder(field === 'time' ? 'desc' : 'asc');
    }
  };

  const addSegment = () => {
    if (segments.length >= 50) return;
    const lastPos = segments[segments.length - 1]?.now_pos || 0;
    setSegments([...segments, { 
      now_pos: Math.min(lastPos + 100, 2820), 
      strategy: 'a', 
      is_corner: false 
    }]);
  };

  const removeSegment = (index: number) => {
    if (segments.length <= 1) return;
    setSegments(segments.filter((_, i) => i !== index));
  };

  const updateSegment = (index: number, field: keyof Segment, value: any) => {
    const updated = [...segments];
    updated[index] = { ...updated[index], [field]: value };
    
    // Auto-fill turn_id sequence if is_corner is checked
    if (field === 'is_corner' && value === true && !updated[index].turn_id) {
      const corners = ['turn1', 'turn2', 'turn4', 'turn6', 'turn7', 'turn8', 'turn10', 'turn12', 'turn13'];
      const used = updated.filter((s, i) => i < index && s.is_corner && s.turn_id).map(s => s.turn_id);
      const next = corners.find(c => !used.includes(c));
      if (next) updated[index].turn_id = next;
    }
    
    setSegments(updated);
  };

  const EXPECTED_CORNERS = ['turn1','turn2','turn4','turn6','turn7','turn8','turn10','turn12','turn13'];

  const validateCorners = (segs: Segment[]) => {
    // collect corners in appearance order
    const corners = segs
      .filter((s) => s.is_corner)
      .map((s) => ({
        turn_id: (s.turn_id || '').trim(),
        steer_LR: s.steer_LR,
        steer_degree: s.steer_degree,
      }));

    // if marked corner but missing turn_id
    const missingTurn = corners.find((c) => !c.turn_id);
    if (missingTurn) {
      setError('策略不合法：勾选“弯道”后必须选择 turn_id。');
      return false;
    }

    const seq = corners.map((c) => c.turn_id);
    if (seq.length !== EXPECTED_CORNERS.length) {
      setError(
        `策略不合法：必须包含全部9个弯道且严格按顺序。\n期望：${EXPECTED_CORNERS.join(' → ')}\n当前：${seq.join(' → ') || '(空)'}`
      );
      return false;
    }
    for (let i = 0; i < EXPECTED_CORNERS.length; i++) {
      if (seq[i] !== EXPECTED_CORNERS[i]) {
        setError(
          `策略不合法：弯道顺序必须严格匹配。\n期望：${EXPECTED_CORNERS.join(' → ')}\n当前：${seq.join(' → ')}`
        );
        return false;
      }
    }

    for (let i = 0; i < corners.length; i++) {
      const c = corners[i];
      if (c.steer_LR !== 'L' && c.steer_LR !== 'R') {
        setError(`策略不合法：${c.turn_id} 缺少转向方向（steer_LR 必须为 L 或 R）。`);
        return false;
      }
      if (c.steer_degree === undefined || c.steer_degree === null || Number.isNaN(Number(c.steer_degree))) {
        setError(`策略不合法：${c.turn_id} 缺少转向角度（steer_degree）。`);
        return false;
      }
    }

    return true;
  };

  const validateFinish = (segs: { now_pos: number }[]) => {
    const last = segs[segs.length - 1];
    const lastPos = last?.now_pos ?? 0;
    if (lastPos < 2820) {
      setError(
        `策略未到终点：最后位置需达到 2820m（当前：${lastPos}m）。请补全最后一段/调整最后 now_pos。`
      );
      return false;
    }
    return true;
  };

  const handleSubmit = async () => {
    setError('');

    if (!validateCorners(segments)) return;
    if (!validateFinish(segments)) return;

    setIsSubmitting(true);

    try {
      const res = await axios.post(`${API_URL}/api/student/submit`, { segments });
      setResult(res.data.result);
      setLastAttemptNumber(res.data.attempt_number ?? null);
      setLastJobId(res.data.job_id ?? null);
      fetchStatus();
      fetchHistory();
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      // Fix 8: 429 队列满 / 防重入
      if (err.response?.status === 429) {
        const msg = (typeof detail === 'object' && detail?.message) ? detail.message : (typeof detail === 'string' ? detail : '系统仿真队列已满，请稍后重试');
        setError(msg);
      } else if (typeof detail === 'string' && detail.includes('Session Closed')) {
        setError('当前轮次已结束');
      } else if (err.response?.status === 401) {
        setError('当前会话被终止');
        // show message then force logout; also persist reason to login page
        sessionStorage.setItem('logout_reason', '当前会话被终止');
        setTimeout(() => logout(), 300);
      } else {
        setError(detail || 'Submission failed');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // 智能表头修复：将常见拼写错误映射到标准表头
  const HEADER_ALIASES: Record<string, string[]> = {
    'turn_id': ['turn_id', 'turnid', 'turn-id', 'turn id', 'turn', '弯道id', '弯道'],
    'steer_L/R': ['steer_L/R', 'steer_l/r', 'steerlr', 'steer lr', 'steer-lr', 'steer', 'l/r', '方向'],
    'steer_degree': ['steer_degree', 'steerdegree', 'steer-degree', 'steer degree', 'degree', '角度', '转向角度', 'deg'],
    'now_pos': ['now_pos', 'nowpos', 'now-pos', 'now pos', 'position', 'pos', '位置', '当前位置', 'distance', '距离'],
    'sec': ['sec', 'section', '段', '路段', 'segment'],
    'strategy': ['strategy', 'strat', '策略', '驾驶策略'],
    'current_speed km/h': ['current_speed km/h', 'speed', 'current_speed', '速度', '当前速度'],
    'time(s)': ['time(s)', 'time', '时间', 'timestamp'],
    'turn_timeloss': ['turn_timeloss', 'timeloss', 'time_loss', '损失时间'],
    'car_status': ['car_status', 'carstatus', 'status', '车辆状态', '状态']
  };

  const normalizeHeader = (header: string): string => {
    const normalized = header.trim().toLowerCase().replace(/[_\s-]+/g, '').replace(/[()]/g, '');
    
    for (const [standard, aliases] of Object.entries(HEADER_ALIASES)) {
      // 检查完全匹配
      if (aliases.includes(header.trim())) return standard;
      // 检查归一化匹配
      const normalizedAliases = aliases.map(a => a.toLowerCase().replace(/[_\s-]+/g, '').replace(/[()]/g, ''));
      if (normalizedAliases.includes(normalized)) return standard;
      // 模糊匹配：检查是否包含关键子串
      for (const alias of normalizedAliases) {
        if (normalized.includes(alias) || alias.includes(normalized)) {
          // 长度相似度检查（防止过度匹配）
          if (Math.abs(normalized.length - alias.length) <= 3) {
            return standard;
          }
        }
      }
    }
    return header.trim();
  };

  const parseCsvLastNowPos = async (file: File): Promise<number | null> => {
    const text = await file.text();
    const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
    if (lines.length < 2) return null;

    const rawHeader = lines[0].split(',').map((h) => h.trim());
    const header = rawHeader.map(normalizeHeader);
    const idx = header.findIndex((h) => h === 'now_pos');
    if (idx < 0) return null;

    // find last data row
    for (let i = lines.length - 1; i >= 1; i--) {
      const cols = lines[i].split(',');
      if (cols.length <= idx) continue;
      const v = parseFloat((cols[idx] || '').trim());
      if (!Number.isNaN(v)) return v;
    }
    return null;
  };

  const validateCsvCorners = async (file: File): Promise<{ valid: boolean; fixedText?: string }> => {
    // lightweight CSV parsing (no quoted commas support); ok for our generated telemetry CSV.
    const text = await file.text();
    const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
    if (lines.length < 2) {
      setError('CSV 解析失败：内容为空。');
      return { valid: false };
    }

    const rawHeader = lines[0].split(',').map((h) => h.trim());
    const header = rawHeader.map(normalizeHeader);
    
    // 检查是否有表头被修复
    const hasFixes = rawHeader.some((h, i) => h !== header[i]);
    if (hasFixes) {
      console.log('表头自动修复:', rawHeader.map((h, i) => h !== header[i] ? `${h} → ${header[i]}` : h).filter((_, i) => rawHeader[i] !== header[i]));
    }
    
    const idxTurn = header.findIndex((h) => h === 'turn_id');
    const idxLR = header.findIndex((h) => h === 'steer_L/R');
    const idxDeg = header.findIndex((h) => h === 'steer_degree');
    const idxStrategy = header.findIndex((h) => h === 'strategy');
    if (idxTurn < 0 || idxLR < 0 || idxDeg < 0) {
      const missing = [];
      if (idxTurn < 0) missing.push('turn_id');
      if (idxLR < 0) missing.push('steer_L/R');
      if (idxDeg < 0) missing.push('steer_degree');
      setError(`CSV 解析失败：缺少 ${missing.join(' / ')} 表头。检测到表头: ${rawHeader.join(', ')}`);
      return { valid: false };
    }

    let hasDataFixes = false;
    const cleanedDataLines: string[] = [];
    const seq: string[] = [];

    for (let i = 1; i < lines.length; i++) {
      const cols = lines[i].split(',');

      // 清洗 turn_id：0 / 0.0 等占位符 → 空
      let rawTurn = (cols[idxTurn] || '').trim();
      if (/^0+(\.0*)?$/.test(rawTurn)) {
        rawTurn = '';
        cols[idxTurn] = '';
        // steer_L/R 若也是 0 占位符，一并清空
        if (/^0+(\.0*)?$/.test((cols[idxLR] || '').trim())) {
          cols[idxLR] = '';
        }
        hasDataFixes = true;
      }

      // 清洗 strategy：统一小写
      if (idxStrategy >= 0 && cols[idxStrategy]) {
        const rawStrat = cols[idxStrategy].trim();
        const lower = rawStrat.toLowerCase();
        if (lower !== rawStrat) {
          cols[idxStrategy] = lower;
          hasDataFixes = true;
        }
      }

      cleanedDataLines.push(cols.join(','));

      const turn = rawTurn;
      if (!turn) continue;
      seq.push(turn);

      const lr = (cols[idxLR] || '').trim();
      const deg = (cols[idxDeg] || '').trim();
      if (!(lr === 'L' || lr === 'R')) {
        setError(`CSV 策略不合法：${turn} 缺少转向方向（steer_L/R 必须为 L 或 R）。`);
        return { valid: false };
      }
      if (!deg || Number.isNaN(Number(deg))) {
        setError(`CSV 策略不合法：${turn} 缺少转向角度（steer_degree）。`);
        return { valid: false };
      }
    }

    if (seq.length !== EXPECTED_CORNERS.length) {
      setError(
        `CSV 策略不合法：必须包含全部9个弯道且严格按顺序。\n期望：${EXPECTED_CORNERS.join(' → ')}\n当前：${seq.join(' → ') || '(空)'}`
      );
      return { valid: false };
    }
    for (let i = 0; i < EXPECTED_CORNERS.length; i++) {
      if (seq[i] !== EXPECTED_CORNERS[i]) {
        setError(
          `CSV 策略不合法：弯道顺序必须严格匹配。\n期望：${EXPECTED_CORNERS.join(' → ')}\n当前：${seq.join(' → ')}`
        );
        return { valid: false };
      }
    }

    // 生成修复后的 CSV 文本（表头或数据行有任何修复时）
    if (hasFixes || hasDataFixes) {
      const fixedLines = [header.join(','), ...cleanedDataLines];
      return { valid: true, fixedText: fixedLines.join('\n') };
    }
    return { valid: true };
  };

  const handleCsvSubmit = async () => {
    setError('');
    if (!csvFile) {
      setError('请先选择 CSV 文件 / Please choose a CSV file.');
      return;
    }

    const validation = await validateCsvCorners(csvFile);
    if (!validation.valid) return;

    const lastPos = await parseCsvLastNowPos(csvFile);
    if (lastPos === null) {
      setError('CSV 解析失败：未找到 now_pos 列或数据为空。');
      return;
    }
    if (lastPos < 2820) {
      setError(
        `CSV 策略未到终点：最后 now_pos 需达到 2820m（当前：${lastPos}m）。请修改后再提交。`
      );
      return;
    }

    const form = new FormData();
    
    // 如果有修复后的文本，使用修复后的版本
    if (validation.fixedText) {
      const fixedBlob = new Blob([validation.fixedText], { type: 'text/csv' });
      form.append('file', fixedBlob, csvFile.name);
      console.log('使用自动修复后的 CSV 提交');
    } else {
      form.append('file', csvFile);
    }

    setIsSubmitting(true);
    try {
      const res = await axios.post(`${API_URL}/api/student/submit-csv`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setResult(res.data.result);
      setLastAttemptNumber(res.data.attempt_number ?? null);
      setLastJobId(res.data.job_id ?? null);
      fetchStatus();
      fetchHistory();
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      // Fix 8: 429 队列满 / 防重入
      if (err.response?.status === 429) {
        const msg = (typeof detail === 'object' && detail?.message) ? detail.message : (typeof detail === 'string' ? detail : '系统仿真队列已满，请稍后重试');
        setError(msg);
      } else if (typeof detail === 'string' && detail.includes('Session Closed')) {
        setError('当前轮次已结束');
      } else if (err.response?.status === 401) {
        setError('当前会话被终止');
        sessionStorage.setItem('logout_reason', '当前会话被终止');
        setTimeout(() => logout(), 300);
      } else {
        setError(detail || 'CSV submission failed');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const canSubmit = status?.round_active && status?.remaining > 0;

  const guessStudentCode = () => {
    const dn = user?.display_name || '';
    const m = dn.match(/Student\s*(\d+)/i);
    if (m) {
      const n = parseInt(m[1], 10);
      if (!Number.isNaN(n)) return `Student_${String(n).padStart(2, '0')}`;
    }
    // fallback: safe slug
    return dn.replace(/\s+/g, '_') || 'Student';
  };

  const toCsv = (rows: any[]) => {
    if (!rows || rows.length === 0) return '';
    const preferred = ['sec','now_pos','strategy','current_speed km/h','time(s)','turn_id','turn_timeloss','car_status'];
    const keys = new Set<string>();
    rows.forEach((r) => Object.keys(r || {}).forEach((k) => keys.add(k)));
    const cols: string[] = [];
    preferred.forEach((k) => { if (keys.has(k)) cols.push(k); });
    [...keys].sort().forEach((k) => { if (!cols.includes(k)) cols.push(k); });

    const esc = (v: any) => {
      if (v === null || v === undefined) return '';
      const s = String(v);
      if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
      return s;
    };

    const lines = [cols.join(',')];
    rows.forEach((r) => {
      lines.push(cols.map((c) => esc(r?.[c])).join(','));
    });
    return lines.join('\n');
  };

  const downloadRowsAsCsv = (rows: any[], filename: string) => {
    const csv = toCsv(rows);
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const handleDownloadCsv = () => {
    setError('');
    try {
      // backend returns best run details in result.raw_data
      const rows = result?.raw_data;
      if (!Array.isArray(rows) || rows.length === 0) {
        setError('暂无可下载的遥测数据：请先提交一次策略并获得结果。');
        return;
      }

      const roundNo = status?.round_number ?? 'x';
      const attemptNo = lastAttemptNumber ?? 'x';
      const lap = result?.final_time;
      const lapStr = (typeof lap === 'number' && !Number.isNaN(lap)) ? lap.toFixed(4) : 'DNF';
      const studentCode = guessStudentCode();
      const filename = `Lap-result-${studentCode}-Round_${roundNo}-${lapStr}-${attemptNo}.csv`;

      downloadRowsAsCsv(rows, filename);
    } catch (e: any) {
      setError(`下载失败：${e?.message || e}`);
    }
  };

  const handleDownloadHistoryRecord = async (recordId: number) => {
    setError('');
    try {
      const res = await axios.get(`${API_URL}/api/student/history/${recordId}`);
      const rec = res.data;
      const rows = rec?.result?.raw_data;
      if (!Array.isArray(rows) || rows.length === 0) {
        setError('该历史记录暂无可下载的遥测数据。');
        return;
      }

      const roundNo = rec?.round_number ?? 'x';
      const attemptNo = rec?.attempt_number ?? 'x';
      const lap = rec?.result_time;
      const lapStr = (typeof lap === 'number' && !Number.isNaN(lap)) ? lap.toFixed(4) : 'DNF';
      const studentCode = guessStudentCode();
      const filename = `Lap-result-${studentCode}-Round_${roundNo}-${lapStr}-${attemptNo}.csv`;

      downloadRowsAsCsv(rows, filename);
    } catch (e: any) {
      setError(e?.response?.data?.detail || `下载失败：${e?.message || e}`);
    }
  };

  return (
    <div className="min-h-screen bg-racing-bg racing-shell">
      {/* Header */}
      <header className="bg-racing-card border-b border-gray-800">
        <div className="max-w-7xl mx-auto px-4 py-4 flex justify-between items-center">
          <div className="flex items-center gap-4">
            <Zap className="w-8 h-8 text-racing-red" />
            <div>
              <h1 className="text-xl font-bold text-white">学生驾驶舱 | Student Cockpit</h1>
              <p className="text-sm text-racing-gray">{user?.display_name}</p>
            </div>
          </div>
          <button onClick={logout} className="racing-btn-secondary text-sm">
            退出 | Logout
          </button>
        </div>
      </header>

      {/* Leaderboard Banner */}
      <div className="bg-racing-dark border-b border-gray-800 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-3">
          <div className="flex items-center gap-2 mb-2">
            <Trophy className="w-5 h-5 text-racing-gold" />
            <span className="text-sm font-medium text-racing-gray">本轮排行榜 | Round Leaderboard</span>
          </div>
          <div className="flex gap-3 overflow-x-auto">
            {status?.leaderboard?.map((entry: LeaderboardEntry) => (
              <div 
                key={entry.rank}
                className={`flex-shrink-0 px-4 py-2 rounded-lg min-w-[140px] ${
                  entry.name === user?.display_name 
                    ? 'bg-racing-red/20 border border-racing-red' 
                    : 'bg-racing-card border border-gray-800'
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className={`text-lg font-bold ${
                    entry.rank === 1 ? 'text-racing-gold' : 'text-gray-500'
                  }`}>#{entry.rank}</span>
                  <span className="text-white font-medium truncate">{entry.name}</span>
                </div>
                <div className="text-racing-gold font-mono text-sm">{entry.time?.toFixed(2)}s</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Status Bar */}
      <div className="max-w-7xl mx-auto px-4 py-4">
        <div className="racing-card flex flex-wrap gap-6 items-center">
          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-racing-red" />
            <span className="text-racing-gray">轮次 | Round:</span>
            <span className="text-white font-bold">{status?.round_number || '-'}</span>
          </div>
          <div className="flex items-center gap-2">
            <div className={`w-3 h-3 rounded-full ${status?.round_active ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className={status?.round_active ? 'text-green-500' : 'text-red-500'}>
              {status?.round_active ? '🟢 OPEN' : '🔴 CLOSED'}
            </span>
            {!status?.round_active && (
              <span className="ml-2 text-red-400 text-sm flex items-center gap-1">
                <AlertCircle className="w-4 h-4" />
                当前轮次已结束
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Clock className="w-5 h-5 text-racing-gold" />
            <span className="text-racing-gray">剩余机会 | Remaining:</span>
            <span className="text-white font-bold">{status?.remaining ?? '-'}/{status?.max_attempts ?? '-'}</span>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-4 pb-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Strategy Input */}
          <div className="lg:col-span-2 space-y-4">
            <div className="racing-card">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-lg font-bold text-white flex items-center gap-2">
                  <Activity className="w-5 h-5 text-racing-red" />
                  驾驶策略 | Strategy Input
                </h2>
                <span className="text-sm text-racing-gray">{segments.length}/50 段</span>
              </div>

              {/* Segments */}
              <div className="space-y-3 max-h-[400px] overflow-y-auto">
                {segments.map((seg, index) => (
                  <div key={index} className="bg-racing-dark p-3 rounded-lg border border-gray-800">
                    <div className="grid grid-cols-12 gap-2 items-end">
                      <div className="col-span-2">
                        <label className="text-xs text-racing-gray block mb-1">位置 | Pos</label>
                        <input
                          type="number"
                          value={seg.now_pos}
                          onChange={(e) => updateSegment(index, 'now_pos', parseFloat(e.target.value))}
                          className="racing-input w-full text-sm"
                          max={2820}
                          min={0}
                          step="0.1"
                        />
                      </div>
                      <div className="col-span-2">
                        <label className="text-xs text-racing-gray block mb-1">策略 | Strat</label>
                        <select
                          value={seg.strategy}
                          onChange={(e) => updateSegment(index, 'strategy', e.target.value)}
                          className="racing-input w-full text-sm"
                        >
                          <option value="a">加速 A</option>
                          <option value="b">刹车 B</option>
                          <option value="c">滑行 C</option>
                        </select>
                      </div>
                      <div className="col-span-2">
                        <label className="text-xs text-racing-gray block mb-1 flex items-center gap-1">
                          <input
                            type="checkbox"
                            checked={seg.is_corner}
                            onChange={(e) => updateSegment(index, 'is_corner', e.target.checked)}
                            className="rounded border-gray-600"
                          />
                          弯道
                        </label>
                      </div>
                      {seg.is_corner && (
                        <>
                          <div className="col-span-2">
                            <select
                              value={seg.turn_id || ''}
                              onChange={(e) => updateSegment(index, 'turn_id', e.target.value)}
                              className="racing-input w-full text-sm"
                            >
                              <option value="">弯道</option>
                              {['turn1','turn2','turn4','turn6','turn7','turn8','turn10','turn12','turn13'].map(t => (
                                <option key={t} value={t}>{t}</option>
                              ))}
                            </select>
                          </div>
                          <div className="col-span-2">
                            <select
                              value={seg.steer_LR || ''}
                              onChange={(e) => updateSegment(index, 'steer_LR', e.target.value)}
                              className="racing-input w-full text-sm"
                            >
                              <option value="">方向</option>
                              <option value="L">左 L</option>
                              <option value="R">右 R</option>
                            </select>
                          </div>
                          <div className="col-span-1">
                            <input
                              type="number"
                              value={seg.steer_degree || ''}
                              onChange={(e) => updateSegment(index, 'steer_degree', parseFloat(e.target.value))}
                              className="racing-input w-full text-sm"
                              placeholder="°"
                              max={360}
                              min={0}
                            />
                          </div>
                        </>
                      )}
                      <div className="col-span-1">
                        <button
                          onClick={() => removeSegment(index)}
                          disabled={segments.length <= 1}
                          className="p-2 text-red-500 hover:bg-red-900/20 rounded disabled:opacity-30"
                        >
                          <Minus className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Add Button (should sit between manual input and CSV upload) */}
              <button
                onClick={addSegment}
                disabled={segments.length >= 50}
                className="mt-4 w-full py-3 border-2 border-dashed border-gray-700 rounded-lg text-racing-gray hover:border-racing-red hover:text-racing-red transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
              >
                <Plus className="w-5 h-5" />
                添加路段 | Add Segment
              </button>

              {/* CSV Upload */}
              <div className="mt-4 bg-racing-dark p-3 rounded-lg border border-gray-800">
                <div className="flex items-center gap-2 text-racing-gray text-sm mb-2">
                  <Upload className="w-4 h-4" />
                  CSV 上传提交 | Upload CSV
                </div>
                <div className="flex flex-col sm:flex-row gap-2">
                  <input
                    type="file"
                    accept=".csv,text/csv"
                    onChange={(e) => setCsvFile(e.target.files?.[0] || null)}
                    className="racing-input w-full text-sm"
                  />
                  <button
                    onClick={handleCsvSubmit}
                    disabled={!canSubmit || isSubmitting || !csvFile}
                    className="racing-btn-secondary whitespace-nowrap"
                  >
                    提交 CSV
                  </button>
                </div>
                <div className="text-xs text-racing-gray mt-2">
                  要求：CSV 最后一行 now_pos ≥ 2820
                </div>
              </div>

              {/* Error */}
              {error && (
                <div className="mt-4 p-3 bg-red-900/20 border border-racing-red rounded-lg flex items-center gap-2 text-racing-red">
                  <AlertCircle className="w-5 h-5" />
                  {error}
                </div>
              )}

              {/* Submit */}
              <button
                onClick={handleSubmit}
                disabled={!canSubmit || isSubmitting}
                className="mt-4 racing-btn-primary w-full py-4 text-lg font-bold disabled:opacity-50"
              >
                {isSubmitting ? (
                  <span className="animate-pulse">SIMULATING PHYSICS ENGINE...</span>
                ) : (
                  <>发起圈速挑战 | SUBMIT STRATEGY</>
                )}
              </button>
            </div>
          </div>

          {/* Result Panel */}
          <div className="space-y-4">
            {result && (
              <div className="racing-card border-racing-gold/50 border">
                <div className="text-center">
                  <div className="text-sm text-racing-gray mb-2">本圈用时 | Lap Time</div>
                  <div className="text-5xl font-bold text-racing-gold font-mono">
                    {result.final_time?.toFixed(2) || 'DNF'}
                  </div>
                  <div className="text-sm text-racing-gray mt-2">
                    {result.is_dnf ? '车辆损毁 | DNF' : `Run ${result.best_run}/5 最优`}
                  </div>
                </div>
                <button
                  onClick={handleDownloadCsv}
                  className="mt-4 w-full racing-btn-secondary flex items-center justify-center gap-2"
                >
                  <Download className="w-4 h-4" />
                  下载遥测数据 | Download CSV
                </button>
              </div>
            )}

            {/* History */}
            <div className="racing-card">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-white font-bold flex items-center gap-2">
                  <History className="w-5 h-5 text-racing-gray" />
                  历史记录 | History
                </h3>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => toggleSort('time')}
                    className={`flex items-center gap-1 px-2 py-1 text-xs rounded transition-colors ${
                      sortBy === 'time' ? 'bg-racing-red text-white' : 'bg-racing-dark text-racing-gray hover:text-white'
                    }`}
                  >
                    时间
                    {sortBy === 'time' ? (
                      sortOrder === 'asc' ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />
                    ) : (
                      <ArrowUpDown className="w-3 h-3" />
                    )}
                  </button>
                  <button
                    onClick={() => toggleSort('lap')}
                    className={`flex items-center gap-1 px-2 py-1 text-xs rounded transition-colors ${
                      sortBy === 'lap' ? 'bg-racing-red text-white' : 'bg-racing-dark text-racing-gray hover:text-white'
                    }`}
                  >
                    圈速
                    {sortBy === 'lap' ? (
                      sortOrder === 'asc' ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />
                    ) : (
                      <ArrowUpDown className="w-3 h-3" />
                    )}
                  </button>
                </div>
              </div>
              <div className="space-y-2 text-sm">
                {sortedHistory.length === 0 ? (
                  <div className="text-racing-gray text-center py-4">暂无记录 | No records yet</div>
                ) : (
                  sortedHistory.map((h, idx) => (
                    <div
                      key={h.id ?? idx}
                      className="flex items-center justify-between gap-3 bg-racing-dark border border-gray-800 rounded-lg px-3 py-2"
                    >
                      <div className="min-w-0">
                        <div className="text-white font-mono text-sm truncate">
                          Round {h.round_number} · #{h.attempt_number}
                          {h.is_dnf ? ' · DNF' : ''}
                        </div>
                        <div className="text-xs text-racing-gray truncate">
                          {h.created_at}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 whitespace-nowrap">
                        <div className="text-racing-gold font-mono text-sm">
                          {h.is_dnf ? 'DNF' : (typeof h.result_time === 'number' ? `${h.result_time.toFixed(2)}s` : '-')}
                        </div>
                        <button
                          onClick={() => handleDownloadHistoryRecord(h.id)}
                          className="racing-btn-secondary text-xs px-2 py-1 flex items-center gap-1"
                          title="下载该条记录的遥测数据 / Download telemetry"
                        >
                          <Download className="w-3 h-3" />
                          下载
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default StudentDashboard;
