import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  // Users table
  users: defineTable({
    email: v.string(),
    name: v.optional(v.string()),
    image: v.optional(v.string()),
    subscription: v.string(), // "free", "pro", "enterprise"
    credits: v.number(),
    createdAt: v.number(),
  }).index("by_email", ["email"]),

  // Projects table
  projects: defineTable({
    userId: v.string(),
    name: v.string(),
    description: v.optional(v.string()),
    status: v.string(), // "active", "paused", "completed", "archived"
    requirements: v.optional(v.string()),
    generatedCode: v.optional(v.string()),
    refinedCode: v.optional(v.string()),
    documentation: v.optional(v.string()),
    language: v.optional(v.string()),
    framework: v.optional(v.string()),
    githubUrl: v.optional(v.string()),
    modelConfig: v.optional(v.object({
      codeGenModel: v.string(),
      reviewModel: v.string(),
      refineModel: v.string(),
    })),
    createdAt: v.number(),
    updatedAt: v.number(),
  })
    .index("by_user", ["userId"])
    .index("by_status", ["status"]),

  // Tasks table (individual agent runs)
  tasks: defineTable({
    projectId: v.id("projects"),
    userId: v.string(),
    taskId: v.string(), // External task ID for LangGraph
    prompt: v.string(),
    status: v.string(), // "pending", "running", "completed", "failed", "paused"
    currentAgent: v.optional(v.string()),
    progress: v.number(),
    checkpointId: v.optional(v.string()),
    checkpointState: v.optional(v.any()),
    modelUsed: v.optional(v.string()), // "groq", "ollama"
    outputs: v.optional(v.object({
      generatedCode: v.optional(v.string()),
      reviewReport: v.optional(v.string()),
      decision: v.optional(v.string()),
      refinedCode: v.optional(v.string()),
      documentation: v.optional(v.string()),
      testResults: v.optional(v.string()),
    })),
    errors: v.optional(v.array(v.string())),
    startedAt: v.number(),
    completedAt: v.optional(v.number()),
  })
    .index("by_project", ["projectId"])
    .index("by_user", ["userId"])
    .index("by_task_id", ["taskId"])
    .index("by_status", ["status"]),

  // Events table (real-time agent events)
  events: defineTable({
    taskId: v.id("tasks"),
    userId: v.string(),
    type: v.string(), // "agent_start", "agent_end", "log", "code_output", etc.
    agent: v.optional(v.string()),
    message: v.optional(v.string()),
    code: v.optional(v.string()),
    data: v.optional(v.any()),
    timestamp: v.number(),
  })
    .index("by_task", ["taskId"])
    .index("by_user", ["userId"]),

  // Files table
  files: defineTable({
    projectId: v.id("projects"),
    userId: v.string(),
    name: v.string(),
    path: v.string(),
    type: v.string(), // "code", "doc", "config", "asset"
    content: v.optional(v.string()), // For text files
    storageId: v.optional(v.id("_storage")), // For binary files
    mimeType: v.string(),
    size: v.number(),
    version: v.number(),
    isGenerated: v.boolean(),
    createdAt: v.number(),
    updatedAt: v.number(),
  })
    .index("by_project", ["projectId"])
    .index("by_user", ["userId"]),

  // Memory table (agent learning/context)
  memory: defineTable({
    userId: v.string(),
    projectId: v.optional(v.id("projects")),
    type: v.string(), // "preference", "pattern", "error", "context"
    key: v.string(),
    value: v.any(),
    importance: v.number(), // 1-10
    usageCount: v.number(),
    createdAt: v.number(),
    lastUsedAt: v.number(),
  })
    .index("by_user", ["userId"])
    .index("by_project", ["projectId"])
    .index("by_type", ["type"]),
});
