# modules/debug/webui_server.py
import argparse
import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from modules.debug.context_snapshot import context_snapshot_store
from modules.debug.phone_trace import phone_trace_store


HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Yuki Sweet-Cyber Console 🌸</title>
  <style>
    :root {
      color-scheme: light;
      --bg-base: #fff5f9;
      --bg-sec: #ffeaf3;
      --card: rgba(255, 255, 255, 0.84);
      --card-strong: rgba(255, 255, 255, 0.94);
      --card-soft: rgba(255, 240, 247, 0.72);
      --line: rgba(255, 110, 168, 0.22);
      --line-strong: rgba(255, 77, 148, 0.48);
      --text: #341628;
      --text-sec: #6e445c;
      --muted: #a47690;
      --pink: #ff4785;
      --pink-soft: #ff85b3;
      --pink-pale: #ffe0ed;
      --berry: #d61f69;
      --purple: #9b5de5;
      --purple-pale: #f3e8ff;
      --cyan: #00b4d8;
      --cyan-pale: #e0f7fc;
      --mint: #10b981;
      --mint-pale: #d1fae5;
      --amber: #f59e0b;
      --amber-pale: #fef3c7;
      --coral: #f43f5e;
      --coral-pale: #ffe4e6;
      --shadow-sm: 0 6px 20px -4px rgba(236, 72, 153, 0.10), 0 2px 6px rgba(236, 72, 153, 0.05);
      --shadow-md: 0 16px 40px -10px rgba(236, 72, 153, 0.15), 0 4px 12px rgba(236, 72, 153, 0.06);
      --shadow-glow: 0 8px 26px -4px rgba(255, 71, 133, 0.35);
      --grad-primary: linear-gradient(135deg, #ff4785 0%, #ff75a8 52%, #b565ff 100%);
      --grad-soft: linear-gradient(135deg, rgba(255, 71, 133, 0.12) 0%, rgba(181, 101, 255, 0.12) 100%);
      --grad-bar: linear-gradient(90deg, #ff4785, #ff85b3, #b565ff, #38bdf8, #ff4785);
      --ease-spring: cubic-bezier(0.22, 1, 0.36, 1);
    }

    * { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; min-height: 100vh; }
    body {
      font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Segoe UI", system-ui, sans-serif;
      color: var(--text);
      background-color: var(--bg-base);
      background-image:
        radial-gradient(circle at 8% 10%, rgba(255, 117, 168, 0.25), transparent 36%),
        radial-gradient(circle at 88% 8%, rgba(181, 101, 255, 0.20), transparent 34%),
        radial-gradient(circle at 50% 92%, rgba(255, 158, 196, 0.22), transparent 40%),
        linear-gradient(rgba(255, 110, 168, 0.05) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255, 110, 168, 0.05) 1px, transparent 1px);
      background-size: 100% 100%, 100% 100%, 100% 100%, 28px 28px, 28px 28px;
      background-attachment: fixed;
      overflow-x: hidden;
    }

    /* 樱花星光背景粒子层 */
    #sakuraCanvas {
      position: fixed;
      inset: 0;
      width: 100vw;
      height: 100vh;
      pointer-events: none;
      z-index: 0;
      opacity: 0.75;
    }

    /* 自定义滚动条 */
    ::-webkit-scrollbar { width: 7px; height: 7px; }
    ::-webkit-scrollbar-track { background: rgba(255, 214, 232, 0.35); border-radius: 99px; }
    ::-webkit-scrollbar-thumb {
      background: linear-gradient(180deg, #ff85b3, #ff4785);
      border-radius: 99px;
    }
    ::-webkit-scrollbar-thumb:hover { background: var(--berry); }

    @keyframes shimmerFlow {
      0% { background-position: 0% 50%; }
      100% { background-position: 200% 50%; }
    }
    @keyframes floatBob {
      0%, 100% { transform: translateY(0px); }
      50% { transform: translateY(-4px); }
    }
    @keyframes pulseRing {
      0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.55); }
      70% { box-shadow: 0 0 0 8px rgba(16, 185, 129, 0); }
      100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
    }
    @keyframes pinkPulse {
      0% { box-shadow: 0 0 0 0 rgba(255, 71, 133, 0.5); }
      70% { box-shadow: 0 0 0 9px rgba(255, 71, 133, 0); }
      100% { box-shadow: 0 0 0 0 rgba(255, 71, 133, 0); }
    }
    @keyframes fadeSlideUp {
      from { opacity: 0; transform: translateY(10px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .app-shell {
      position: relative;
      z-index: 1;
      width: min(1780px, calc(100vw - 28px));
      margin: 0 auto;
      padding: 16px 0 36px;
    }

    /* 玻璃态卡片通用 */
    .glass {
      background: var(--card);
      backdrop-filter: blur(20px) saturate(150%);
      -webkit-backdrop-filter: blur(20px) saturate(150%);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow-sm), inset 0 1px 0 rgba(255, 255, 255, 0.92);
      transition: transform 0.25s var(--ease-spring), box-shadow 0.25s var(--ease-spring), border-color 0.25s ease;
    }
    .glass:hover {
      border-color: rgba(255, 71, 133, 0.34);
    }

    /* 顶栏 Hero */
    .top-nav {
      padding: 16px 22px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      flex-wrap: wrap;
      position: relative;
      overflow: hidden;
    }
    .top-nav::before {
      content: "";
      position: absolute;
      top: 0; left: 0; right: 0;
      height: 3.5px;
      background: var(--grad-bar);
      background-size: 200% 100%;
      animation: shimmerFlow 5s linear infinite;
    }

    .brand-wrap {
      display: flex;
      align-items: center;
      gap: 14px;
    }
    .mascot-avatar {
      width: 56px;
      height: 56px;
      border-radius: 18px;
      background: var(--grad-primary);
      padding: 2.5px;
      box-shadow: var(--shadow-glow);
      position: relative;
      animation: floatBob 3.6s ease-in-out infinite;
      cursor: pointer;
      flex-shrink: 0;
    }
    .mascot-avatar-inner {
      width: 100%;
      height: 100%;
      border-radius: 15.5px;
      background: #fff0f6;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      font-size: 28px;
    }
    .mascot-avatar-inner img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    .mascot-online-dot {
      position: absolute;
      right: -3px;
      bottom: -3px;
      width: 15px;
      height: 15px;
      border-radius: 50%;
      background: var(--mint);
      border: 2.5px solid #fff;
      animation: pulseRing 2s infinite;
    }
    .brand-title {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .brand-title h1 {
      margin: 0;
      font-size: 23px;
      font-weight: 800;
      letter-spacing: -0.02em;
      background: linear-gradient(135deg, #d61f69 0%, #ff4785 45%, #8b3dff 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .cyber-tag {
      font-size: 11px;
      font-weight: 700;
      padding: 3px 9px;
      border-radius: 999px;
      background: var(--grad-primary);
      color: #fff;
      box-shadow: 0 3px 10px rgba(255, 71, 133, 0.3);
      letter-spacing: 0.04em;
    }
    .brand-sub {
      margin-top: 4px;
      font-size: 12.5px;
      color: var(--text-sec);
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }

    /* 主导航切换器 */
    .tab-switcher {
      display: inline-flex;
      background: rgba(255, 224, 237, 0.65);
      border: 1px solid rgba(255, 110, 168, 0.25);
      padding: 5px;
      border-radius: 16px;
      gap: 5px;
    }
    .tab-btn {
      border: none;
      background: transparent;
      color: var(--text-sec);
      font-weight: 700;
      font-size: 13.5px;
      padding: 8px 16px;
      border-radius: 12px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 7px;
      transition: all 0.25s var(--ease-spring);
    }
    .tab-btn:hover {
      color: var(--berry);
      background: rgba(255, 255, 255, 0.55);
    }
    .tab-btn.active {
      background: var(--grad-primary);
      color: #fff;
      box-shadow: var(--shadow-glow);
      transform: translateY(-1px);
    }
    .tab-count {
      padding: 1px 7px;
      border-radius: 99px;
      font-size: 11px;
      background: rgba(255, 255, 255, 0.26);
      color: inherit;
    }
    .tab-btn:not(.active) .tab-count {
      background: rgba(255, 71, 133, 0.14);
      color: var(--berry);
    }

    /* 顶栏右侧操作按钮 */
    .top-actions {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .btn {
      border: 1px solid var(--line);
      background: var(--card-strong);
      color: var(--text);
      padding: 8px 13px;
      border-radius: 12px;
      font-size: 12.5px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      text-decoration: none;
      transition: all 0.2s var(--ease-spring);
      box-shadow: 0 2px 6px rgba(236, 72, 153, 0.06);
    }
    .btn:hover {
      border-color: var(--pink);
      color: var(--berry);
      transform: translateY(-1.5px);
      box-shadow: 0 6px 14px rgba(255, 71, 133, 0.15);
    }
    .btn:active { transform: translateY(0); }
    .btn.primary {
      background: var(--grad-primary);
      color: #fff;
      border-color: transparent;
      box-shadow: var(--shadow-glow);
    }
    .btn.primary:hover {
      color: #fff;
      filter: brightness(1.05);
    }
    .btn.soft-active {
      background: var(--pink-pale);
      border-color: var(--pink);
      color: var(--berry);
    }
    .btn-sm {
      padding: 4px 9px;
      font-size: 11.5px;
      border-radius: 9px;
    }

    /* 顶部 Yuki 实时状态舱 (Brain & Energy Ribbon) */
    .brain-ribbon {
      margin-top: 12px;
      padding: 11px 18px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      flex-wrap: wrap;
      border-radius: 20px;
    }
    .ribbon-left, .ribbon-right {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 5px 11px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 600;
      background: rgba(255, 255, 255, 0.85);
      border: 1px solid var(--line);
      color: var(--text-sec);
    }
    .status-pill b { color: var(--berry); }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--mint);
      display: inline-block;
    }
    .dot.pink { background: var(--pink); animation: pinkPulse 2s infinite; }
    .dot.warn { background: var(--amber); }
    .dot.err { background: var(--coral); }

    /* 群组迷你精力胶囊条 */
    .group-mini-pills {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .group-mini {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      padding: 4px 10px;
      border-radius: 11px;
      background: rgba(255, 255, 255, 0.9);
      border: 1px solid rgba(255, 110, 168, 0.24);
      font-size: 11.5px;
      cursor: pointer;
      transition: all 0.2s ease;
    }
    .group-mini:hover {
      border-color: var(--pink);
      transform: translateY(-1px);
    }
    .mini-bar {
      width: 44px;
      height: 6px;
      border-radius: 99px;
      background: #ffe0ed;
      overflow: hidden;
    }
    .mini-bar-fill {
      height: 100%;
      border-radius: 99px;
      background: var(--grad-primary);
      transition: width 0.4s var(--ease-spring);
    }

    /* 视图面板切换 */
    .tab-pane {
      display: none;
      margin-top: 14px;
      animation: fadeSlideUp 0.28s var(--ease-spring);
    }
    .tab-pane.active { display: block; }

    /* ==================== TAB 1: CONTEXT STUDIO ==================== */
    .context-grid {
      display: grid;
      grid-template-columns: 330px minmax(0, 1fr) 360px;
      gap: 14px;
      align-items: start;
    }
    .panel-card {
      padding: 16px;
      min-width: 0;
    }
    .card-title {
      margin: 0 0 12px;
      font-size: 15px;
      font-weight: 800;
      color: var(--text);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .card-title-left {
      display: inline-flex;
      align-items: center;
      gap: 7px;
    }

    /* 搜索与筛选栏 */
    .search-input {
      width: 100%;
      padding: 9px 12px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.92);
      color: var(--text);
      font-size: 12.5px;
      outline: none;
      transition: border-color 0.2s, box-shadow 0.2s;
    }
    .search-input:focus {
      border-color: var(--pink);
      box-shadow: 0 0 0 3px rgba(255, 71, 133, 0.15);
    }
    .filter-chips {
      display: flex;
      gap: 5px;
      flex-wrap: wrap;
      margin: 9px 0 11px;
    }
    .chip {
      padding: 4px 9px;
      border-radius: 999px;
      font-size: 11.5px;
      font-weight: 600;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.75);
      color: var(--text-sec);
      cursor: pointer;
      transition: all 0.18s ease;
    }
    .chip:hover { border-color: var(--pink); color: var(--berry); }
    .chip.active {
      background: var(--grad-primary);
      color: #fff;
      border-color: transparent;
      box-shadow: 0 3px 10px rgba(255, 71, 133, 0.25);
    }

    /* 左侧会话列表 */
    .session-list {
      display: grid;
      gap: 9px;
      max-height: calc(100vh - 280px);
      overflow-y: auto;
      padding-right: 3px;
    }
    .sess-card {
      padding: 11px 13px;
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.78);
      cursor: pointer;
      transition: all 0.22s var(--ease-spring);
      position: relative;
      overflow: hidden;
    }
    .sess-card:hover {
      border-color: var(--pink-soft);
      transform: translateX(3px);
      background: #fff;
    }
    .sess-card.active {
      border-color: var(--pink);
      background: linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(255, 232, 243, 0.92));
      box-shadow: 0 8px 22px -6px rgba(255, 71, 133, 0.25), inset 3.5px 0 0 var(--pink);
    }
    .sess-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 6px;
      margin-bottom: 5px;
    }
    .sess-chat {
      font-weight: 800;
      font-size: 13px;
      color: var(--text);
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }
    .sess-in {
      font-size: 12px;
      color: var(--text-sec);
      line-height: 1.45;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
      word-break: break-all;
    }
    .sess-out {
      margin-top: 5px;
      padding: 4px 8px;
      border-radius: 8px;
      background: rgba(255, 71, 133, 0.08);
      color: var(--berry);
      font-size: 11.5px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .sess-meta {
      margin-top: 6px;
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      font-size: 11px;
      color: var(--muted);
    }

    /* 糖果色徽章 */
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 700;
      white-space: nowrap;
    }
    .badge.replied, .badge.running {
      background: var(--mint-pale);
      color: #047857;
      border: 1px solid #a7f3d0;
    }
    .badge.dived, .badge.finished {
      background: var(--purple-pale);
      color: #6d28d9;
      border: 1px solid #ddd6fe;
    }
    .badge.skip, .badge.time {
      background: var(--amber-pale);
      color: #b45309;
      border: 1px solid #fde68a;
    }
    .badge.err {
      background: var(--coral-pale);
      color: #be123c;
      border: 1px solid #fecdd3;
    }
    .badge.pink {
      background: var(--pink-pale);
      color: var(--berry);
      border: 1px solid rgba(255, 71, 133, 0.3);
    }
    .badge.cyan {
      background: var(--cyan-pale);
      color: #0369a1;
      border: 1px solid #bae6fd;
    }

    /* 中栏：本轮对话速览卡 (Turn Hero Summary Card) */
    .turn-hero {
      padding: 16px;
      border-radius: 20px;
      background: linear-gradient(135deg, rgba(255, 255, 255, 0.95), rgba(255, 236, 245, 0.88));
      border: 1px solid rgba(255, 71, 133, 0.28);
      box-shadow: var(--shadow-sm);
      margin-bottom: 14px;
    }
    .turn-bubbles {
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      gap: 12px;
      align-items: stretch;
    }
    .turn-box {
      padding: 12px 14px;
      border-radius: 16px;
      background: #fff;
      border: 1px solid var(--line);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      min-width: 0;
    }
    .turn-box.out-box {
      background: linear-gradient(135deg, #fff9fc 0%, #fff0f7 100%);
      border-color: rgba(255, 71, 133, 0.35);
    }
    .turn-box-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      font-weight: 700;
      color: var(--text-sec);
      margin-bottom: 6px;
    }
    .turn-box-body {
      font-size: 13.5px;
      line-height: 1.6;
      color: var(--text);
      word-break: break-word;
      max-height: 120px;
      overflow-y: auto;
      white-space: pre-wrap;
    }
    .turn-bridge {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 5px;
      padding: 0 4px;
      min-width: 110px;
    }
    .meme-tag {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 2px 8px;
      margin: 0 3px;
      border-radius: 99px;
      background: var(--grad-primary);
      color: #fff;
      font-size: 11.5px;
      font-weight: 700;
    }

    /* 8阶段管线瀑布条 */
    .pipeline-strip {
      display: grid;
      grid-template-columns: repeat(8, minmax(0, 1fr));
      gap: 6px;
      margin-top: 12px;
    }
    .stage-node {
      padding: 8px 9px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.72);
      font-size: 11.5px;
      transition: all 0.2s ease;
      position: relative;
      overflow: hidden;
    }
    .stage-node.done {
      border-color: rgba(16, 185, 129, 0.42);
      background: rgba(236, 253, 245, 0.85);
    }
    .stage-node.active {
      border-color: var(--pink);
      background: var(--pink-pale);
    }
    .stage-node.error {
      border-color: var(--coral);
      background: var(--coral-pale);
    }
    .stage-node .st-idx {
      font-size: 10px;
      font-weight: 700;
      color: var(--muted);
    }
    .stage-node .st-name {
      font-weight: 700;
      color: var(--text);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      margin: 2px 0;
    }
    .stage-node .st-time {
      font-size: 11px;
      font-weight: 700;
      color: var(--berry);
    }

    /* 工具调用链面板 */
    .tool-trace-box {
      margin-bottom: 14px;
      padding: 12px 14px;
      border-radius: 16px;
      background: rgba(254, 243, 199, 0.55);
      border: 1px solid #fde68a;
    }
    .tool-round-item {
      padding: 8px 10px;
      border-radius: 11px;
      background: rgba(255, 255, 255, 0.88);
      border: 1px solid rgba(245, 158, 11, 0.25);
      font-size: 12px;
      margin-top: 7px;
    }

    /* LLM Messages 气泡流 */
    .msg-toolbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 10px;
    }
    .messages-stream {
      display: grid;
      gap: 9px;
      max-height: calc(100vh - 380px);
      overflow-y: auto;
      padding-right: 4px;
    }
    details.msg-card {
      border: 1px solid var(--line);
      border-radius: 16px;
      background: rgba(255, 255, 255, 0.88);
      overflow: hidden;
      transition: border-color 0.2s, box-shadow 0.2s;
    }
    details.msg-card[open] {
      box-shadow: 0 6px 18px rgba(236, 72, 153, 0.08);
    }
    details.msg-card.role-system {
      background: linear-gradient(135deg, rgba(243, 232, 255, 0.55), rgba(255, 255, 255, 0.9));
      border-color: rgba(155, 93, 229, 0.28);
    }
    details.msg-card.role-user {
      background: linear-gradient(135deg, rgba(224, 247, 252, 0.55), rgba(255, 255, 255, 0.94));
      border-color: rgba(0, 180, 216, 0.30);
    }
    details.msg-card.role-assistant {
      background: linear-gradient(135deg, rgba(255, 224, 237, 0.60), rgba(255, 255, 255, 0.95));
      border-color: rgba(255, 71, 133, 0.34);
    }
    details.msg-card.role-tool {
      background: linear-gradient(135deg, rgba(254, 243, 199, 0.55), rgba(255, 255, 255, 0.92));
      border-color: rgba(245, 158, 11, 0.32);
    }
    details.msg-card summary {
      cursor: pointer;
      padding: 10px 14px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      list-style: none;
      user-select: none;
    }
    details.msg-card summary::-webkit-details-marker { display: none; }
    .msg-sum-left {
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
      flex: 1;
    }
    .msg-snippet {
      font-size: 12px;
      color: var(--text-sec);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    details.msg-card[open] .msg-snippet { display: none; }
    .role-pill {
      padding: 3px 9px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      flex-shrink: 0;
    }
    .role-pill.system { background: var(--purple-pale); color: #6d28d9; }
    .role-pill.user { background: var(--cyan-pale); color: #0369a1; }
    .role-pill.assistant { background: var(--pink-pale); color: var(--berry); }
    .role-pill.tool { background: var(--amber-pale); color: #b45309; }

    .msg-content {
      padding: 10px 14px 14px;
      border-top: 1px dashed rgba(255, 110, 168, 0.2);
      font-size: 13px;
      line-height: 1.65;
      white-space: pre-wrap;
      word-break: break-word;
      color: var(--text);
      max-height: 440px;
      overflow-y: auto;
      font-family: "PingFang SC", "Microsoft YaHei", ui-monospace, SFMono-Regular, Menlo, monospace;
    }

    /* 右栏：Token 分布与 RAG 记忆 */
    .right-stack {
      display: grid;
      gap: 14px;
    }
    .token-role-row {
      display: grid;
      grid-template-columns: 72px 1fr 68px;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      margin-top: 7px;
    }
    .progress-track {
      height: 8px;
      border-radius: 99px;
      background: rgba(255, 194, 219, 0.35);
      overflow: hidden;
    }
    .progress-fill {
      height: 100%;
      border-radius: 99px;
      transition: width 0.45s var(--ease-spring);
    }
    .diary-card {
      padding: 11px 12px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.85);
      font-size: 12.5px;
      line-height: 1.55;
      color: var(--text);
      margin-bottom: 8px;
    }
    .diary-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 5px;
      font-size: 11px;
      color: var(--muted);
    }
    .json-pre {
      white-space: pre-wrap;
      word-break: break-word;
      max-height: 260px;
      overflow: auto;
      font-size: 11.5px;
      line-height: 1.5;
      color: var(--text-sec);
      background: rgba(255, 240, 247, 0.75);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 10px;
      font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
    }

    /* ==================== TAB 2: ANALYTICS & BRAIN ==================== */
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 14px;
    }
    .kpi-card {
      padding: 15px 16px;
      position: relative;
      overflow: hidden;
    }
    .kpi-card .kpi-label {
      font-size: 12px;
      font-weight: 700;
      color: var(--text-sec);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .kpi-card .kpi-val {
      font-size: 26px;
      font-weight: 900;
      margin: 6px 0 4px;
      background: var(--grad-primary);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .kpi-card .kpi-sub {
      font-size: 11.5px;
      color: var(--muted);
    }

    .analytics-row-2 {
      display: grid;
      grid-template-columns: 1.35fr 1fr;
      gap: 14px;
      margin-bottom: 14px;
    }
    .analytics-row-3 {
      display: grid;
      grid-template-columns: 1fr 1.15fr 1fr;
      gap: 14px;
    }
    .group-gauge-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
      gap: 10px;
      max-height: 290px;
      overflow-y: auto;
    }
    .group-gauge-card {
      padding: 12px;
      border-radius: 16px;
      background: rgba(255, 255, 255, 0.88);
      border: 1px solid var(--line);
    }
    .waterfall-row {
      display: grid;
      grid-template-columns: 115px 1fr 78px;
      align-items: center;
      gap: 10px;
      font-size: 12px;
      margin-bottom: 9px;
    }
    .svg-chart-wrap {
      width: 100%;
      overflow: hidden;
    }

    /* ==================== TAB 3: PHONE MONITOR ==================== */
    .phone-grid {
      display: grid;
      grid-template-columns: 350px minmax(0, 1fr) 450px;
      gap: 14px;
      align-items: start;
    }
    .phone-screens {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }
    .phone-bezel {
      border-radius: 28px;
      padding: 12px 12px 14px;
      background: linear-gradient(160deg, #fff5fa 0%, #ffe0ee 100%);
      border: 2px solid rgba(255, 71, 133, 0.35);
      box-shadow: var(--shadow-md), inset 0 2px 4px #fff;
      display: flex;
      flex-direction: column;
      align-items: center;
    }
    .phone-notch {
      width: 86px;
      height: 14px;
      border-radius: 99px;
      background: rgba(255, 71, 133, 0.20);
      margin-bottom: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
    }
    .phone-notch i {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--pink);
    }
    .phone-screen-head {
      width: 100%;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 6px;
      margin-bottom: 8px;
      font-size: 13px;
    }
    .img-wrap {
      width: 100%;
      min-height: 470px;
      max-height: 66vh;
      display: flex;
      align-items: center;
      justify-content: center;
      background: radial-gradient(circle, #2a1523 0%, #160a13 100%);
      border-radius: 18px;
      overflow: hidden;
      position: relative;
      border: 1px solid rgba(255, 71, 133, 0.25);
    }
    .img-wrap img {
      max-width: 100%;
      max-height: 64vh;
      object-fit: contain;
      cursor: zoom-in;
      border-radius: 10px;
      transition: transform 0.2s ease;
    }
    .timing-bar {
      width: 100%;
      margin-top: 10px;
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      font-size: 11.5px;
    }
    .timing-chip {
      padding: 4px 8px;
      border-radius: 9px;
      background: rgba(255, 255, 255, 0.88);
      border: 1px solid var(--line);
      color: var(--text-sec);
    }
    .timing-seg-bar {
      width: 100%;
      height: 8px;
      border-radius: 99px;
      background: rgba(255, 255, 255, 0.7);
      overflow: hidden;
      display: flex;
      margin-top: 8px;
    }
    .list-box {
      display: grid;
      gap: 8px;
      max-height: 33vh;
      overflow-y: auto;
      padding-right: 3px;
    }
    .step-list-box {
      display: grid;
      gap: 8px;
      max-height: 44vh;
      overflow-y: auto;
      padding-right: 3px;
    }
    .item {
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.82);
      cursor: pointer;
      transition: all 0.18s var(--ease-spring);
    }
    .item:hover {
      border-color: var(--pink);
      background: #fff;
      transform: translateX(2px);
    }
    .item.active {
      border-color: var(--pink);
      background: linear-gradient(135deg, #fff 0%, #ffe6f1 100%);
      box-shadow: 0 6px 16px -4px rgba(255, 71, 133, 0.22), inset 3px 0 0 var(--pink);
    }
    .item-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      margin-bottom: 4px;
      font-size: 13px;
    }
    .sub, .muted { color: var(--muted); font-size: 12px; }
    .text-panel { display: grid; gap: 12px; }
    .box {
      border: 1px solid var(--line);
      border-radius: 16px;
      background: rgba(255, 255, 255, 0.88);
      padding: 12px;
    }
    .box h3 {
      margin: 0 0 8px;
      font-size: 13px;
      color: var(--berry);
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 6px;
    }
    .pre {
      white-space: pre-wrap;
      word-break: break-word;
      font-size: 12.5px;
      line-height: 1.6;
      color: var(--text);
      max-height: 230px;
      overflow: auto;
      font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
      background: rgba(255, 245, 250, 0.65);
      padding: 8px 10px;
      border-radius: 10px;
      border: 1px solid rgba(255, 110, 168, 0.14);
    }
    .empty {
      padding: 32px 16px;
      text-align: center;
      color: var(--muted);
      font-size: 13px;
    }
    .modal {
      position: fixed;
      inset: 0;
      background: rgba(45, 16, 34, 0.78);
      backdrop-filter: blur(8px);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 999;
      padding: 24px;
    }
    .modal img {
      max-width: 95vw;
      max-height: 92vh;
      object-fit: contain;
      border-radius: 16px;
      box-shadow: 0 24px 60px rgba(0, 0, 0, 0.45);
    }

    /* Toast 提示 */
    #toast {
      position: fixed;
      bottom: 24px;
      right: 24px;
      padding: 10px 18px;
      border-radius: 999px;
      background: var(--grad-primary);
      color: #fff;
      font-size: 13px;
      font-weight: 700;
      box-shadow: var(--shadow-glow);
      transform: translateY(80px);
      opacity: 0;
      transition: all 0.3s var(--ease-spring);
      z-index: 1000;
      pointer-events: none;
    }
    #toast.show {
      transform: translateY(0);
      opacity: 1;
    }

    @media (max-width: 1360px) {
      .context-grid, .phone-grid, .analytics-row-2, .analytics-row-3 { grid-template-columns: 1fr; }
      .kpi-grid { grid-template-columns: repeat(2, 1fr); }
      .turn-bubbles { grid-template-columns: 1fr; }
      .pipeline-strip { grid-template-columns: repeat(4, 1fr); }
      .phone-screens { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
<canvas id="sakuraCanvas"></canvas>

<main class="app-shell">
  <!-- 顶部主控台导航 -->
  <header class="glass top-nav">
    <div class="brand-wrap">
      <div class="mascot-avatar" onclick="openHelpPoster()" title="点击查看 Yuki 观察手册 🌸">
        <div class="mascot-avatar-inner" id="yukiAvatarBox">🌸</div>
        <i class="mascot-online-dot" id="onlineDot"></i>
      </div>
      <div>
        <div class="brand-title">
          <h1>Yuki Sweet-Cyber Console</h1>
          <span class="cyber-tag">SAKURA PULSE v2.5 ✨</span>
        </div>
        <div class="brand-sub" id="status">
          <span>(｡•̀ᴗ-)✧ 正在连接 Yuki 核心脑波...</span>
        </div>
      </div>
    </div>

    <!-- 三大工作台丝滑切换 -->
    <nav class="tab-switcher" role="tablist">
      <button class="tab-btn active" id="tabBtn-context" onclick="switchTab('context')">
        <span>💬 对话 &amp; 上下文工作台</span>
        <span class="tab-count" id="navSnapCount">0</span>
      </button>
      <button class="tab-btn" id="tabBtn-analytics" onclick="switchTab('analytics')">
        <span>📊 遥测分析 &amp; 脑波大屏</span>
        <span class="tab-count" id="navReplyRate">--%</span>
      </button>
      <button class="tab-btn" id="tabBtn-phone" onclick="switchTab('phone')">
        <span>📱 手机灵动监控台</span>
        <span class="tab-count" id="navPhoneCount">0</span>
      </button>
    </nav>

    <div class="top-actions">
      <button class="btn" onclick="refreshEverything(true)">🔄 立即刷新</button>
      <button class="btn soft-active" id="pauseBtn" onclick="togglePause()">⚡ 自动同步: 开启</button>
      <button class="btn" id="petalBtn" onclick="togglePetals()">🌸 樱花粒子</button>
      <button class="btn" onclick="openHelpPoster()">📖 观察手册</button>
    </div>
  </header>

  <!-- 顶部 Yuki 实时生理与精力状态舱 -->
  <section class="glass brain-ribbon" id="brainRibbon">
    <div class="ribbon-left" id="ribbonBioclock">
      <span class="status-pill"><i class="dot pink"></i>生物钟加载中...</span>
    </div>
    <div class="group-mini-pills" id="ribbonGroups"></div>
  </section>

  <!-- ==================== TAB 1: 对话 & 上下文工作台 ==================== -->
  <section class="tab-pane active" id="pane-context">
    <div class="context-grid">
      <!-- 左栏：智能会话流 -->
      <aside class="glass panel-card">
        <div class="card-title">
          <span class="card-title-left">🗂️ 最近对话快照</span>
          <span class="muted" id="filteredSnapCount">0 条</span>
        </div>
        <input type="search" id="sessSearch" class="search-input" placeholder="🔍 搜索群号 / 消息 / 回复内容..." oninput="renderSessions()" />
        <div class="filter-chips">
          <button class="chip active" data-filter="all" onclick="setSessFilter('all', this)">全部</button>
          <button class="chip" data-filter="replied" onclick="setSessFilter('replied', this)">💬 已回复</button>
          <button class="chip" data-filter="dived" onclick="setSessFilter('dived', this)">🫧 潜水/Skip</button>
          <button class="chip" data-filter="tools" onclick="setSessFilter('tools', this)">🔧 含工具</button>
          <button class="chip" data-filter="group" onclick="setSessFilter('group', this)">👥 群聊</button>
          <button class="chip" data-filter="private" onclick="setSessFilter('private', this)">💌 私聊</button>
        </div>
        <div id="sessions" class="session-list">
          <div class="empty">暂无 snapshot</div>
        </div>
      </aside>

      <!-- 中栏：本轮对话速览 + 管线瀑布 + 上下文气泡流 -->
      <section class="glass panel-card">
        <div class="turn-hero" id="turnHeroCard">
          <div class="card-title" style="margin-bottom:10px">
            <span class="card-title-left" id="turnHeroTitle">🎀 本轮收发速览</span>
            <div style="display:flex;gap:6px;flex-wrap:wrap">
              <button class="btn btn-sm" onclick="copySnapshot()">📋 复制整包 JSON</button>
              <button class="btn btn-sm" onclick="downloadSnapshot()">💾 导出 Snapshot</button>
            </div>
          </div>

          <div class="turn-bubbles">
            <div class="turn-box">
              <div class="turn-box-head">
                <span id="turnSenderLabel">📥 收到用户消息</span>
                <button class="btn btn-sm" onclick="copyField('combined_text')">复制</button>
              </div>
              <div class="turn-box-body" id="turnIncomingBox">等待选择会话...</div>
            </div>

            <div class="turn-bridge" id="turnDecisionBridge">
              <span class="badge pink">等待中</span>
            </div>

            <div class="turn-box out-box">
              <div class="turn-box-head">
                <span>📤 Yuki 最终回复</span>
                <button class="btn btn-sm" onclick="copyField('answer_text')">复制</button>
              </div>
              <div class="turn-box-body" id="turnAnswerBox">等待生成...</div>
            </div>
          </div>

          <!-- 8 阶段管线实时瀑布 -->
          <div id="timeline" class="pipeline-strip"></div>
        </div>

        <!-- 工具调用链追踪 (有工具调用时显示) -->
        <div id="toolTraceWrap" class="tool-trace-box" style="display:none"></div>

        <!-- 完整构建上下文 Messages -->
        <div class="msg-toolbar">
          <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
            <b style="font-size:14.5px">🧠 完整构建上下文 (Built Messages)</b>
            <div class="filter-chips" style="margin:0">
              <button class="chip active" onclick="setMsgRoleFilter('all', this)">全部</button>
              <button class="chip" onclick="setMsgRoleFilter('system', this)">System</button>
              <button class="chip" onclick="setMsgRoleFilter('user', this)">User</button>
              <button class="chip" onclick="setMsgRoleFilter('assistant', this)">Assistant</button>
              <button class="chip" onclick="setMsgRoleFilter('tool', this)">Tool</button>
            </div>
          </div>
          <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
            <input type="search" id="msgSearchInput" class="search-input" style="width:170px;padding:5px 10px" placeholder="搜索上下文正文..." oninput="renderMessagesList()" />
            <button class="btn btn-sm" onclick="toggleAllMessages(true)">展开全部</button>
            <button class="btn btn-sm" onclick="toggleAllMessages(false)">折叠全部</button>
          </div>
        </div>
        <div id="messages" class="messages-stream empty">暂无 snapshot</div>
      </section>

      <!-- 右栏：Token 构成 & RAG 记忆召回 & JSON -->
      <aside class="right-stack">
        <div class="glass panel-card">
          <div class="card-title">
            <span class="card-title-left">🪙 Token 角色构成分析</span>
            <span class="badge pink" id="totalTokenBadge">0 tok</span>
          </div>
          <div id="tokenBreakdownBox"></div>
        </div>

        <div class="glass panel-card">
          <div class="card-title">
            <span class="card-title-left">📚 RAG 记忆日记召回</span>
            <span class="badge cyan" id="ragCountBadge">0 条</span>
          </div>
          <div id="memories" style="max-height:340px;overflow-y:auto;padding-right:2px"></div>
        </div>

        <div class="glass panel-card">
          <details>
            <summary style="cursor:pointer;font-weight:800;font-size:13.5px;display:flex;justify-content:space-between;align-items:center">
              <span>🧩 原始 Snapshot JSON</span>
              <span class="muted">点击展开</span>
            </summary>
            <div style="margin-top:10px">
              <div id="snapshotJson" class="json-pre">{}</div>
            </div>
          </details>
        </div>
      </aside>
    </div>
  </section>

  <!-- ==================== TAB 2: 遥测分析 & 脑波监控 ==================== -->
  <section class="tab-pane" id="pane-analytics">
    <div class="kpi-grid" id="analyticsKpiGrid"></div>

    <div class="analytics-row-2">
      <div class="glass panel-card">
        <div class="card-title">
          <span class="card-title-left">🌙 Yuki 24 小时生物钟平滑律动曲线 (Bioclock Curve)</span>
          <span class="badge pink" id="bioclockPhaseBadge">加载中</span>
        </div>
        <div id="bioclockChartBox" class="svg-chart-wrap"></div>
      </div>

      <div class="glass panel-card">
        <div class="card-title">
          <span class="card-title-left">🔋 群聊精力池 · 刷屏热度 · 说话欲望实时矩阵</span>
          <span class="muted">Cost=4 / 恢复=0.8/min</span>
        </div>
        <div id="groupGaugeGrid" class="group-gauge-grid"></div>
      </div>
    </div>

    <div class="analytics-row-3">
      <div class="glass panel-card">
        <div class="card-title">
          <span class="card-title-left">⏱️ 管线 8 阶段平均耗时瀑布</span>
          <span class="muted" id="stageTotalAvgLabel">Avg -- ms</span>
        </div>
        <div id="stageWaterfallBox"></div>
      </div>

      <div class="glass panel-card">
        <div class="card-title">
          <span class="card-title-left">📈 最近 24 轮 Token 角色堆叠趋势 (点击柱子跳转)</span>
          <span class="muted">System / User / Assistant / Tool</span>
        </div>
        <div id="tokenTrendChartBox" class="svg-chart-wrap"></div>
      </div>

      <div class="glass panel-card">
        <div class="card-title">
          <span class="card-title-left">🎯 回复决策分布 &amp; 工具调用 Top 榜</span>
          <span class="muted" id="toolTotalCallsLabel">0 次工具调用</span>
        </div>
        <div id="decisionAndToolsBox"></div>
      </div>
    </div>
  </section>

  <!-- ==================== TAB 3: 手机实时监控 & 轨迹回放 ==================== -->
  <section class="tab-pane" id="pane-phone">
    <div class="glass panel-card" style="margin-bottom:14px;padding:12px 18px">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">
        <div id="statusPills" style="display:flex;gap:8px;flex-wrap:wrap;align-items:center"></div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button id="followBtn" class="btn soft-active" onclick="toggleFollow()">🎯 自动跟随最新步</button>
          <button id="liveBtn" class="btn soft-active" onclick="toggleLive()">🟢 实时画面流: 开启</button>
          <button class="btn" onclick="refreshLiveImage(true)">📸 立即抓屏</button>
          <button class="btn" onclick="refreshPhoneData()">🔄 刷新轨迹</button>
        </div>
      </div>
    </div>

    <div class="phone-grid">
      <!-- 左栏：历史轨迹会话 + 步骤列表 -->
      <aside class="glass panel-card" style="display:grid;gap:14px">
        <div>
          <div class="card-title">
            <span class="card-title-left">🗂️ 手机操作轨迹列表</span>
            <span class="muted" id="sessCount">0 条</span>
          </div>
          <div id="sessionList" class="list-box"><div class="empty">暂无手机操作轨迹</div></div>
        </div>
        <div>
          <div class="card-title">
            <span class="card-title-left">⏱️ 步骤时间轴 (支持 ← / →)</span>
            <span style="display:flex;gap:4px">
              <button class="btn btn-sm" onclick="stepDelta(-1)">◀ 上一步</button>
              <button class="btn btn-sm" onclick="stepDelta(1)">下一步 ▶</button>
            </span>
          </div>
          <div id="stepList" class="step-list-box"><div class="empty">请选择轨迹会话</div></div>
        </div>
      </aside>

      <!-- 中栏：双机位粉色拟物手机壳 -->
      <section class="glass panel-card">
        <div class="phone-screens">
          <div class="phone-bezel">
            <div class="phone-notch"><i></i><span style="width:28px;height:4px;border-radius:9px;background:rgba(255,71,133,.35)"></span></div>
            <div class="phone-screen-head">
              <b>📡 当前手机实时画面 (Live)</b>
              <span class="badge time" id="liveMeta">等待抓拍...</span>
            </div>
            <div class="img-wrap">
              <img id="liveImg" alt="当前手机实时画面" onclick="openModal(this.src)" />
            </div>
            <div class="timing-bar">
              <span class="timing-chip" id="liveHint">每 1.2s 自动从 ADB 拉取当前屏幕</span>
            </div>
          </div>

          <div class="phone-bezel">
            <div class="phone-notch"><i></i><span style="width:28px;height:4px;border-radius:99px;background:rgba(255,71,133,.35)"></span></div>
            <div class="phone-screen-head">
              <b id="stepScreenTitle">👁️ Yuki 看到的画面</b>
              <span style="display:flex;gap:6px;align-items:center">
                <button id="viewModeBtn" class="btn btn-sm" onclick="toggleStepImgMode()">切换: 红框标注图</button>
                <span class="badge pink" id="stepElapsedBadge">- ms</span>
              </span>
            </div>
            <div class="img-wrap">
              <img id="yukiImg" alt="Yuki 看到的画面" onclick="openModal(this.src)" />
            </div>
            <div id="stepTimingSegBar" class="timing-seg-bar"></div>
            <div class="timing-bar" id="stepTimingBar">
              <span class="timing-chip">选择左侧步骤查看当步耗时分解</span>
            </div>
          </div>
        </div>
      </section>

      <!-- 右栏：Yuki 收发原文本 & 控件树过滤 -->
      <aside class="glass panel-card text-panel">
        <div class="box">
          <h3>
            <span>📥 Yuki 收到的用户触发原文本</span>
            <button class="btn btn-sm" onclick="copyText('userIncomingText')">复制</button>
          </h3>
          <div id="userIncomingText" class="pre">暂无</div>
        </div>

        <div class="box">
          <h3>
            <span>📤 Yuki 当步思考 / 调用 + 最终回复</span>
            <button class="btn btn-sm" onclick="copyText('yukiReplyText')">复制</button>
          </h3>
          <div id="yukiReplyText" class="pre">暂无</div>
        </div>

        <div class="box">
          <h3>
            <span>🌲 当步回传给 Yuki 的控件树 / 工具结果</span>
            <div style="display:flex;gap:5px;align-items:center">
              <input type="search" id="treeSearchInput" class="search-input" style="width:125px;padding:3px 8px;font-size:11.5px" placeholder="过滤控件词..." oninput="renderTreeText()" />
              <button class="btn btn-sm" onclick="copyText('toolResultText')">复制</button>
            </div>
          </h3>
          <div id="toolResultText" class="pre" style="max-height:290px">暂无</div>
        </div>
      </aside>
    </div>
  </section>
</main>

<!-- 图片放大预览 Modal -->
<div id="imgModal" class="modal" onclick="this.style.display='none'">
  <img id="modalImg" src="" alt="preview" />
</div>

<div id="toast">✨ 已复制到剪贴板</div>

<script>
const INITIAL_TAB = (() => {
  const p = window.location.pathname;
  if (p.startsWith('/phone')) return 'phone';
  if (p.startsWith('/analytics')) return 'analytics';
  return 'context';
})();

const stages = [
  'prepare_message_batch',
  'normalize_incoming_content',
  'prepare_chat_context',
  'retrieve_memories',
  'decide_reply_action',
  'generate_reply',
  'send_reply',
  'finalize_conversation'
];

const stageShortLabels = {
  prepare_message_batch: '1.读缓冲',
  normalize_incoming_content: '2.归一化',
  prepare_chat_context: '3.载上下文',
  retrieve_memories: '4.RAG回忆',
  decide_reply_action: '5.回复决策',
  generate_reply: '6.LLM生成',
  send_reply: '7.分段发送',
  finalize_conversation: '8.收尾保存'
};

let activeTab = INITIAL_TAB;
let selectedId = null;
let current = null;
let snapshotList = [];
let paused = false;
let sessFilter = 'all';
let msgRoleFilter = 'all';
let analyticsData = null;

// 手机监控状态
let selectedSessionId = null;
let selectedStepIndex = null;
let currentSession = null;
let followLatest = true;
let liveEnabled = true;
let showAnnotated = true;
let liveBusy = false;
let rawTreeCache = '';

function esc(s) {
  return String(s ?? '').replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
}

function fmtMs(ms) {
  const n = Number(ms || 0);
  return n >= 1000 ? (n / 1000).toFixed(2) + 's (' + Math.round(n) + 'ms)' : Math.round(n) + 'ms';
}

function showToast(msg = '✨ 已复制到剪贴板') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(window._toastTimer);
  window._toastTimer = setTimeout(() => t.classList.remove('show'), 1800);
}

async function api(path) {
  const r = await fetch(path);
  return await r.json();
}

function switchTab(tab, pushUrl = true) {
  activeTab = tab;
  ['context', 'analytics', 'phone'].forEach(k => {
    document.getElementById('tabBtn-' + k)?.classList.toggle('active', k === tab);
    document.getElementById('pane-' + k)?.classList.toggle('active', k === tab);
  });
  if (pushUrl && window.history && window.history.replaceState) {
    const targetPath = tab === 'phone' ? '/phone' : (tab === 'analytics' ? '/analytics' : '/');
    if (window.location.pathname !== targetPath) {
      window.history.replaceState({ tab }, '', targetPath);
    }
  }
  if (tab === 'analytics') refreshAnalytics();
  if (tab === 'phone') {
    refreshLiveImage(true);
    refreshPhoneData();
  }
}

function openModal(src) {
  if (!src) return;
  document.getElementById('modalImg').src = src;
  document.getElementById('imgModal').style.display = 'flex';
}

function openHelpPoster() {
  openModal('/assets/yuki_help.png');
}

function copyText(id) {
  const el = document.getElementById(id);
  if (el) {
    navigator.clipboard.writeText(el.textContent || '');
    showToast('✨ 已复制文本');
  }
}

function copyField(field) {
  if (!current) return;
  navigator.clipboard.writeText(String(current[field] || ''));
  showToast('✨ 已复制内容');
}

function formatWithMemeBadges(text) {
  if (!text) return '<span class="muted">（无内容）</span>';
  const safe = esc(text);
  return safe.replace(/\[MEME:([^\]]+)\]/g, '<span class="meme-tag">🎀 表情包: $1</span>');
}

