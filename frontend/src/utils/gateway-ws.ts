// WebSocket 客户端工具类
// 用于与 OpenClaw Gateway ws://localhost:18789 建立实时连接
// Phase 2: 集成 PinchChat WebSocket 认证

import { API_BASE_URL } from '../lib/apiBase';

// Gateway WebSocket 配置 (来自 PinchChat 验证)
const GATEWAY_WS_URL = import.meta.env.VITE_GATEWAY_WS_URL || 'ws://localhost:18789';
const GATEWAY_TOKEN = import.meta.env.VITE_GATEWAY_TOKEN || '';

export type MessageHandler = (data: any) => void;

export interface WebSocketMessage {
  type: string;
  id?: string;
  method?: string;
  params?: any;
  data?: any;
  timestamp?: string;
  channel?: string;
  message?: string;
  sessionKey?: string;
  deliver?: boolean;
  idempotencyKey?: string;
}

class GatewayWebSocketClient {
  private ws: WebSocket | null = null;
  private url: string;
  private token: string;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private handlers: Map<string, MessageHandler[]> = new Map();
  private isConnecting = false;
  private messageQueue: WebSocketMessage[] = [];
  private pendingRequests: Map<string, { resolve: Function; reject: Function; timeout: NodeJS.Timeout }> = new Map();
  private currentSessionKey: string | null = null;

  constructor() {
    this.url = GATEWAY_WS_URL;
    this.token = GATEWAY_TOKEN;
  }

