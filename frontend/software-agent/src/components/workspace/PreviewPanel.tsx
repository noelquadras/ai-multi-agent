'use client';

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { RotateCw, ExternalLink, Monitor, StopCircle, Play, Code, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useState, useEffect } from "react";

interface PreviewPanelProps {
  taskStatus?: {
    result?: any;
    status?: string;
  } | null;
}

export function PreviewPanel({ taskStatus }: PreviewPanelProps) {
    const [isPreviewRunning, setIsPreviewRunning] = useState(false);
    const [previewCode, setPreviewCode] = useState<string>('');

    useEffect(() => {
        if (taskStatus?.result) {
            // Use refined code if available, otherwise generated code
            const code = taskStatus.result.refined_code || taskStatus.result.generated_code || '';
            setPreviewCode(code);
        } else {
            setPreviewCode('');
        }
    }, [taskStatus]);

    const handleRunPreview = () => {
        if (!previewCode) return;
        
        setIsPreviewRunning(true);
        // Simulate preview running
        setTimeout(() => {
            setIsPreviewRunning(false);
        }, 2000);
    };

    const getPreviewStatus = () => {
        if (!taskStatus) return { text: 'No Data', color: 'text-zinc-500', bg: 'bg-zinc-500/20' };
        
        switch (taskStatus.status) {
            case 'running':
                return { text: 'Generating', color: 'text-blue-500', bg: 'bg-blue-500/20' };
            case 'completed':
                return { text: 'Ready', color: 'text-green-500', bg: 'bg-green-500/20' };
            case 'failed':
                return { text: 'Failed', color: 'text-red-500', bg: 'bg-red-500/20' };
            default:
                return { text: 'Idle', color: 'text-zinc-500', bg: 'bg-zinc-500/20' };
        }
    };

    const status = getPreviewStatus();

    return (
        <Card className="h-full border-none rounded-none bg-[#050505] flex flex-col p-4 w-[400px]">
            {/* Browser Bar */}
            <div className="h-10 bg-[#110C1D] border border-[#1F1F1F] rounded-t-lg flex items-center justify-between px-3">
                <div className="flex items-center gap-2">
                    <div className="w-2.5 h-2.5 rounded-full bg-red-500/20 border border-red-500/50" />
                    <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/20 border border-yellow-500/50" />
                    <div className="w-2.5 h-2.5 rounded-full bg-green-500/20 border border-green-500/50" />
                </div>
                <div className="flex-1 mx-4 h-6 bg-[#050505]/50 rounded text-[10px] text-zinc-500 flex items-center justify-center font-mono gap-1 border border-white/5">
                    <div className={`w-2 h-2 rounded-full ${status.color} animate-pulse`} />
                    localhost:3000
                </div>
                <div className="flex items-center gap-2 text-zinc-600">
                    <RotateCw className="w-3 h-3 hover:text-white cursor-pointer" />
                    <ExternalLink className="w-3 h-3 hover:text-white cursor-pointer" />
                </div>
            </div>

            {/* Preview Content */}
            <CardContent className="flex-1 bg-[#0A0A0A] border-x border-b border-[#1F1F1F] rounded-b-lg p-6 relative overflow-hidden">
                <div className="flex items-center justify-between mb-6">
                    <div>
                        <h1 className="text-xl font-bold text-white mb-1">AI Code Preview</h1>
                        <Badge className={`${status.bg} ${status.color} border-0 text-[10px] uppercase tracking-widest font-semibold`}>
                            {status.text}
                        </Badge>
                    </div>
                    <div className="w-10 h-10 rounded-xl bg-[#1F1F1F] flex items-center justify-center text-purple-400">
                        <Monitor className="w-5 h-5" />
                    </div>
                </div>

                {/* Preview Info */}
                <div className="space-y-4 mb-6">
                    <div className="bg-[#141414] border border-[#222] rounded-lg p-4">
                        <div className="flex items-center justify-between mb-3">
                            <span className="text-sm text-zinc-400">Generated Code</span>
                            <Badge variant="outline" className="border-blue-500/30 text-blue-400 text-[10px]">
                                {previewCode ? `${previewCode.length} chars` : 'Empty'}
                            </Badge>
                        </div>
                        <div className="h-2 w-full bg-[#222] rounded-full overflow-hidden">
                            <div 
                                className={`h-full rounded-full transition-all duration-300 ${
                                    previewCode ? 'bg-gradient-to-r from-blue-500 to-purple-500' : 'bg-zinc-700'
                                }`}
                                style={{ width: previewCode ? '100%' : '0%' }}
                            />
                        </div>
                    </div>

                    {taskStatus?.result?.documentation && (
                        <div className="bg-[#141414] border border-[#222] rounded-lg p-4">
                            <div className="flex items-center gap-2 mb-2">
                                <Code className="w-4 h-4 text-green-500" />
                                <span className="text-sm text-zinc-400">Documentation</span>
                            </div>
                            <p className="text-xs text-zinc-500 line-clamp-2">
                                {taskStatus.result.documentation.substring(0, 100)}...
                            </p>
                        </div>
                    )}

                    {taskStatus?.result?.review_report && (
                        <div className="bg-[#141414] border border-[#222] rounded-lg p-4">
                            <div className="flex items-center gap-2 mb-2">
                                <AlertCircle className="w-4 h-4 text-yellow-500" />
                                <span className="text-sm text-zinc-400">Review Notes</span>
                            </div>
                            <p className="text-xs text-zinc-500 line-clamp-2">
                                {taskStatus.result.review_report.substring(0, 100)}...
                            </p>
                        </div>
                    )}
                </div>

                {/* Preview Mock */}
                <div className="space-y-4 opacity-50">
                    <div className="h-32 rounded-xl bg-[#141414] border border-[#222] p-4">
                        <div className="flex items-start justify-between">
                            <div className="w-1/3 h-2 bg-[#222] rounded-full" />
                            <div className="px-2 py-0.5 bg-green-500/10 text-green-500 text-[10px] rounded">Preview</div>
                        </div>
                        <div className="mt-4 w-2/3 h-2 bg-[#222] rounded-full" />
                        <div className="mt-12 w-full h-3 bg-purple-900/30 rounded-full overflow-hidden">
                            <div className="w-2/3 h-full bg-purple-600 rounded-full" />
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <div className="h-24 rounded-xl bg-[#141414] border border-[#222] p-4 flex flex-col justify-between">
                            <div className="w-1/2 h-2 bg-[#222] rounded-full" />
                            <div className="w-full h-8 bg-[#222] rounded-lg opacity-50" />
                        </div>
                        <div className="h-24 rounded-xl bg-[#141414] border border-[#222] p-4 flex flex-col justify-between">
                            <div className="w-1/2 h-2 bg-[#222] rounded-full" />
                            <div className="w-full h-8 bg-[#222] rounded-lg opacity-50" />
                        </div>
                    </div>
                </div>

                {/* Action Button */}
                <div className="absolute inset-x-6 bottom-6">
                    <Button 
                        onClick={handleRunPreview}
                        disabled={!previewCode || isPreviewRunning}
                        className={`w-full text-xs tracking-widest uppercase h-12 ${
                            isPreviewRunning 
                                ? 'bg-purple-600 cursor-wait' 
                                : previewCode 
                                    ? 'bg-gradient-to-r from-blue-600 to-purple-600 hover:opacity-90' 
                                    : 'bg-[#1F1F1F] text-zinc-500 cursor-not-allowed'
                        }`}
                    >
                        {isPreviewRunning ? (
                            <>
                                <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin mr-2" />
                                Running Preview...
                            </>
                        ) : previewCode ? (
                            <>
                                <Play className="w-3 h-3 mr-2" />
                                Run Interactive Preview
                            </>
                        ) : (
                            'No Code Available'
                        )}
                    </Button>
                </div>
            </CardContent>
        </Card>
    );
}