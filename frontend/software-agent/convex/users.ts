import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

// Get or create user by email
export const getOrCreateUser = mutation({
  args: {
    email: v.string(),
    name: v.optional(v.string()),
    image: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query("users")
      .withIndex("by_email", (q) => q.eq("email", args.email))
      .first();

    if (existing) {
      // Update name/image if provided
      if (args.name || args.image) {
        await ctx.db.patch(existing._id, {
          ...(args.name && { name: args.name }),
          ...(args.image && { image: args.image }),
        });
      }
      return existing._id;
    }

    return await ctx.db.insert("users", {
      email: args.email,
      name: args.name,
      image: args.image,
      subscription: "free",
      credits: 100,
      createdAt: Date.now(),
    });
  },
});

// Get user by email
export const getUserByEmail = query({
  args: { email: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("users")
      .withIndex("by_email", (q) => q.eq("email", args.email))
      .first();
  },
});

// Update user credits
export const updateCredits = mutation({
  args: {
    email: v.string(),
    credits: v.number(),
  },
  handler: async (ctx, args) => {
    const user = await ctx.db
      .query("users")
      .withIndex("by_email", (q) => q.eq("email", args.email))
      .first();

    if (!user) throw new Error("User not found");

    await ctx.db.patch(user._id, { credits: args.credits });
  },
});

// Deduct credits
export const deductCredits = mutation({
  args: {
    email: v.string(),
    amount: v.number(),
  },
  handler: async (ctx, args) => {
    const user = await ctx.db
      .query("users")
      .withIndex("by_email", (q) => q.eq("email", args.email))
      .first();

    if (!user) throw new Error("User not found");
    if (user.credits < args.amount) throw new Error("Insufficient credits");

    await ctx.db.patch(user._id, { credits: user.credits - args.amount });
    return user.credits - args.amount;
  },
});
