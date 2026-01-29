"use client";

import { useSession, signOut } from "next-auth/react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { LogOut, User } from "lucide-react";

export function UserMenu() {
  const { data: session } = useSession();

  if (!session?.user) {
    return null;
  }

  const initials = session.user.name
    ?.split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase() || "U";

  return (
    <div className="flex items-center gap-3">
      <div className="flex items-center gap-2">
        <Avatar className="w-8 h-8">
          <AvatarImage src={session.user.image || undefined} />
          <AvatarFallback className="bg-purple-600 text-white text-xs">
            {initials}
          </AvatarFallback>
        </Avatar>
        <span className="text-sm text-zinc-300 hidden sm:inline">
          {session.user.name || session.user.email}
        </span>
      </div>
      <Button
        variant="ghost"
        size="icon"
        onClick={() => signOut({ callbackUrl: "/auth/signin" })}
        className="text-zinc-400 hover:text-white"
      >
        <LogOut className="w-4 h-4" />
      </Button>
    </div>
  );
}