// ==================== 顶部状态条与头像渲染 ====================
let avatarLoadedQQ = '';
function renderTopBrainRibbon(status, yukiState) {
  const ys = yukiState || status?.yuki_state || {};
  const bio = ys.bioclock || {};
  const groups = ys.groups || [];

  if (ys.self_qq && ys.self_qq !== avatarLoadedQQ) {
    avatarLoadedQQ = ys.self_qq;
    const box = document.getElementById('yukiAvatarBox');
    const img = new Image();
    img.onload = () => { box.innerHTML = ''; box.appendChild(img); };
    img.src = `https://q1.qlogo.cn/g?b=qq&nk=${encodeURIComponent(ys.self_qq)}&s=640`;
  }

  document.getElementById('status').innerHTML = `
    <span class="status-pill"><i class="dot"></i>Online</span>
    <span class="status-pill">🕒 ${esc(status?.generated_at || '')}</span>
    <span class="status-pill">📸 快照 <b>${status?.snapshot_count || 0}</b></span>
    ${ys.llm_model ? `<span class="status-pill">🤖 模型 <b>${esc(ys.llm_model)}</b></span>` : ''}
    ${(ys.phone_focused_chats || []).length ? `<span class="status-pill"><i class="dot pink"></i>📱 手机聚焦中: <b>${esc(ys.phone_focused_chats.join(','))}</b></span>` : ''}
  `;

  document.getElementById('ribbonBioclock').innerHTML = `
    <span class="status-pill" onclick="switchTab('analytics')" style="cursor:pointer">
      <i class="dot pink"></i>
      <span>${esc(bio.phase_label || '🌸 日常态')}</span>
      <b>${bio.current_weight ?? 1.0}x</b>
    </span>
    ${Object.keys(ys.maid_tasks || {}).length ? `<span class="status-pill"><i class="dot warn"></i>🧹 小女仆执勤中 (${Object.keys(ys.maid_tasks).length})</span>` : ''}
  `;

  document.getElementById('ribbonGroups').innerHTML = groups.slice(0, 6).map(g => `
    <div class="group-mini" onclick="filterByChatId('${esc(g.chat_id)}')" title="点击筛选群 ${esc(g.chat_id)} | 精力 ${g.energy}/${g.max_energy} | 活跃度 ${g.activity} | 说话欲望 ${g.desire}%">
      <b>${g.sleeping ? '💤' : '⚡'} ${esc(g.chat_id)}</b>
      <div class="mini-bar"><div class="mini-bar-fill" style="width:${g.energy_pct}%"></div></div>
      <span style="color:var(--berry);font-weight:700">${g.energy}</span>
      <span class="muted">🔥${g.activity}</span>
      <span class="muted">💗${g.desire}%</span>
    </div>
  `).join('');
}

