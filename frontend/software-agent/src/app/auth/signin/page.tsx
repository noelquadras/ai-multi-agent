"use client";

import { signIn } from "next-auth/react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Bot, Github, Loader2, Mail } from "lucide-react";

export default function SignInPage() {
  const [isLoading, setIsLoading] = useState<string | null>(null);
  const [email, setEmail] = useState("demo@example.com");
  const [password, setPassword] = useState("demo123");

  const handleOAuthSignIn = async (provider: string) => {
    setIsLoading(provider);
    await signIn(provider, { callbackUrl: "/" });
  };

  const handleCredentialsSignIn = async () => {
    setIsLoading("credentials");
    await signIn("credentials", {
      email,
      password,
      callbackUrl: "/",
    });
  };

  return (
    <main className="min-h-screen bg-[#050505] text-white flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="w-12 h-12 bg-purple-600 rounded-lg flex items-center justify-center">
            <Bot className="text-white w-7 h-7" />
          </div>
          <h1 className="text-2xl font-bold">AI Software Team</h1>
        </div>

        {/* Sign In Card */}
        <div className="bg-[#0A0A0A] border border-[#1F1F1F] rounded-xl p-6">
          <h2 className="text-xl font-semibold mb-6 text-center">
            Sign in to continue
          </h2>

          {/* OAuth Providers */}
          <div className="space-y-3 mb-6">
            <Button
              variant="outline"
              className="w-full bg-[#1A1A1A] border-[#2A2A2A] hover:bg-[#2A2A2A]"
              onClick={() => handleOAuthSignIn("github")}
              disabled={isLoading !== null}
            >
              {isLoading === "github" ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Github className="w-4 h-4 mr-2" />
              )}
              Continue with GitHub
            </Button>

            <Button
              variant="outline"
              className="w-full bg-[#1A1A1A] border-[#2A2A2A] hover:bg-[#2A2A2A]"
              onClick={() => handleOAuthSignIn("google")}
              disabled={isLoading !== null}
            >
              {isLoading === "google" ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Mail className="w-4 h-4 mr-2" />
              )}
              Continue with Google
            </Button>
          </div>

          {/* Divider */}
          <div className="flex items-center gap-4 mb-6">
            <div className="flex-1 h-px bg-[#2A2A2A]" />
            <span className="text-zinc-500 text-sm">or</span>
            <div className="flex-1 h-px bg-[#2A2A2A]" />
          </div>

          {/* Demo Login */}
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-zinc-400 mb-1">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full bg-[#1A1A1A] border border-[#2A2A2A] rounded-lg px-3 py-2 text-white"
                placeholder="demo@example.com"
              />
            </div>
            <div>
              <label className="block text-sm text-zinc-400 mb-1">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full bg-[#1A1A1A] border border-[#2A2A2A] rounded-lg px-3 py-2 text-white"
                placeholder="demo123"
              />
            </div>
            <Button
              className="w-full bg-purple-600 hover:bg-purple-700"
              onClick={handleCredentialsSignIn}
              disabled={isLoading !== null}
            >
              {isLoading === "credentials" ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : null}
              Sign in with Demo Account
            </Button>
          </div>

          {/* Demo Hint */}
          <p className="text-xs text-zinc-500 text-center mt-4">
            Demo credentials: demo@example.com / demo123
          </p>
        </div>
      </div>
    </main>
  );
}
