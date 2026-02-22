"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { X, Send } from "lucide-react";

interface RejectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (feedback: string) => void;
}

export function RejectModal({ isOpen, onClose, onSubmit }: RejectModalProps) {
  const [feedback, setFeedback] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async () => {
    setIsSubmitting(true);
    await onSubmit(feedback);
    setFeedback("");
    setIsSubmitting(false);
    onClose();
  };

  const handleClose = () => {
    setFeedback("");
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={handleClose}
      />

      {/* Modal */}
      <div className="relative z-10 w-full max-w-lg bg-card border border-border rounded-xl shadow-2xl p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-foreground">
            Reject Code & Provide Feedback
          </h2>
          <Button
            variant="ghost"
            size="icon"
            onClick={handleClose}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="w-4 h-4" />
          </Button>
        </div>

        {/* Description */}
        <p className="text-sm text-muted-foreground mb-4">
          Tell the AI what&apos;s wrong with the code or what you&apos;d like changed. 
          This feedback will be used to generate an improved version.
        </p>

        {/* Feedback Input */}
        <Textarea
          placeholder="e.g., 'The sorting algorithm is inefficient' or 'Add error handling for edge cases'"
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          className="min-h-[120px] bg-muted border-border text-foreground resize-none mb-4"
          autoFocus
        />

        {/* Actions */}
        <div className="flex justify-end gap-3">
          <Button
            variant="ghost"
            onClick={handleClose}
            className="text-muted-foreground"
          >
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={isSubmitting}
            className="bg-red-600 hover:bg-red-700 text-white"
          >
            <Send className="w-4 h-4 mr-2" />
            {isSubmitting ? "Sending..." : "Reject & Send Feedback"}
          </Button>
        </div>
      </div>
    </div>
  );
}