function filterByChatId(cid) {
  switchTab('context');
  const input = document.getElementById('sessSearch');
  input.value = cid;
  renderSessions();
}

// ==================== TAB 1: CONTEXT STUDIO 逻辑 ====================
async function refreshAll() {
  try {
    const [status, list] = await Promise.all([
      api('/api/status'),
      api('/api/snapshots?limit=100')
    ]);
    snapshotList = Array.isArray(list) ? list : [];
    document.getElementById('navSnapCount').textContent = status.snapshot_count || snapshotList.length;
    renderTopBrainRibbon(status, status.yuki_state);
    renderSessions();

    if (!selectedId && status.latest_snapshot_id) {
      selectedId = status.latest_snapshot_id;
    }

    if (selectedId) {
      const freshData = await api('/api/snapshots/' + encodeURIComponent(selectedId));
      if (freshData && freshData.snapshot_id) {
        if (!current || current.snapshot_id !== freshData.snapshot_id || current.updated_at !== freshData.updated_at) {
          current = freshData;
          renderSnapshot();
        }
      }
    }
  } catch (e) {
    console.error(e);
  }
}

function setSessFilter(f, btn) {
  sessFilter = f;
  btn.parentElement.querySelectorAll('.chip').forEach(c => c.classList.toggle('active', c === btn));
  renderSessions();
}

