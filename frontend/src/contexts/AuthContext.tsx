import React, { createContext, useContext, useState, useEffect } from 'react';
import axios from 'axios';

interface User {
  token: string;
  role: 'admin' | 'teacher' | 'student';
  display_name: string;
}

interface AuthContextType {
  user: User | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  isLoading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const API_URL = import.meta.env.VITE_API_URL || window.location.origin;

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('token');
    const role = localStorage.getItem('role') as User['role'] | null;
    const display_name = localStorage.getItem('display_name');
    
    if (token && role && display_name) {
      setUser({ token, role, display_name });
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    }
    setIsLoading(false);
  }, []);

  const login = async (username: string, password: string) => {
    const response = await axios.post(`${API_URL}/api/auth/login`, {
      username,
      password
    });
    
    const { token, role, display_name } = response.data;
    
    localStorage.setItem('token', token);
    localStorage.setItem('role', role);
    localStorage.setItem('display_name', display_name);
    
    axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    setUser({ token, role, display_name });
  };

  const logout = async () => {
    try {
      await axios.post(`${API_URL}/api/auth/logout`);
    } catch (e) {
      // ignore
    }
    
    localStorage.removeItem('token');
    localStorage.removeItem('role');
    localStorage.removeItem('display_name');
    delete axios.defaults.headers.common['Authorization'];
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, login, logout, isLoading }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
};
