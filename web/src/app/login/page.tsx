"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Images, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { user, loading, login } = useAuth();
  const router = useRouter();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Already signed in? Skip the form.
  useEffect(() => {
    if (!loading && user) router.replace("/");
  }, [user, loading, router]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username.trim(), password);
      router.replace("/");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Sign in failed. Try again."
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="grid min-h-screen place-items-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-7 flex flex-col items-center text-center">
          <span className="mb-3 grid h-12 w-12 place-items-center rounded-xl bg-accent text-accent-fg">
            <Images size={24} />
          </span>
          <h1 className="text-xl font-semibold">PhotoPi</h1>
          <p className="mt-1 text-sm text-muted">
            Sign in to your photo library
          </p>
        </div>

        <form
          onSubmit={onSubmit}
          className="space-y-3 rounded-xl border border-border bg-surface p-6"
        >
          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="username">
              Username
            </label>
            <Input
              id="username"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="password">
              Password
            </label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          {error && (
            <p className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
              {error}
            </p>
          )}

          <Button type="submit" disabled={submitting} className="w-full">
            {submitting && <Loader2 size={16} className="animate-spin" />}
            {submitting ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        <p className="mt-4 text-center text-xs text-muted">
          Default credentials are set in your <code>.env</code> file. Change
          the password after your first sign in.
        </p>
      </div>
    </div>
  );
}