function decisionBadge(x) {
  if (x.errors && x.errors.length) return '<span class="badge err">⚠️ 异常</span>';
  if (x.skip_reply) return '<span class="badge skip">⏭️ Skip安静</span>';
  if (x.should_reply === false) return '<span class="badge dived">🫧 潜水</span>';
  if (x.should_reply === true) return '<span class="badge replied">💬 已回复</span>';
  return '<span class="badge cyan">⚡ 处理中</span>';
}

function renderSessions() {
  const q = (document.getElementById('sessSearch')?.value || '').trim().toLowerCase();
  const filtered = snapshotList.filter(x => {
    if (sessFilter === 'replied' && (x.should_reply !== true || x.skip_reply)) return false;
    if (sessFilter === 'dived' && (x.should_reply !== false && !x.skip_reply)) return false;
    if (sessFilter === 'tools' && !(x.tools_used && x.tools_used.length)) return false;
    if (sessFilter === 'group' && x.mode !== 'group') return false;
    if (sessFilter === 'private' && x.mode === 'group') return false;
    if (q) {
      const hay = `${x.chat_id || ''} ${x.combined_text_preview || ''} ${x.answer_text_preview || ''} ${(x.senders || []).join(' ')}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  document.getElementById('filteredSnapCount').textContent = `${filtered.length} 条`;
  const el = document.getElementById('sessions');
  if (!filtered.length) {
    el.innerHTML = '<div class="empty">🌸 没有匹配的会话快照</div>';
    return;
  }

  el.innerHTML = filtered.map(x => {
    const modeIcon = x.mode === 'group' ? '👥' : '💌';
    const timeShort = String(x.updated_at || x.created_at || '').split(' ').pop();
    const latStr = x.latency_total != null ? `${Number(x.latency_total).toFixed(2)}s` : '-';
    const toolsTag = (x.tools_used && x.tools_used.length) ? `<span>🔧 ${x.tools_used.length}</span>` : '';
    return `
      <div class="sess-card ${x.snapshot_id === selectedId ? 'active' : ''}" onclick="selectSnapshot('${esc(x.snapshot_id)}')">
        <div class="sess-head">
          <span class="sess-chat">${modeIcon} ${esc(x.chat_id || '-')}</span>
          ${decisionBadge(x)}
        </div>
        <div class="sess-in">${esc(x.combined_text_preview || '（空消息）')}</div>
        ${x.answer_text_preview ? `<div class="sess-out">🎀 ${esc(x.answer_text_preview)}</div>` : ''}
        <div class="sess-meta">
          <span>⏱️ ${latStr}</span>
          <span>🪙 ${x.estimated_tokens || 0}</span>
          ${x.rag_count ? `<span>📚 RAG ${x.rag_count}</span>` : ''}
          ${toolsTag}
          <span style="margin-left:auto">${esc(timeShort)}</span>
        </div>
      </div>
    `;
  }).join('');
}

async function selectSnapshot(id) {
  selectedId = id;
  current = null;
  renderSessions();
  await refreshAll();
}

function renderSnapshot() {
  if (!current) return;
  document.getElementById('snapshotJson').textContent = JSON.stringify(current, null, 2);

  // 1) 顶部速览卡
  const modeLabel = current.mode === 'group' ? '👥 群聊' : (current.mode === 'master_private' ? '👑 主人私聊' : '💌 私聊');
  const senders = (current.senders || []).length ? ` · 来自: ${current.senders.join(', ')}` : '';
  document.getElementById('turnHeroTitle').innerHTML = `
    🎀 会话 <b>${esc(current.chat_id || '-')}</b> (${modeLabel})
    <span class="muted" style="font-weight:500;font-size:12px">${esc(current.updated_at || '')}${esc(senders)}</span>
  `;
  document.getElementById('turnSenderLabel').innerHTML = `
    📥 收到消息 ${current.native_image_count ? `<span class="badge cyan">🖼️ 附图 ${current.native_image_count}</span>` : ''}
  `;
  document.getElementById('turnIncomingBox').innerHTML = current.combined_text
    ? esc(current.combined_text)
    : '<span class="muted">（本轮无输入文本）</span>';

  const latTotal = current.latency?.total != null ? `${Number(current.latency.total).toFixed(2)}s` : '-';
  document.getElementById('turnDecisionBridge').innerHTML = `
    ${decisionBadge(current)}
    <span class="badge pink">⏱️ 总耗时 ${latTotal}</span>
    ${current.energy != null ? `<span class="muted" style="font-size:11px">⚡精力 ${current.energy} · 🔥${current.activity ?? 0}</span>` : ''}
    ${current.rag_interest != null ? `<span class="muted" style="font-size:11px">🧠语义分 ${(current.rag_interest * 100).toFixed(0)}%</span>` : ''}
  `;

  if (current.skip_reply) {
    document.getElementById('turnAnswerBox').innerHTML = '<span class="muted">⏭️ 模型调用了 skip 工具，本轮主动保持安静喵～</span>';
  } else if (current.should_reply === false) {
    document.getElementById('turnAnswerBox').innerHTML = '<span class="muted">🫧 群聊潜水判定未触发回复，Yuki 静静观察中～</span>';
  } else if (current.answer_text) {
    document.getElementById('turnAnswerBox').innerHTML = formatWithMemeBadges(current.answer_text);
  } else {
    document.getElementById('turnAnswerBox').innerHTML = '<span class="muted">（尚未生成或无可见文本）</span>';
  }

  // 2) 工具调用链追踪
  const trace = current.tool_trace || [];
  const traceWrap = document.getElementById('toolTraceWrap');
  if (trace.length > 1 || (trace.length === 1 && (trace[0].calls || []).length)) {
    traceWrap.style.display = 'block';
    traceWrap.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center">
        <b style="font-size:13px;color:#b45309">🔧 本轮 LLM 思考与工具调用链 (共 ${trace.length} 轮)</b>
        <span class="badge skip">调用工具: ${esc((current.tools_used || []).join(', ') || '无')}</span>
      </div>
      ${trace.map(r => `
        <div class="tool-round-item">
          <div style="display:flex;justify-content:space-between;font-weight:700;margin-bottom:3px">
            <span>Round #${r.round}</span>
            <span class="muted">LLM ${r.llm_ms || 0}ms ${r.exec_ms ? `· 工具执行 ${r.exec_ms}ms` : ''}</span>
          </div>
          ${r.thought ? `<div style="color:var(--text-sec);margin-bottom:4px">💭 ${esc(r.thought)}</div>` : ''}
          ${(r.calls || []).map(c => `<div style="font-family:monospace;color:var(--berry)">⚡ <b>${esc(c.name)}</b>(${esc(c.args)})</div>`).join('')}
        </div>
      `).join('')}
    `;
  } else {
    traceWrap.style.display = 'none';
  }

  renderTimeline();
  renderMessagesList();
  renderTokenBreakdown();
  renderMemories();
}

function setMsgRoleFilter(role, btn) {
  msgRoleFilter = role;
  btn.parentElement.querySelectorAll('.chip').forEach(c => c.classList.toggle('active', c === btn));
  renderMessagesList();
}

function toggleAllMessages(openState) {
  document.querySelectorAll('#messages details.msg-card').forEach(d => { d.open = openState; });
}

function renderMessagesList() {
  const messages = (current && current.built_messages) || [];
  const q = (document.getElementById('msgSearchInput')?.value || '').trim().toLowerCase();
  const container = document.getElementById('messages');

  if (!messages.length) {
    container.className = 'messages-stream empty';
    container.innerHTML = '🌸 暂无完整 messages（如群聊潜水轮次在进入 LLM 前已结束）';
    return;
  }

  const total = messages.length;
  const filtered = messages.map((m, idx) => ({ m, idx })).filter(({ m }) => {
    const role = m.role || 'unknown';
    if (msgRoleFilter !== 'all' && role !== msgRoleFilter) return false;
    if (q) {
      const c = typeof m.content === 'string' ? m.content : JSON.stringify(m.content);
      if (!c.toLowerCase().includes(q) && !(m.name || '').toLowerCase().includes(q)) return false;
    }
    return true;
  });

  container.className = filtered.length ? 'messages-stream' : 'messages-stream empty';
  if (!filtered.length) {
    container.innerHTML = '没有匹配的上下文消息';
    return;
  }

  container.innerHTML = filtered.map(({ m, idx }) => {
    const role = String(m.role || 'unknown');
    const c = typeof m.content === 'string' ? m.content : JSON.stringify(m.content, null, 2);
    const tok = Math.max(1, Math.floor(c.length / 2));
    // 默认折叠超长 system prompt，展开最后 6 条对话消息
    const shouldOpen = q ? true : (role !== 'system' && idx >= Math.max(0, total - 6));
    const snippet = c.replace(/\s+/g, ' ').slice(0, 95);
    const toolLabel = m.name ? `<span class="badge skip">${esc(m.name)}</span>` : '';
    return `
      <details class="msg-card role-${esc(role)}" ${shouldOpen ? 'open' : ''}>
        <summary>
          <div class="msg-sum-left">
            <span class="role-pill ${esc(role)}">${esc(role)}</span>
            ${toolLabel}
            <span class="muted">#${idx + 1} · ${c.length} 字 · ≈${tok} tok</span>
            <span class="msg-snippet">${esc(snippet)}</span>
          </div>
          <button class="btn btn-sm" onclick="event.stopPropagation();navigator.clipboard.writeText(${JSON.stringify(c).replace(/"/g, '&quot;')});showToast('✨ 已复制该条消息')">复制</button>
        </summary>
        <div class="msg-content">${esc(c)}</div>
      </details>
    `;
  }).join('');
}

function renderTokenBreakdown() {
  const te = (current && current.token_estimate) || {};
  const total = te.estimated_tokens || 0;
  const byRole = te.by_role || {};
  document.getElementById('totalTokenBadge').textContent = `${total.toLocaleString()} tok`;

  const roles = [
    { key: 'system', label: '🌸 System', color: '#9b5de5' },
    { key: 'user', label: '💧 User', color: '#00b4d8' },
    { key: 'assistant', label: '🍓 Yuki', color: '#ff4785' },
    { key: 'tool', label: '🍯 Tool', color: '#f59e0b' }
  ];

  const rowsHtml = roles.map(r => {
    const val = byRole[r.key] || 0;
    const pct = total > 0 ? Math.round((val / total) * 100) : 0;
    return `
      <div class="token-role-row">
        <span style="font-weight:700;color:var(--text-sec)">${r.label}</span>
        <div class="progress-track">
          <div class="progress-fill" style="width:${pct}%;background:${r.color}"></div>
        </div>
        <span style="text-align:right;font-weight:700">${val} <span class="muted">(${pct}%)</span></span>
      </div>
    `;
  }).join('');

  document.getElementById('tokenBreakdownBox').innerHTML = rowsHtml;
}

function renderMemories() {
  const diaries = (current && current.relevant_diaries) || [];
  document.getElementById('ragCountBadge').textContent = `${diaries.length} 条`;
  const box = document.getElementById('memories');
  if (!diaries.length) {
    box.innerHTML = '<div class="empty" style="padding:18px">本轮无召回日记</div>';
    return;
  }
  box.innerHTML = diaries.map((d, i) => {
    if (typeof d === 'string') {
      return `<div class="diary-card">${esc(d)}</div>`;
    }
    const score = d.relevance ?? d.score;
    const scoreBadge = score != null ? `<span class="badge pink">相关度 ${(Number(score) * 100).toFixed(1)}%</span>` : '';
    const ts = (d.metadata && d.metadata.timestamp) || d.timestamp || '';
    const content = d.content || d.document || JSON.stringify(d, null, 2);
    return `
      <div class="diary-card">
        <div class="diary-head">
          <span><b>#${i + 1}</b> ${esc(ts)}</span>
          ${scoreBadge}
        </div>
        <div>${esc(content)}</div>
      </div>
    `;
  }).join('');
}

function renderTimeline() {
  const latency = (current && current.latency) || {};
  const curStage = (current && current.stage) || '';
  const errors = (current && current.errors) || [];
  const errStages = new Set(errors.map(e => e.stage));

  document.getElementById('timeline').innerHTML = stages.map(s => {
    const val = latency[s];
    const hasDone = val != null;
    const isErr = errStages.has(s);
    const isActive = curStage === s && !hasDone;
    const cls = isErr ? 'error' : (hasDone ? 'done' : (isActive ? 'active' : ''));
    const timeText = val != null ? (val >= 1 ? `${Number(val).toFixed(2)}s` : `${Math.round(val * 1000)}ms`) : (isActive ? '运行中...' : '—');
    return `
      <div class="stage-node ${cls}" title="${esc(s)}">
        <div class="st-name">${esc(stageShortLabels[s] || s)}</div>
        <div class="st-time">${timeText}</div>
      </div>
    `;
  }).join('');
}

// ==================== TAB 2: ANALYTICS & BRAIN 图表渲染 ====================
async function refreshAnalytics() {
  try {
    analyticsData = await api('/api/analytics');
    if (!analyticsData || !analyticsData.ok) return;
    const dec = analyticsData.decisions || {};
    document.getElementById('navReplyRate').textContent = `${dec.reply_rate ?? 0}%`;

    renderAnalyticsKpis(analyticsData);
    renderBioclockChart(analyticsData.yuki_state?.bioclock);
    renderGroupGauges(analyticsData.yuki_state?.groups || []);
    renderStageWaterfall(analyticsData.latency);
    renderTokenTrendChart(analyticsData.tokens?.recent_series || []);
    renderDecisionAndTools(analyticsData);
  } catch (e) {
    console.error(e);
  }
}

function renderAnalyticsKpis(data) {
  const dec = data.decisions || {};
  const lat = data.latency || {};
  const tok = data.tokens || {};
  const rag = data.rag || {};
  const tools = data.tools || {};
  const phone = data.phone || {};

  document.getElementById('analyticsKpiGrid').innerHTML = `
    <div class="glass kpi-card">
      <div class="kpi-label"><span>💬 累计会话 &amp; 回复率</span><span class="badge pink">${dec.total || 0} 轮</span></div>
      <div class="kpi-val">${dec.reply_rate ?? 0}%</div>
      <div class="kpi-sub">已回 ${dec.replied || 0} · 潜水 ${dec.dived || 0} · Skip ${dec.skipped || 0}</div>
    </div>
    <div class="glass kpi-card">
      <div class="kpi-label"><span>⚡ 平均响应耗时</span><span class="badge cyan">P95 ${fmtMs(lat.p95_total_ms)}</span></div>
      <div class="kpi-val">${fmtMs(lat.avg_total_ms)}</div>
      <div class="kpi-sub">端到端管线平均总耗时</div>
    </div>
    <div class="glass kpi-card">
      <div class="kpi-label"><span>🪙 平均单轮 Token</span><span class="badge skip">Max ${tok.max_tokens || 0}</span></div>
      <div class="kpi-val">${(tok.avg_tokens || 0).toLocaleString()}</div>
      <div class="kpi-sub">累计估算 ${(tok.total_tokens || 0).toLocaleString()} tok</div>
    </div>
    <div class="glass kpi-card">
      <div class="kpi-label"><span>📚 RAG 记忆命中率</span><span class="badge replied">平均 ${rag.avg_recall_count || 0} 条</span></div>
      <div class="kpi-val">${rag.hit_rate ?? 0}%</div>
      <div class="kpi-sub">平均语义兴趣度 ${((rag.avg_interest || 0) * 100).toFixed(1)}%</div>
    </div>
    <div class="glass kpi-card">
      <div class="kpi-label"><span>🔧 工具链调用统计</span><span class="badge dived">${tools.total_llm_rounds || 0} LLM轮</span></div>
      <div class="kpi-val">${tools.total_tool_calls || 0}</div>
      <div class="kpi-sub">共 ${tools.turns_with_tools || 0} 轮触发工具调用</div>
    </div>
    <div class="glass kpi-card">
      <div class="kpi-label"><span>📱 手机自动化轨迹</span><span class="badge replied">成功率 ${phone.success_rate ?? 100}%</span></div>
      <div class="kpi-val">${phone.total_steps || 0} 步</div>
      <div class="kpi-sub">${phone.session_count || 0} 个会话 · 均步 ${fmtMs(phone.avg_step_ms)}</div>
    </div>
  `;
}

function renderBioclockChart(bio) {
  if (!bio || !bio.curve || !bio.curve.length) return;
  document.getElementById('bioclockPhaseBadge').textContent = `${bio.phase_label || ''} · 当前 ${bio.current_weight}x (${bio.now_hour}h)`;

  const W = 680, H = 220, padL = 38, padR = 18, padT = 18, padB = 28;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  const minW = 0.15, maxW = 1.55;

  const xOf = h => padL + (h / 24.0) * plotW;
  const yOf = w => padT + plotH - ((w - minW) / (maxW - minW)) * plotH;

  const pts = bio.curve.map(p => `${xOf(p.hour).toFixed(1)},${yOf(p.weight).toFixed(1)}`).join(' ');
  const areaPts = `${xOf(0).toFixed(1)},${(padT + plotH).toFixed(1)} ${pts} ${xOf(24).toFixed(1)},${(padT + plotH).toFixed(1)}`;
  const curX = xOf(bio.now_hour || 0);
  const curY = yOf(bio.current_weight || 1.0);

  const hours = [0, 4, 8, 12, 16, 20, 24];
  document.getElementById('bioclockChartBox').innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" width="100%" height="220">
      <defs>
        <linearGradient id="bioGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#ff4785" stop-opacity="0.45"/>
          <stop offset="65%" stop-color="#ff85b3" stop-opacity="0.16"/>
          <stop offset="100%" stop-color="#ffffff" stop-opacity="0.0"/>
        </linearGradient>
      </defs>
      ${[0.3, 0.6, 0.9, 1.2, 1.5].map(v => `
        <line x1="${padL}" y1="${yOf(v)}" x2="${W - padR}" y2="${yOf(v)}" stroke="rgba(255,110,168,0.18)" stroke-dasharray="3,3"/>
        <text x="${padL - 6}" y="${yOf(v) + 4}" text-anchor="end" font-size="10" fill="#a47690">${v}x</text>
      `).join('')}
      ${hours.map(h => `
        <text x="${xOf(h)}" y="${H - 6}" text-anchor="middle" font-size="10.5" fill="#6e445c">${String(h).padStart(2, '0')}:00</text>
      `).join('')}
      <polygon points="${areaPts}" fill="url(#bioGrad)"/>
      <polyline points="${pts}" fill="none" stroke="#ff4785" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
      <line x1="${curX}" y1="${padT}" x2="${curX}" y2="${padT + plotH}" stroke="#9b5de5" stroke-width="1.5" stroke-dasharray="4,3"/>
      <circle cx="${curX}" cy="${curY}" r="6" fill="#ff4785" stroke="#fff" stroke-width="2.5"/>
      <text x="${Math.min(W - 65, Math.max(45, curX))}" y="${Math.max(24, curY - 10)}" text-anchor="middle" font-size="11" font-weight="800" fill="#d61f69">当前 ${bio.current_weight}x</text>
    </svg>
  `;
}

function renderGroupGauges(groups) {
  const el = document.getElementById('groupGaugeGrid');
  if (!groups.length) {
    el.innerHTML = '<div class="empty">暂无群组实时状态</div>';
    return;
  }
  el.innerHTML = groups.map(g => `
    <div class="group-gauge-card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <b style="font-size:13.5px">👥 ${esc(g.chat_id)}</b>
        <span class="badge ${g.sleeping ? 'dived' : 'replied'}">${g.sleeping ? '💤 午睡休眠' : '⚡ 元气在线'}</span>
      </div>
      <div style="font-size:11.5px;margin-bottom:6px">
        <div style="display:flex;justify-content:space-between"><span>🔋 精力值 (Energy)</span><b>${g.energy} / ${g.max_energy}</b></div>
        <div class="progress-track" style="margin-top:3px"><div class="progress-fill" style="width:${g.energy_pct}%;background:var(--grad-primary)"></div></div>
      </div>
      <div style="font-size:11.5px;margin-bottom:6px">
        <div style="display:flex;justify-content:space-between"><span>🔥 群聊活跃度 (Activity)</span><b>${g.activity} / 10</b></div>
        <div class="progress-track" style="margin-top:3px"><div class="progress-fill" style="width:${g.activity_pct}%;background:#f59e0b"></div></div>
      </div>
      <div style="font-size:11.5px">
        <div style="display:flex;justify-content:space-between"><span>💗 说话/破冰欲望 (Desire)</span><b>${g.desire}%</b></div>
        <div class="progress-track" style="margin-top:3px"><div class="progress-fill" style="width:${g.desire}%;background:#9b5de5"></div></div>
      </div>
    </div>
  `).join('');
}

function renderStageWaterfall(lat) {
  const stList = (lat && lat.stages) || [];
  document.getElementById('stageTotalAvgLabel').textContent = `平均总耗时 ${fmtMs(lat?.avg_total_ms)}`;
  const maxAvg = Math.max(1, ...stList.map(s => s.avg_ms || 0));
  document.getElementById('stageWaterfallBox').innerHTML = stList.map(s => {
    const w = Math.max(3, Math.round(((s.avg_ms || 0) / maxAvg) * 100));
    return `
      <div class="waterfall-row">
        <span style="font-weight:700;color:var(--text-sec);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(s.label)}</span>
        <div class="progress-track" style="height:10px">
          <div class="progress-fill" style="width:${w}%;background:var(--grad-primary)"></div>
        </div>
        <span style="text-align:right;font-weight:700;color:var(--berry)">${fmtMs(s.avg_ms)}</span>
      </div>
    `;
  }).join('');
}

function renderTokenTrendChart(series) {
  const box = document.getElementById('tokenTrendChartBox');
  if (!series.length) {
    box.innerHTML = '<div class="empty">暂无足够快照生成趋势图</div>';
    return;
  }
  const W = 540, H = 220, padL = 42, padR = 12, padT = 16, padB = 28;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  const maxTok = Math.max(100, ...series.map(s => s.total_tokens || 0));
  const barW = Math.max(8, Math.min(22, (plotW / series.length) - 4));

  const bars = series.map((s, i) => {
    const x = padL + (i + 0.5) * (plotW / series.length) - barW / 2;
    const sysH = ((s.system || 0) / maxTok) * plotH;
    const usrH = ((s.user || 0) / maxTok) * plotH;
    const astH = ((s.assistant || 0) / maxTok) * plotH;
    const tolH = ((s.tool || 0) / maxTok) * plotH;
    let curY = padT + plotH;
    const segs = [
      { h: sysH, c: '#9b5de5' },
      { h: usrH, c: '#00b4d8' },
      { h: astH, c: '#ff4785' },
      { h: tolH, c: '#f59e0b' }
    ].map(seg => {
      curY -= seg.h;
      return `<rect x="${x.toFixed(1)}" y="${curY.toFixed(1)}" width="${barW.toFixed(1)}" height="${Math.max(0, seg.h).toFixed(1)}" fill="${seg.c}" rx="2"/>`;
    }).join('');
    return `
      <g style="cursor:pointer" onclick="switchTab('context');selectSnapshot('${esc(s.snapshot_id)}')">
        <title>会话 ${esc(s.chat_id)} (${esc(s.time)}) | 总 Token: ${s.total_tokens} | 耗时: ${s.latency_ms}ms</title>
        ${segs}
      </g>
    `;
  }).join('');

  box.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" width="100%" height="220">
      <line x1="${padL}" y1="${padT + plotH}" x2="${W - padR}" y2="${padT + plotH}" stroke="rgba(255,110,168,0.3)"/>
      <text x="${padL - 5}" y="${padT + 8}" text-anchor="end" font-size="10" fill="#a47690">${maxTok}</text>
      <text x="${padL - 5}" y="${padT + plotH}" text-anchor="end" font-size="10" fill="#a47690">0</text>
      ${bars}
    </svg>
    <div style="display:flex;justify-content:center;gap:14px;font-size:11.5px;color:var(--text-sec)">
      <span><b style="color:#9b5de5">■</b> System</span>
      <span><b style="color:#00b4d8">■</b> User</span>
      <span><b style="color:#ff4785">■</b> Yuki</span>
      <span><b style="color:#f59e0b">■</b> Tool</span>
    </div>
  `;
}

function renderDecisionAndTools(data) {
  const tools = data.tools || {};
  const ranking = tools.ranking || [];
  const chats = data.chats || [];
  document.getElementById('toolTotalCallsLabel').textContent = `${tools.total_tool_calls || 0} 次工具调用`;

  const toolHtml = ranking.length
    ? ranking.slice(0, 5).map(t => `
        <div style="display:flex;justify-content:space-between;align-items:center;padding:5px 8px;border-radius:9px;background:rgba(255,255,255,0.8);border:1px solid var(--line);font-size:12px;margin-bottom:5px">
          <b>🔧 ${esc(t.name)}</b>
          <span class="badge pink">${t.count} 次</span>
        </div>
      `).join('')
    : '<div class="muted" style="font-size:12px;margin-bottom:8px">暂无工具调用记录</div>';

  const chatHtml = chats.length
    ? chats.slice(0, 4).map(c => `
        <div style="display:flex;justify-content:space-between;align-items:center;padding:5px 8px;border-radius:9px;background:rgba(255,255,255,0.8);border:1px solid var(--line);font-size:12px;margin-bottom:5px;cursor:pointer" onclick="filterByChatId('${esc(c.chat_id)}')">
          <span><b>${c.mode === 'group' ? '👥' : '💌'} ${esc(c.chat_id)}</b> (${c.turns}轮)</span>
          <span class="muted">回复率 ${c.reply_rate}% · ${fmtMs(c.avg_latency_ms)}</span>
        </div>
      `).join('')
    : '';

  document.getElementById('decisionAndToolsBox').innerHTML = `
    <div style="margin-bottom:10px">
      <div style="font-size:12px;font-weight:700;color:var(--text-sec);margin-bottom:6px">🛠️ 热门工具排行榜</div>
      ${toolHtml}
    </div>
    <div>
      <div style="font-size:12px;font-weight:700;color:var(--text-sec);margin-bottom:6px">🔥 活跃会话 Top</div>
      ${chatHtml}
    </div>
  `;
}

// ==================== TAB 3: PHONE MONITOR 逻辑 ====================
function toggleFollow() {
  followLatest = !followLatest;
  const btn = document.getElementById('followBtn');
  btn.className = followLatest ? 'btn soft-active' : 'btn';
  btn.textContent = followLatest ? '🎯 自动跟随最新步' : '📌 已锁定当前步';
  if (followLatest) refreshPhoneData();
}

function toggleLive() {
  liveEnabled = !liveEnabled;
  const btn = document.getElementById('liveBtn');
  btn.className = liveEnabled ? 'btn soft-active' : 'btn';
  btn.textContent = liveEnabled ? '🟢 实时画面流: 开启' : '⏸️ 实时画面流: 暂停';
}

function toggleStepImgMode() {
  showAnnotated = !showAnnotated;
  document.getElementById('viewModeBtn').textContent = showAnnotated ? '切换: 红框标注图' : '切换: 无框原图';
  renderSelectedStep();
}

function refreshLiveImage(force = false) {
  if (activeTab !== 'phone' && !force) return;
  if (liveBusy && !force) return;
  liveBusy = true;
  const img = document.getElementById('liveImg');
  const t0 = performance.now();
  const url = '/api/phone/live.jpg?t=' + Date.now() + (force ? '&force=1' : '');
  const loader = new Image();
  loader.onload = () => {
    img.src = url;
    const cost = Math.round(performance.now() - t0);
    document.getElementById('liveMeta').textContent = '实时帧 ' + cost + 'ms';
    liveBusy = false;
  };
  loader.onerror = () => {
    document.getElementById('liveMeta').textContent = '设备未就绪或抓屏失败';
    liveBusy = false;
  };
  loader.src = url;
}

async function refreshPhoneData() {
  try {
    const [status, sessions] = await Promise.all([
      api('/api/phone/status'),
      api('/api/phone/sessions?limit=60')
    ]);
    document.getElementById('navPhoneCount').textContent = status.session_count || sessions.length || 0;
    const activeChats = Object.keys(status.active_chats || {});
    document.getElementById('statusPills').innerHTML = `
      <span class="status-pill"><i class="dot ${status.live_error ? 'warn' : ''}"></i>${status.live_error ? 'ADB: ' + esc(status.live_error) : 'ADB 实时在线'}</span>
      <span class="status-pill">聚焦中会话: <b>${activeChats.length ? esc(activeChats.join(',')) : '无'}</b></span>
      <span class="status-pill">历史轨迹数: <b>${status.session_count || 0}</b></span>
      <span class="status-pill">刷新: ${esc(status.generated_at || '')}</span>
    `;
    document.getElementById('sessCount').textContent = `${sessions.length} 条`;

    if ((followLatest && status.latest_session_id) || (!selectedSessionId && sessions.length)) {
      selectedSessionId = (followLatest && status.latest_session_id) ? status.latest_session_id : sessions[0].session_id;
    }

    renderSessionList(sessions);

    if (selectedSessionId) {
      const detail = await api('/api/phone/sessions/' + encodeURIComponent(selectedSessionId));
      if (detail && detail.session_id) {
        currentSession = detail;
        const steps = currentSession.steps || [];
        if (followLatest || !selectedStepIndex || selectedStepIndex > steps.length) {
          selectedStepIndex = steps.length ? steps[steps.length - 1].step_index : null;
        }
        renderStepList();
        renderSelectedStep();
      }
    }
  } catch (e) {
    console.error(e);
  }
}

function renderSessionList(sessions) {
  const el = document.getElementById('sessionList');
  if (!sessions.length) {
    el.innerHTML = '<div class="empty">暂无手机操作轨迹</div>';
    return;
  }
  el.innerHTML = sessions.map(s => `
    <div class="item ${s.session_id === selectedSessionId ? 'active' : ''}" onclick="selectSession('${esc(s.session_id)}')">
      <div class="item-head">
        <b>${esc(s.goal || '手机操作')}</b>
        <span class="badge ${s.status === 'running' ? 'running' : 'finished'}">${esc(s.status)}</span>
      </div>
      <div class="sub">chat: ${esc(s.chat_id)} · ${s.step_count || 0} 步 · 总耗时 ${fmtMs(s.total_elapsed_ms)}</div>
      <div class="sub">${esc(s.updated_at || s.created_at || '')}</div>
    </div>
  `).join('');
}

async function selectSession(sid) {
  selectedSessionId = sid;
  selectedStepIndex = null;
  followLatest = false;
  document.getElementById('followBtn').className = 'btn';
  document.getElementById('followBtn').textContent = '📌 已锁定当前步';
  await refreshPhoneData();
}

function selectStep(idx) {
  selectedStepIndex = idx;
  followLatest = false;
  document.getElementById('followBtn').className = 'btn';
  document.getElementById('followBtn').textContent = '📌 已锁定当前步';
  renderStepList();
  renderSelectedStep();
}

function stepDelta(delta) {
  if (!currentSession || !(currentSession.steps || []).length) return;
  const total = currentSession.steps.length;
  const cur = selectedStepIndex || total;
  const next = Math.max(1, Math.min(total, cur + delta));
  selectStep(next);
}

function renderStepList() {
  const el = document.getElementById('stepList');
  const steps = (currentSession && currentSession.steps) || [];
  if (!steps.length) {
    el.innerHTML = '<div class="empty">该会话暂无步骤记录</div>';
    return;
  }
  el.innerHTML = steps.map(st => `
    <div class="item ${st.step_index === selectedStepIndex ? 'active' : ''}" onclick="selectStep(${st.step_index})">
      <div class="item-head">
        <b>#${st.step_index} ${esc(st.step_display || st.action)}</b>
        <span class="badge ${st.success ? 'time' : 'err'}">${fmtMs(st.elapsed_ms)}</span>
      </div>
      <div class="sub">${esc(st.note || '')}</div>
      <div class="sub">${esc(st.package || '未知包名')} · 节点 ${st.node_count || 0} · ${esc(st.timestamp || '')}</div>
    </div>
  `).join('');
}

function renderSelectedStep() {
  if (!currentSession) return;
  const steps = currentSession.steps || [];
  const step = steps.find(s => s.step_index === selectedStepIndex) || steps[steps.length - 1];

  const incomingList = (currentSession.incoming_messages || []).map(m => `[${m.time}] ${m.text}`).join('\n---\n');
  const stepIncoming = step ? (step.user_incoming_text || '') : '';
  document.getElementById('userIncomingText').textContent =
    incomingList || stepIncoming || currentSession.last_incoming_text || '暂无';

  if (!step) {
    document.getElementById('yukiReplyText').textContent = currentSession.last_final_reply || '暂无';
    rawTreeCache = '暂无步骤';
    renderTreeText();
    return;
  }

  document.getElementById('stepScreenTitle').textContent =
    `👁️ 第 #${step.step_index} 步 Yuki 视角 (${step.action})`;
  document.getElementById('stepElapsedBadge').textContent = fmtMs(step.elapsed_ms);

  const imgUrl = showAnnotated ? (step.yuki_image_url || step.raw_image_url) : (step.raw_image_url || step.yuki_image_url);
  const yukiImg = document.getElementById('yukiImg');
  if (imgUrl) {
    yukiImg.src = imgUrl;
  } else {
    yukiImg.removeAttribute('src');
  }

  const tb = step.timing_breakdown || {};
  const parts = [
    { key: 'dump_before_ms', label: '动作前Dump', color: '#9b5de5' },
    { key: 'exec_ms', label: 'ADB执行', color: '#ff4785' },
    { key: 'wait_ms', label: '等待稳定', color: '#f59e0b' },
    { key: 'dump_after_ms', label: '动作后Dump', color: '#00b4d8' },
    { key: 'screenshot_ms', label: '截图+标注', color: '#10b981' }
  ];
  const chips = [`<span class="timing-chip"><b>总用时</b>: ${fmtMs(step.elapsed_ms)}</span>`];
  const totalParts = parts.reduce((acc, p) => acc + (Number(tb[p.key]) || 0), 0) || 1;
  const segHtml = parts.map(p => {
    const v = tb[p.key];
    if (v == null) return '';
    chips.push(`<span class="timing-chip"><b style="color:${p.color}">●</b> ${p.label}: ${v}ms</span>`);
    const pct = Math.max(2, Math.round((Number(v) / totalParts) * 100));
    return `<div style="width:${pct}%;background:${p.color}" title="${p.label}: ${v}ms"></div>`;
  }).join('');

  document.getElementById('stepTimingSegBar').innerHTML = segHtml;
  document.getElementById('stepTimingBar').innerHTML = chips.join('');

  const replyParts = [];
  if (step.yuki_replied_text) {
    replyParts.push(`【第 #${step.step_index} 步模型思考 & 调用原文】\n${step.yuki_replied_text}`);
  }
  if (step.yuki_final_reply || currentSession.last_final_reply) {
    replyParts.push(`【本轮最终回复原文】\n${step.yuki_final_reply || currentSession.last_final_reply}`);
  }
  if (currentSession.summary) {
    replyParts.push(`【聚焦退出总结】\n${currentSession.summary}`);
  }
  document.getElementById('yukiReplyText').textContent = replyParts.join('\n\n====================\n\n') || '（本步无附加文本）';

  rawTreeCache = step.yuki_received_text || '暂无';
  renderTreeText();
}

function renderTreeText() {
  const q = (document.getElementById('treeSearchInput')?.value || '').trim().toLowerCase();
  const el = document.getElementById('toolResultText');
  if (!q) {
    el.textContent = rawTreeCache;
    return;
  }
  const lines = String(rawTreeCache).split('\n');
  const matched = lines.filter(l => l.toLowerCase().includes(q));
  el.textContent = matched.length ? matched.join('\n') : `（未找到包含 "${q}" 的控件节点）`;
}

// ==================== 全局控制与樱花粒子动效 ====================
function togglePause() {
  paused = !paused;
  const btn = document.getElementById('pauseBtn');
  btn.className = paused ? 'btn' : 'btn soft-active';
  btn.textContent = paused ? '⏸️ 自动同步: 已暂停' : '⚡ 自动同步: 开启';
}

function copySnapshot() {
  if (current) {
    navigator.clipboard.writeText(JSON.stringify(current, null, 2));
    showToast('✨ 已复制完整 Snapshot JSON');
  }
}

function downloadSnapshot() {
  if (!current) return;
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(current, null, 2)], { type: 'application/json' }));
  a.download = (current.snapshot_id || 'snapshot') + '.json';
  a.click();
}