  /**
   * 连接到 OpenClaw Gateway
   */
  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        resolve();
        return;
      }

      if (this.isConnecting) {
        reject(new Error('Already connecting...'));
        return;
      }

      this.isConnecting = true;
      console.log('[GatewayWS] Connecting to', this.url);

      try {
        this.ws = new WebSocket(this.url);

        this.ws.onopen = () => {
          console.log('[GatewayWS] Connected, authenticating...');
          // Phase 2: 认证流程
          this.authenticate().then(() => {
            console.log('[GatewayWS] Authenticated successfully');
            this.isConnecting = false;
            this.reconnectAttempts = 0;
            this.flushMessageQueue();
            resolve();
          }).catch((err) => {
            console.error('[GatewayWS] Authentication failed:', err);
            this.isConnecting = false;
            reject(err);
          });
        };

        this.ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data);
            console.log('[GatewayWS] Received:', message);
            this.handleMessage(message);
          } catch (e) {
            console.error('[GatewayWS] Failed to parse message:', e);
          }
        };

        this.ws.onclose = (event) => {
          console.log('[GatewayWS] Disconnected:', event.code, event.reason);
          this.isConnecting = false;
          this.handleClose();
        };

        this.ws.onerror = (error) => {
          console.error('[GatewayWS] Error:', error);
          this.isConnecting = false;
          reject(error);
        };
      } catch (e) {
        this.isConnecting = false;
        reject(e);
      }
    });
  }

  /**
   * 认证到 Gateway (来自 PinchChat 验证)
   */
  private async authenticate(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
        reject(new Error('WebSocket not connected'));
        return;
      }

      // 监听认证响应
      const authHandler = (msg: any) => {
        if (msg.type === 'response' && msg.id === 'auth') {
          if (msg.error) {
            console.error('[GatewayWS] Auth error:', msg.error);
            reject(new Error(msg.error.message || 'Authentication failed'));
          } else {
            console.log('[GatewayWS] Auth success:', msg.result);
            this.off('response_auth', authHandler);
            resolve();
          }
        }
      };
      this.on('response_auth', authHandler);

      // 发送认证请求 (来自 pinchchat-study-notes.md)
      this.send({
        id: 'auth',
        method: 'connect',
        params: {
          minProtocol: 3,
          maxProtocol: 3,
          client: {
            id: 'racing-sim',
            version: '1.0.0',
            platform: 'web',
            mode: 'webchat'
          },
          role: 'operator',
          scopes: ['operator.read', 'operator.write', 'operator.admin'],
          auth: { token: this.token }
        }
      });

      // 5秒超时
      setTimeout(() => {
        this.off('response_auth', authHandler);
        reject(new Error('Authentication timeout'));
      }, 5000);
    });
  }

  /**
   * 断开连接
   */
  disconnect(): void {
    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
    }
    this.handlers.clear();
    this.pendingRequests.forEach(({ reject }) => reject(new Error('Disconnected')));
    this.pendingRequests.clear();
  }

  /**
   * 发送消息到 Gateway
   */
  send(message: WebSocketMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    } else {
      this.messageQueue.push(message);
    }
  }

  /**
   * 发送请求并等待响应 (RPC 风格)
   */
  sendRequest<T = any>(method: string, params: Record<string, any>, timeout = 30000): Promise<T> {
    const id = `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    return new Promise((resolve, reject) => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
        reject(new Error('WebSocket not connected'));
        return;
      }

      const timeoutId = setTimeout(() => {
        this.pendingRequests.delete(id);
        reject(new Error(`Request timeout: ${method}`));
      }, timeout);

      this.pendingRequests.set(id, { resolve, reject, timeout: timeoutId });

      this.send({
        id,
        method,
        params
      });
    });
  }

  /**
   * 发送聊天消息 (Phase 2 核心功能)
   */
  async sendChatMessage(sessionKey: string, message: string, deliver = false): Promise<any> {
    return this.sendRequest('chat.send', {
      sessionKey,
      message,
      deliver,
      idempotencyKey: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    });
  }

  /**
   * 查询会话列表
   */
  async listSessions(): Promise<any> {
    return this.sendRequest('sessions.list', {});
  }

  /**
   * 创建新会话
   */
  async createSession(agentId = 'main'): Promise<any> {
    return this.sendRequest('sessions.create', {
      agentId,
      label: `racing-sim-${Date.now()}`
    });
  }

  /**
   * 订阅事件
   */
  onEvent(handler: MessageHandler): void {
    this.on('event', handler);
  }

  /**
   * 订阅聊天消息
   */
  onChat(handler: (data: any) => void): void {
    this.on('chat', handler);
  }

  /**
   * 注册消息处理器
   */
  on(type: string, handler: MessageHandler): void {
    if (!this.handlers.has(type)) {
      this.handlers.set(type, []);
    }
    this.handlers.get(type)!.push(handler);
  }

  /**
   * 移除消息处理器
   */
  off(type: string, handler?: MessageHandler): void {
    if (!handler) {
      this.handlers.delete(type);
    } else {
      const handlers = this.handlers.get(type);
      if (handlers) {
        const index = handlers.indexOf(handler);
        if (index > -1) {
          handlers.splice(index, 1);
        }
      }
    }
  }

  /**
   * 获取连接状态
   */
  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  // 私有方法

  private handleMessage(message: any): void {
    const { id, type, method, result, error } = message;

    // 处理请求响应
    if (id && this.pendingRequests.has(id)) {
      const { resolve, reject, timeout } = this.pendingRequests.get(id)!;
      clearTimeout(timeout);
      this.pendingRequests.delete(id);

      if (error) {
        reject(new Error(error.message || 'Request failed'));
      } else {
        resolve(result);
      }
      return;
    }

    // 触发特定类型处理器
    if (type) {
      const handlers = this.handlers.get(type);
      if (handlers) {
        handlers.forEach((handler) => handler(message));
      }
    }

    // 触发所有消息处理器
    const allHandlers = this.handlers.get('*');
    if (allHandlers) {
      allHandlers.forEach((handler) => handler(message));
    }
  }

  private handleClose(): void {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
      console.log(`[GatewayWS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
      setTimeout(() => {
        this.connect().catch(console.error);
      }, delay);
    }
  }

  private flushMessageQueue(): void {
    while (this.messageQueue.length > 0) {
      const message = this.messageQueue.shift();
      if (message) {
        this.send(message);
      }
    }
  }
}

// 导出单例
export const gatewayClient = new GatewayWebSocketClient();

// React Hook
export function useGatewayWebSocket() {
  return gatewayClient;
}
