"use client";

import { useState } from 'react';
import { useRouter } from 'next/navigation';

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();

    // Replicating your legacy logic
    if (username === 'admin' && password === 'ubuntuServer2026') {
      // Set cookie (expires in 1 day)
      const d = new Date();
      d.setTime(d.getTime() + (24*60*60*1000));
      document.cookie = `session_token=admin_secret_123; expires=${d.toUTCString()}; path=/`;
      
      router.push('/admin'); // Redirect to dashboard
    } else {
      alert("Invalid Credentials");
    }
  };

  return (
    <div className="global_body_container h-screen flex items-center justify-center bg-gray-200">
      <div className="global_box_login_container bg-white p-8 rounded shadow-md w-96">
        <h2 className="text-2xl font-bold mb-6 text-center text-gray-700">
          Login data skor rekomendasi desa
        </h2>
        <form onSubmit={handleLogin}>
          <div className="mb-4">
            <label className="block text-sm font-bold mb-2">Username</label>
            <input 
              type="text" 
              className="w-full border p-2 rounded" 
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="admin"
            />
          </div>
          <div className="mb-6">
            <label className="block text-sm font-bold mb-2">Password</label>
            <input 
              type="password" 
              className="w-full border p-2 rounded" 
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="password"
            />
          </div>
          <button className="w-full bg-blue-600 text-white py-2 rounded font-bold hover:bg-blue-700">
            Login
          </button>
        </form>
      </div>
    </div>
  );
}