async function refreshEverything(manual = false) {
  await refreshAll();
  if (activeTab === 'analytics' || manual) await refreshAnalytics();
  if (activeTab === 'phone' || manual) await refreshPhoneData();
}

document.addEventListener('keydown', e => {
  if (e.target && ['INPUT', 'TEXTAREA'].includes(e.target.tagName)) return;
  if (activeTab === 'phone') {
    if (e.key === 'ArrowLeft') stepDelta(-1);
    if (e.key === 'ArrowRight') stepDelta(1);
  }
  if (e.key === 'Escape') document.getElementById('imgModal').style.display = 'none';
});

// 轻量级樱花星点粒子动画
let petalsEnabled = true;
function togglePetals() {
  petalsEnabled = !petalsEnabled;
  document.getElementById('sakuraCanvas').style.display = petalsEnabled ? 'block' : 'none';
  document.getElementById('petalBtn').className = petalsEnabled ? 'btn soft-active' : 'btn';
}

(function initSakuraCanvas() {
  const canvas = document.getElementById('sakuraCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let w = canvas.width = window.innerWidth;
  let h = canvas.height = window.innerHeight;
  window.addEventListener('resize', () => {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
  });
  const petals = Array.from({ length: 22 }, () => ({
    x: Math.random() * w,
    y: Math.random() * h,
    r: 3 + Math.random() * 4.5,
    vx: 0.25 + Math.random() * 0.55,
    vy: 0.45 + Math.random() * 0.75,
    angle: Math.random() * Math.PI * 2,
    spin: (Math.random() - 0.5) * 0.02,
    alpha: 0.22 + Math.random() * 0.35
  }));
  function draw() {
    if (petalsEnabled) {
      ctx.clearRect(0, 0, w, h);
      for (const p of petals) {
        p.x += p.vx;
        p.y += p.vy;
        p.angle += p.spin;
        if (p.y > h + 12) { p.y = -10; p.x = Math.random() * w; }
        if (p.x > w + 12) { p.x = -10; }
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(p.angle);
        ctx.fillStyle = `rgba(255, 117, 168, ${p.alpha})`;
        ctx.beginPath();
        ctx.ellipse(0, 0, p.r, p.r * 0.62, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      }
    }
    requestAnimationFrame(draw);
  }
  requestAnimationFrame(draw);
})();

// 启动初始化
switchTab(INITIAL_TAB, false);
refreshEverything(true);
setInterval(() => {
  if (paused) return;
  refreshAll();
  if (activeTab === 'analytics') refreshAnalytics();
  if (activeTab === 'phone') refreshPhoneData();
}, 2000);
setInterval(() => {
  if (!paused && liveEnabled && activeTab === 'phone') refreshLiveImage(false);
}, 1200);
</script>
</body>
</html>"""

# 兼容直接引用 PHONE_HTML 的调用方，共享同一套统一 SPA 工作台（根据 URL 自动激活对应 Tab）
PHONE_HTML = HTML

_STEP_IMG_RE = re.compile(r"^/api/phone/sessions/([^/]+)/steps/(\d+)/(yuki|raw)\.jpg$")
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ContextDebugRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_text=HTML):
        body = html_text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, data: bytes, content_type: str = "image/jpeg", status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            if path in ("/", "/analytics", "/analytics/"):
                self._send_html(HTML)
            elif path in ("/phone", "/phone/"):
                self._send_html(PHONE_HTML)
            elif path == "/assets/yuki_help.png":
                help_path = os.path.join(_ROOT_DIR, "yuki_help.png")
                if os.path.isfile(help_path):
                    with open(help_path, "rb") as f:
                        self._send_bytes(f.read(), "image/png", 200)
                else:
                    self._send_json({"ok": False, "error": "asset_not_found"}, 404)
            elif path == "/api/health":
                self._send_json({"ok": True})
            elif path == "/api/status":
                self._send_json(context_snapshot_store.status())
            elif path == "/api/analytics":
                self._send_json(context_snapshot_store.analytics())
            elif path == "/api/yuki/state":
                self._send_json(context_snapshot_store.yuki_runtime_state())
            elif path == "/api/snapshots":
                limit = int((query.get("limit") or [50])[0])
                chat_id = (query.get("chat_id") or [None])[0]
                self._send_json(context_snapshot_store.list_recent(limit=limit, chat_id=chat_id))
            elif path == "/api/latest":
                chat_id = (query.get("chat_id") or [None])[0]
                self._send_json(context_snapshot_store.latest(chat_id) or {})
            elif path.startswith("/api/snapshots/"):
                snapshot_id = unquote(path.removepurb(path) if hasattr(path, "removepurb") else path.removeprefix("/api/snapshots/"))
                item = context_snapshot_store.get(snapshot_id)
                self._send_json(item or {"ok": False, "error": "snapshot_not_found"}, 200 if item else 404)
            # ---------- 手机监控与轨迹 API ----------
            elif path == "/api/phone/status":
                self._send_json(phone_trace_store.status())
            elif path == "/api/phone/sessions":
                limit = int((query.get("limit") or [50])[0])
                self._send_json(phone_trace_store.list_sessions(limit=limit))
            elif path == "/api/phone/live.jpg":
                force = (query.get("force") or ["0"])[0] in ("1", "true")
                jpeg, _, _ = phone_trace_store.capture_live_jpeg(force=force)
                if jpeg:
                    self._send_bytes(jpeg, "image/jpeg", 200)
                else:
                    self._send_json({"ok": False, "error": "live_screencap_unavailable"}, 503)
            elif path.startswith("/api/phone/sessions/"):
                m = _STEP_IMG_RE.match(path)
                if m:
                    sid = unquote(m.group(1))
                    step_idx = int(m.group(2))
                    kind = m.group(3)
                    img_bytes = phone_trace_store.get_step_image(sid, step_idx, kind=kind)
                    if img_bytes:
                        self._send_bytes(img_bytes, "image/jpeg", 200)
                    else:
                        self._send_json({"ok": False, "error": "image_not_found"}, 404)
                else:
                    sid = unquote(path.removeprefix("/api/phone/sessions/"))
                    sess = phone_trace_store.get_session(sid)
                    self._send_json(sess or {"ok": False, "error": "session_not_found"}, 200 if sess else 404)
            else:
                self._send_json({"ok": False, "error": "not_found"}, 404)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, 500)


def run_server(host="127.0.0.1", port=8777):
    server = ThreadingHTTPServer((host, port), ContextDebugRequestHandler)
    print(f"Yuki Debug WebUI: http://{host}:{port}/ (Phone: http://{host}:{port}/phone)")
    server.serve_forever()


def start_background_server(host="127.0.0.1", port=8777):
    """在主程序进程内后台启动 Debug WebUI，共享内存 snapshot store。"""
    thread = threading.Thread(
        target=run_server,
        kwargs={"host": host, "port": port},
        name="context-debug-webui",
        daemon=True,
    )
    thread.start()
    return thread


def main():
    parser = argparse.ArgumentParser(description="启动 Yuki Context Debug WebUI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8777)
    args = parser.parse_args()
    run_server(args.host, args.port)


if __name__ == "__main__":
    main()
