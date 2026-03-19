// WebSocket 客户端工具类
// 用于与后端 ws://localhost:18000/ws 建立实时连接

import { API_BASE_URL } from '../lib/apiBase';

export type MessageHandler = (data: any) => void;

export interface WebSocketMessage {
  type: string;
  data?: any;
  timestamp?: string;
  channel?: string;
  message?: string;
}

class WebSocketClient {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private handlers: Map<string, MessageHandler[]> = new Map();
  private isConnecting = false;
  private messageQueue: WebSocketMessage[] = [];

  constructor() {
    // 使用当前origin，WebSocket使用ws://协议
    // 修复：默认连接到 18000 端口（racing-sim 后端）
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = import.meta.env.VITE_WS_URL?.replace(/^http/, 'ws') 
      || `${wsProtocol}//${window.location.hostname}:18000`;
    this.url = host;
  }

  /**
   * 连接到WebSocket服务器
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
      console.log('[WS] Connecting to', this.url);

      try {
        this.ws = new WebSocket(this.url);

        this.ws.onopen = () => {
          console.log('[WS] Connected');
          this.isConnecting = false;
          this.reconnectAttempts = 0;
          this.flushMessageQueue();
          resolve();
        };

        this.ws.onmessage = (event) => {
          try {
            const message: WebSocketMessage = JSON.parse(event.data);
            console.log('[WS] Received:', message);
            this.handleMessage(message);
          } catch (e) {
            console.error('[WS] Failed to parse message:', e);
          }
        };

        this.ws.onclose = (event) => {
          console.log('[WS] Disconnected:', event.code, event.reason);
          this.isConnecting = false;
          this.handleClose();
        };

        this.ws.onerror = (error) => {
          console.error('[WS] Error:', error);
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
   * 断开连接
   */
  disconnect(): void {
    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
    }
    this.handlers.clear();
  }

  /**
   * 发送消息
   */
  send(message: WebSocketMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    } else {
      // 队列消息，等连接成功后发送
      this.messageQueue.push(message);
    }
  }

  /**
   * 发送消息并等待响应
   */
  sendAndWait(message: WebSocketMessage, timeout = 5000): Promise<any> {
    return new Promise((resolve, reject) => {
      const id = Date.now().toString();
      const timeoutId = setTimeout(() => {
        reject(new Error('Timeout waiting for response'));
      }, timeout);

      const handler: MessageHandler = (data) => {
        if (data.id === id) {
          clearTimeout(timeoutId);
          this.off(`response_${id}`, handler);
          resolve(data);
        }
      };

      this.on(`response_${id}`, handler);
      this.send({ ...message, id });
    });
  }

  /**
   * 订阅频道
   */
  subscribe(channel: string): void {
    this.send({ type: 'subscribe', channel });
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

  private handleMessage(message: WebSocketMessage): void {
    const { type } = message;

    // 触发特定类型处理器
    const handlers = this.handlers.get(type);
    if (handlers) {
      handlers.forEach((handler) => handler(message));
    }

    // 触发所有消息处理器
    const allHandlers = this.handlers.get('*');
    if (allHandlers) {
      allHandlers.forEach((handler) => handler(message));
    }
  }

  private handleClose(): void {
    // 自动重连
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
      console.log(`[WS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
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
export const wsClient = new WebSocketClient();

// React Hook
export function useWebSocket() {
  return wsClient;
}
