import os
import sys
import json
import threading
import datetime
from pathlib import Path

# Bảo vệ an toàn trong môi trường Windows EXE (tránh NoneType write crash)
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')

import webview

# Thêm thư mục hiện tại vào sys.path
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config
from database import (
    init_db,
    get_stats,
    get_top_opportunities,
    get_all_topics,
    delete_session,
    rename_topic,
    export_to_csv,
    get_connection
)
from scrapers.seed_generator import harvest_all_raw_keywords
from pipeline.filter_engine import run_pre_filtering
from pipeline.gemini_analyzer import run_gemini_analysis_batch
from pipeline.deep_search_engine import run_deep_keyword_pipeline

# Logger thread-safe lưu trữ log trong bộ nhớ để giao diện polling
class AppLogger:
    def __init__(self):
        self.logs = []
        self._lock = threading.Lock()

    def log(self, msg):
        with self._lock:
            self.logs.append(str(msg))

    def pop_all(self):
        with self._lock:
            if not self.logs:
                return []
            res = list(self.logs)
            self.logs.clear()
            return res

app_logger = AppLogger()

APP_HTML = r"""<!DOCTYPE html>
<html lang="vi" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Derm Keyword Hunter - Desktop Pro</title>
    <style>
        /* CSS Variables - DARK THEME (Mặc định) */
        :root[data-theme="dark"] {
            --bg-body: #0a0e17;
            --bg-navbar: rgba(13, 19, 31, 0.95);
            --bg-card: rgba(20, 27, 44, 0.7);
            --bg-card-hover: rgba(28, 38, 60, 0.9);
            --bg-input: rgba(10, 14, 23, 0.85);
            --bg-console: #070a10;
            --bg-console-header: rgba(255, 255, 255, 0.03);
            --bg-log-row: rgba(255, 255, 255, 0.03);
            --bg-log-row-hover: rgba(255, 255, 255, 0.06);
            --text-console: #cbd5e1;
            --border: rgba(255, 255, 255, 0.08);
            --border-hover: rgba(16, 185, 129, 0.4);
            --text-main: #f1f5f9;
            --text-muted: #94a3b8;
            --text-dim: #64748b;
            --shadow-card: 0 4px 20px rgba(0, 0, 0, 0.3);
            --tag-bg: rgba(255, 255, 255, 0.05);
        }

        /* CSS Variables - LIGHT THEME (Giao diện Sáng cao cấp & rõ nét) */
        :root[data-theme="light"] {
            --bg-body: #f1f5f9;
            --bg-navbar: #ffffff;
            --bg-card: #ffffff;
            --bg-card-hover: #f8fafc;
            --bg-input: #f8fafc;
            --bg-console: #ffffff;
            --bg-console-header: #f8fafc;
            --bg-log-row: #ffffff;
            --bg-log-row-hover: #f1f5f9;
            --text-console: #0f172a;
            --border: #cbd5e1;
            --border-hover: #10b981;
            --text-main: #0f172a;
            --text-muted: #334155;
            --text-dim: #64748b;
            --shadow-card: 0 4px 14px rgba(0, 0, 0, 0.05);
            --tag-bg: #e2e8f0;
        }

        :root {
            --primary: #10b981;
            --primary-hover: #059669;
            --primary-glow: rgba(16, 185, 129, 0.25);
            --accent-blue: #38bdf8;
            --accent-gold: #f59e0b;
            --accent-purple: #a855f7;
            --danger: #ef4444;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease;
        }

        body {
            background-color: var(--bg-body);
            color: var(--text-main);
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            user-select: none;
        }

        /* Top Navbar */
        .navbar {
            height: 68px;
            background: var(--bg-navbar);
            backdrop-filter: blur(20px);
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 28px;
            z-index: 100;
        }

        .brand-box {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .brand-icon {
            width: 40px;
            height: 40px;
            background: linear-gradient(135deg, #10b981, #047857);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
            box-shadow: 0 0 16px var(--primary-glow);
        }

        .brand-title {
            font-size: 16px;
            font-weight: 800;
            letter-spacing: 0.5px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .model-badge {
            font-size: 10px;
            padding: 2px 7px;
            border-radius: 6px;
            background: linear-gradient(135deg, #8b5cf6, #6366f1);
            color: #ffffff;
            font-weight: 700;
            letter-spacing: 0.3px;
        }

        .brand-subtitle {
            font-size: 11px;
            color: var(--text-muted);
            font-weight: 500;
        }

        .nav-tabs {
            display: flex;
            gap: 8px;
            background: var(--bg-card);
            padding: 5px;
            border-radius: 12px;
            border: 1px solid var(--border);
        }

        .nav-btn {
            background: transparent;
            border: none;
            padding: 8px 18px;
            border-radius: 8px;
            color: var(--text-muted);
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.15s ease;
        }

        .nav-btn:hover {
            color: var(--text-main);
        }

        .nav-btn.active {
            background: var(--primary);
            color: #ffffff;
            box-shadow: 0 2px 10px var(--primary-glow);
        }

        .nav-right {
            display: flex;
            align-items: center;
            gap: 14px;
        }

        .theme-btn {
            background: var(--bg-card);
            border: 1px solid var(--border);
            color: var(--text-muted);
            padding: 7px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .theme-btn:hover {
            color: var(--text-main);
            border-color: var(--border-hover);
        }

        .nav-status {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 12px;
            color: var(--primary);
            background: rgba(16, 185, 129, 0.1);
            padding: 6px 14px;
            border-radius: 20px;
            border: 1px solid rgba(16, 185, 129, 0.25);
            font-weight: 600;
        }

        .nav-status.dry {
            color: var(--accent-gold);
            background: rgba(245, 158, 11, 0.1);
            border-color: rgba(245, 158, 11, 0.25);
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: currentColor;
            box-shadow: 0 0 8px currentColor;
        }

        /* Main View Container */
        .content-area {
            flex: 1;
            overflow-y: auto;
            position: relative;
        }

        .tab-pane {
            display: none;
            padding: 20px 28px;
            height: 100%;
        }

        .tab-pane.active {
            display: block;
        }

        /* Metric Cards */
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 16px;
        }

        .metric-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 16px 20px;
            display: flex;
            flex-direction: column;
            gap: 6px;
            box-shadow: var(--shadow-card);
            position: relative;
            overflow: hidden;
        }

        .metric-card:hover {
            transform: translateY(-2px);
            border-color: var(--border-hover);
        }

        .metric-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .metric-label {
            font-size: 11px;
            color: var(--text-muted);
            text-transform: uppercase;
            font-weight: 700;
            letter-spacing: 0.6px;
        }

        .metric-icon {
            font-size: 15px;
            opacity: 0.8;
        }

        .metric-value {
            font-size: 26px;
            font-weight: 800;
            letter-spacing: -0.5px;
        }

        .metric-card.gold .metric-value { color: var(--accent-gold); }
        .metric-card.green .metric-value { color: var(--primary); }
        .metric-card.blue .metric-value { color: var(--accent-blue); }

        /* Prompt Panel (AI Custom Semantic Prompt) */
        .prompt-panel {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 14px 18px;
            margin-bottom: 14px;
            box-shadow: var(--shadow-card);
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .prompt-panel:focus-within {
            border-color: rgba(16, 185, 129, 0.5);
            box-shadow: 0 4px 16px rgba(16, 185, 129, 0.1);
        }

        .prompt-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .prompt-title {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 12px;
            font-weight: 700;
            color: var(--text-main);
        }

        .prompt-badge {
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
            padding: 2px 7px;
            border-radius: 6px;
            background: rgba(168, 85, 247, 0.15);
            color: var(--accent-purple);
            border: 1px solid rgba(168, 85, 247, 0.3);
            letter-spacing: 0.5px;
        }

        .preset-clear-btn {
            background: transparent;
            border: none;
            color: var(--text-muted);
            font-size: 11px;
            font-weight: 600;
            cursor: pointer;
            padding: 3px 8px;
            border-radius: 6px;
        }

        .preset-clear-btn:hover {
            color: var(--danger);
            background: rgba(239, 68, 68, 0.1);
        }

        .prompt-textarea {
            width: 100%;
            padding: 10px 14px;
            background: var(--bg-input);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text-main);
            font-size: 13px;
            font-family: inherit;
            line-height: 1.45;
            resize: vertical;
            min-height: 52px;
            outline: none;
        }

        .prompt-textarea:focus {
            border-color: var(--primary);
        }

        .prompt-presets {
            display: flex;
            align-items: center;
            flex-wrap: wrap;
            gap: 6px;
        }

        .preset-label {
            font-size: 11px;
            font-weight: 600;
            color: var(--text-dim);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .preset-pill {
            padding: 3px 9px;
            border-radius: 16px;
            border: 1px solid var(--border);
            background: var(--tag-bg);
            color: var(--text-muted);
            font-size: 11px;
            font-weight: 500;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }

        .preset-pill:hover {
            color: var(--text-main);
            border-color: var(--primary);
            background: rgba(16, 185, 129, 0.1);
            transform: translateY(-1px);
        }

        .quick-pill {
            padding: 4px 11px;
            border-radius: 16px;
            border: 1px solid var(--border);
            background: var(--bg-card);
            color: var(--text-main);
            font-size: 11.5px;
            font-weight: 600;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            transition: all 0.2s ease;
        }

        .quick-pill:hover {
            border-color: var(--accent-blue);
            color: var(--accent-blue);
            background: var(--bg-card-hover);
            transform: translateY(-1px);
        }

        .rename-topic-btn:hover {
            border-color: var(--accent-blue) !important;
            color: var(--accent-blue) !important;
            background: rgba(56, 189, 248, 0.1) !important;
        }

        /* Control Panel */
        .control-panel {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 14px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 20px;
            margin-bottom: 14px;
            box-shadow: var(--shadow-card);
        }

        .control-group {
            display: flex;
            align-items: center;
            gap: 24px;
            flex: 1;
        }

        .slider-box {
            display: flex;
            flex-direction: column;
            gap: 6px;
            flex: 1;
        }

        .slider-header {
            display: flex;
            justify-content: space-between;
            font-size: 12px;
            color: var(--text-muted);
        }

        .slider-header b {
            color: var(--text-main);
            font-weight: 700;
        }

        input[type="range"] {
            -webkit-appearance: none;
            width: 100%;
            height: 6px;
            border-radius: 4px;
            background: var(--border);
            outline: none;
        }

        input[type="range"]::-webkit-slider-thumb {
            -webkit-appearance: none;
            width: 16px;
            height: 16px;
            border-radius: 50%;
            background: var(--primary);
            cursor: pointer;
            box-shadow: 0 0 8px var(--primary);
        }

        .btn-group {
            display: flex;
            gap: 10px;
        }

        .btn {
            padding: 9px 18px;
            border-radius: 10px;
            border: none;
            font-size: 13px;
            font-weight: 700;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 6px;
            transition: all 0.15s ease;
        }

        .btn-primary {
            background: linear-gradient(135deg, #10b981, #059669);
            color: #ffffff;
            box-shadow: 0 3px 12px var(--primary-glow);
        }

        .btn-primary:hover {
            background: linear-gradient(135deg, #059669, #047857);
            transform: translateY(-1px);
        }

        .btn-secondary {
            background: var(--tag-bg);
            color: var(--text-main);
            border: 1px solid var(--border);
        }

        .btn-secondary:hover {
            border-color: var(--border-hover);
        }

        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none !important;
        }

        /* Log Console (Rich HTML Activity Feed) */
        .console-container {
            background: var(--bg-console);
            border: 1px solid var(--border);
            border-radius: 14px;
            display: flex;
            flex-direction: column;
            height: calc(100vh - 460px);
            min-height: 230px;
            overflow: hidden;
            box-shadow: var(--shadow-card);
        }

        .console-header {
            padding: 10px 18px;
            background: var(--bg-console-header);
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 12px;
            font-weight: 700;
            color: var(--text-muted);
        }

        .console-body {
            flex: 1;
            padding: 12px 16px;
            overflow-y: auto;
            font-family: 'JetBrains Mono', -apple-system, monospace;
            font-size: 12px;
            line-height: 1.5;
            color: var(--text-console);
            display: flex;
            flex-direction: column;
            gap: 5px;
            user-select: text;
        }

        /* Structured HTML Log Components */
        .log-phase-banner {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 8px 12px;
            border-radius: 8px;
            margin: 6px 0 2px 0;
            font-weight: 700;
        }

        .log-phase-banner.t1 {
            background: rgba(56, 189, 248, 0.12);
            border-left: 4px solid var(--accent-blue);
            color: #e0f2fe;
        }

        .log-phase-banner.t2 {
            background: rgba(168, 85, 247, 0.12);
            border-left: 4px solid var(--accent-purple);
            color: #f3e8ff;
        }

        .log-phase-banner.t3 {
            background: rgba(16, 185, 129, 0.12);
            border-left: 4px solid var(--primary);
            color: #d1fae5;
        }

        .log-phase-banner.done {
            background: linear-gradient(90deg, rgba(16, 185, 129, 0.2), rgba(245, 158, 11, 0.15));
            border-left: 4px solid var(--accent-gold);
            color: #fef3c7;
        }

        .phase-tag {
            font-size: 10px;
            font-weight: 800;
            text-transform: uppercase;
            padding: 2px 6px;
            border-radius: 5px;
            background: rgba(255, 255, 255, 0.15);
            letter-spacing: 0.5px;
        }

        .phase-title {
            font-size: 12px;
            letter-spacing: 0.3px;
        }

        .log-prompt-box {
            background: rgba(245, 158, 11, 0.08);
            border: 1px dashed rgba(245, 158, 11, 0.4);
            border-radius: 8px;
            padding: 7px 12px;
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 12px;
            color: var(--accent-gold);
            margin: 2px 0;
        }

        .log-opp-row {
            background: var(--bg-log-row);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 6px 12px;
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 12px;
            color: var(--text-main);
            transition: all 0.15s ease;
        }

        .log-opp-row:hover {
            background: var(--bg-log-row-hover);
            border-color: var(--border-hover);
        }

        /* Light Theme Overrides cho Activity Feed Console */
        :root[data-theme="light"] .console-container {
            background: #ffffff;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.06);
        }
        :root[data-theme="light"] .console-header {
            background: #f8fafc;
            border-bottom: 1px solid #cbd5e1;
            color: #334155;
        }
        :root[data-theme="light"] .console-body {
            background: #ffffff;
            color: #0f172a;
        }
        :root[data-theme="light"] .log-opp-row {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            color: #0f172a;
        }
        :root[data-theme="light"] .log-opp-row:hover {
            background: #f1f5f9;
            border-color: #10b981;
        }
        :root[data-theme="light"] .log-kw {
            color: #0284c7;
            font-weight: 600;
        }
        :root[data-theme="light"] .log-entity {
            color: #0f172a;
        }
        :root[data-theme="light"] .log-phase-banner.t1 {
            background: #e0f2fe;
            border-left: 4px solid #0284c7;
            color: #0369a1;
        }
        :root[data-theme="light"] .log-phase-banner.t2 {
            background: #f3e8ff;
            border-left: 4px solid #9333ea;
            color: #6b21a8;
        }
        :root[data-theme="light"] .log-phase-banner.t3 {
            background: #ecfdf5;
            border-left: 4px solid #10b981;
            color: #047857;
        }
        :root[data-theme="light"] .log-phase-banner.done {
            background: #fef3c7;
            border-left: 4px solid #f59e0b;
            color: #92400e;
        }
        :root[data-theme="light"] .log-switch-card {
            background: #f0fdf4;
            border: 1px solid #10b981;
            color: #0f172a;
        }
        :root[data-theme="light"] .phase-tag {
            background: rgba(0, 0, 0, 0.08);
            color: inherit;
        }
        :root[data-theme="light"] .log-score.dim {
            background: #f1f5f9;
            color: #64748b;
            border: 1px solid #cbd5e1;
        }
        :root[data-theme="light"] .log-score.green {
            background: rgba(16, 185, 129, 0.15) !important;
            color: #059669 !important;
            border: 1px solid #10b981 !important;
        }
        :root[data-theme="light"] .log-score.orange {
            background: rgba(245, 158, 11, 0.15) !important;
            color: #d97706 !important;
            border: 1px solid #f59e0b !important;
        }
        :root[data-theme="light"] .log-score.red {
            background: rgba(239, 68, 68, 0.15) !important;
            color: #dc2626 !important;
            border: 1px solid #ef4444 !important;
        }

        .log-idx {
            font-size: 11px;
            color: var(--text-dim);
            font-weight: 600;
            min-width: 42px;
        }

        .log-kw {
            color: var(--accent-blue);
            font-style: italic;
            font-weight: 500;
        }

        .log-score {
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 700;
            white-space: nowrap;
        }

        .log-score.green {
            background: rgba(16, 185, 129, 0.2) !important;
            color: #10b981 !important;
            border: 1px solid rgba(16, 185, 129, 0.5) !important;
        }

        .log-score.orange, .log-score.gold {
            background: rgba(245, 158, 11, 0.2) !important;
            color: #f59e0b !important;
            border: 1px solid rgba(245, 158, 11, 0.5) !important;
        }

        .log-score.red {
            background: rgba(239, 68, 68, 0.2) !important;
            color: #ef4444 !important;
            border: 1px solid rgba(239, 68, 68, 0.5) !important;
        }

        .log-score.dim {
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-dim);
            border: 1px solid var(--border);
        }

        .log-sell-tag {
            font-size: 10px;
            font-weight: 700;
            padding: 2px 6px;
            border-radius: 4px;
            white-space: nowrap;
        }

        .log-sell-tag.sell-yes {
            background: rgba(16, 185, 129, 0.15);
            color: var(--primary);
        }

        .log-sell-tag.sell-no {
            background: rgba(239, 68, 68, 0.15);
            color: var(--danger);
        }

        .log-entity {
            color: var(--text-main);
            font-weight: 600;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 320px;
        }

        .log-seed-row {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 2px 4px;
            font-size: 11px;
            color: var(--text-muted);
        }

        .seed-idx { color: var(--text-dim); }
        .seed-text { color: var(--text-main); font-weight: 500; }
        .seed-badge {
            background: rgba(56, 189, 248, 0.12);
            color: var(--accent-blue);
            padding: 1px 6px;
            border-radius: 4px;
            font-size: 10px;
        }

        .log-line {
            display: flex;
            gap: 8px;
            padding: 2px 4px;
            color: var(--text-muted);
            font-size: 11.5px;
        }

        .log-time {
            color: var(--text-dim);
            font-size: 10px;
            min-width: 48px;
        }

        .log-switch-card {
            background: linear-gradient(135deg, rgba(16, 185, 129, 0.15), rgba(56, 189, 248, 0.15));
            border: 1px solid var(--primary);
            border-radius: 10px;
            padding: 12px 16px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin: 6px 0;
            color: var(--text-main);
        }

        /* Opportunities View & Topic Filter */
        .filter-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            margin-bottom: 18px;
            background: var(--bg-card);
            border: 1px solid var(--border);
            padding: 12px 18px;
            border-radius: 14px;
            box-shadow: var(--shadow-card);
            flex-wrap: wrap;
        }

        .filter-group-left {
            display: flex;
            align-items: center;
            gap: 14px;
            flex: 1;
            min-width: 380px;
        }

        .topic-filter-box {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .topic-label {
            font-size: 12px;
            font-weight: 700;
            color: var(--text-muted);
            white-space: nowrap;
        }

        .topic-dropdown {
            padding: 8px 12px;
            background: var(--bg-input);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text-main);
            font-size: 12.5px;
            font-weight: 600;
            outline: none;
            min-width: 200px;
            max-width: 280px;
            cursor: pointer;
        }

        .topic-dropdown:focus {
            border-color: var(--primary);
        }

        .search-input {
            flex: 1;
            padding: 8px 14px;
            background: var(--bg-input);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text-main);
            font-size: 13px;
            outline: none;
        }

        .search-input:focus {
            border-color: var(--primary);
        }

        .filter-group-right {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .delete-topic-btn {
            color: var(--danger) !important;
            border-color: rgba(239, 68, 68, 0.3) !important;
        }

        .delete-topic-btn:hover {
            background: rgba(239, 68, 68, 0.1) !important;
            border-color: var(--danger) !important;
        }

        .cards-list {
            display: flex;
            flex-direction: column;
            gap: 12px;
            max-height: calc(100vh - 195px);
            overflow-y: auto;
            padding-right: 4px;
        }

        .opp-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 16px 20px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            box-shadow: var(--shadow-card);
            transition: all 0.2s ease;
        }

        .opp-card:hover {
            border-color: var(--border-hover);
            transform: translateX(2px);
        }

        .opp-card-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .opp-title-box {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .badge-score {
            font-size: 11.5px;
            font-weight: 800;
            padding: 3px 9px;
            border-radius: 16px;
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }

        .badge-score.green {
            background: rgba(16, 185, 129, 0.15) !important;
            color: #10b981 !important;
            border: 1px solid #10b981 !important;
        }

        .badge-score.orange, .badge-score.high {
            background: rgba(245, 158, 11, 0.15) !important;
            color: #f59e0b !important;
            border: 1px solid #f59e0b !important;
        }

        .badge-score.red {
            background: rgba(239, 68, 68, 0.15) !important;
            color: #ef4444 !important;
            border: 1px solid #ef4444 !important;
        }

        .opp-entity-name {
            font-size: 15px;
            font-weight: 700;
            color: var(--text-main);
        }

        .opp-badges {
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .badge-tag {
            font-size: 10.5px;
            font-weight: 600;
            background: var(--tag-bg);
            color: var(--text-muted);
            border: 1px solid var(--border);
            padding: 2px 7px;
            border-radius: 4px;
        }

        .badge-topic {
            font-size: 10.5px;
            font-weight: 600;
            background: rgba(56, 189, 248, 0.1);
            color: var(--accent-blue);
            border: 1px solid rgba(56, 189, 248, 0.25);
            padding: 2px 7px;
            border-radius: 4px;
        }

        .opp-keyword {
            font-size: 12.5px;
            color: var(--accent-blue);
            font-style: italic;
        }

        .opp-summary {
            font-size: 12.5px;
            line-height: 1.5;
            color: var(--text-muted);
            user-select: text;
        }

        /* Settings View */
        .settings-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 24px;
            max-width: 100%;
            display: flex;
            flex-direction: column;
            gap: 18px;
            box-shadow: var(--shadow-card);
        }

        .settings-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 20px;
        }

        @media (max-width: 900px) {
            .settings-grid {
                grid-template-columns: 1fr;
            }
        }

        .settings-api-card {
            background: var(--bg-input);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            transition: all 0.2s ease;
        }

        .settings-api-card:hover {
            border-color: var(--border-hover);
        }

        .api-card-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            padding-bottom: 8px;
            border-bottom: 1px solid var(--border);
        }

        .api-card-title {
            font-size: 13px;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .api-card-hint {
            font-size: 11.5px;
            color: var(--text-muted);
            line-height: 1.45;
            min-height: 34px;
        }

        .form-group {
            display: flex;
            flex-direction: column;
            gap: 6px;
        }

        .form-group label {
            font-size: 13px;
            font-weight: 700;
            color: var(--text-main);
        }

        .form-group .form-hint {
            font-size: 12px;
            color: var(--text-muted);
            line-height: 1.4;
        }

        .input-row {
            display: flex;
            gap: 10px;
        }

        .form-input {
            flex: 1;
            padding: 10px 14px;
            background: var(--bg-input);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text-main);
            font-size: 13px;
            outline: none;
        }

        .form-input:focus {
            border-color: var(--primary);
        }

        /* Export Success Modal */
        .modal-overlay {
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0, 0, 0, 0.7);
            backdrop-filter: blur(8px);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 1000;
        }

        .modal-overlay.show {
            display: flex;
        }

        .modal-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 24px 28px;
            max-width: 600px;
            width: 90%;
            box-shadow: 0 20px 50px rgba(0,0,0,0.5);
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .modal-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .modal-title {
            font-size: 16px;
            font-weight: 800;
            color: var(--primary);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .modal-close-btn {
            background: transparent;
            border: none;
            font-size: 20px;
            color: var(--text-muted);
            cursor: pointer;
        }

        .modal-path-box {
            background: var(--bg-input);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 12px 16px;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }

        .path-label {
            font-size: 11px;
            color: var(--text-dim);
            font-weight: 700;
            text-transform: uppercase;
        }

        .path-text {
            font-size: 12.5px;
            color: var(--accent-blue);
            font-family: 'JetBrains Mono', monospace;
            word-break: break-all;
            user-select: text;
        }

        .modal-actions {
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 10px;
            margin-top: 4px;
        }

        .spinner {
            display: inline-block;
            width: 14px;
            height: 14px;
            border: 2px solid rgba(255,255,255,0.3);
            border-radius: 50%;
            border-top-color: #fff;
            animation: spin 0.8s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <!-- Top Navbar -->
    <div class="navbar">
        <div class="brand-box">
            <div class="brand-icon">🌿</div>
            <div>
                <div class="brand-title">
                    <span>DERM KEYWORD HUNTER</span>
                    <span class="model-badge">Gemini 3.8 Flash</span>
                </div>
                <div class="brand-subtitle">Bộ công cụ đãi vàng từ khóa • SQLite Local Storage</div>
            </div>
        </div>

        <div class="nav-tabs">
            <button id="nav-btn-dashboard" class="nav-btn active" onclick="switchTab('dashboard')">
                <span>🔥</span> Google Trending
            </button>
            <button id="nav-btn-deepsearch" class="nav-btn" onclick="switchTab('deepsearch')">
                <span>🔎</span> Nghiên Cứu Từ Khóa
            </button>
            <button id="nav-btn-database" class="nav-btn" onclick="switchTab('database')">
                <span>💎</span> Kho Cơ Hội Vàng
            </button>
            <button id="nav-btn-settings" class="nav-btn" onclick="switchTab('settings')">
                <span>⚙️</span> Cài Đặt Hệ Thống
            </button>
        </div>

        <div class="nav-right">
            <button id="themeToggleBtn" class="theme-btn" onclick="toggleTheme()">
                <span id="themeIcon">☀️</span>
                <span id="themeText">Giao diện Sáng</span>
            </button>

            <div id="statusBadge" class="nav-status dry">
                <div class="status-dot"></div>
                <span id="statusText">Chế độ Dry-Run (Chưa nhập key)</span>
            </div>
        </div>
    </div>

    <!-- Main View Container -->
    <div class="content-area">
        <!-- TAB 1: DASHBOARD -->
        <div id="tab-dashboard" class="tab-pane active">
            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-header">
                        <span class="metric-label">Từ Khóa Thô</span>
                        <span class="metric-icon">📥</span>
                    </div>
                    <div id="mRaw" class="metric-value">0</div>
                </div>
                <div class="metric-card blue">
                    <div class="metric-header">
                        <span class="metric-label">Sweet Spot Lọt Lưới</span>
                        <span class="metric-icon">🎯</span>
                    </div>
                    <div id="mFiltered" class="metric-value">0</div>
                </div>
                <div class="metric-card green">
                    <div class="metric-header">
                        <span class="metric-label">Đã Phân Tích AI</span>
                        <span class="metric-icon">🤖</span>
                    </div>
                    <div id="mAnalyzed" class="metric-value">0</div>
                </div>
                <div class="metric-card gold">
                    <div class="metric-header">
                        <span class="metric-label">Cơ Hội Vàng (≥ 7.0)</span>
                        <span class="metric-icon">💎</span>
                    </div>
                    <div id="mGems" class="metric-value">0</div>
                </div>
            </div>

            <!-- TẦNG 1: BỘ ĐIỀU KHIỂN GOOGLE TRENDING VIỆT NAM -->
            <div class="prompt-panel" style="background: var(--bg-card); border: 1px solid var(--border); border-radius: 14px; padding: 18px 22px;">
                <div class="prompt-header" style="margin-bottom: 12px;">
                    <div class="prompt-title" style="display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 18px;">🔥</span>
                        <span style="font-weight: 800; font-size: 14px; color: var(--primary);">NGUỒN TẦNG 1: GOOGLE TRENDING VIỆT NAM (TRENDS.GOOGLE.COM/TRENDING?GEO=VN)</span>
                        <span class="prompt-badge" style="background: rgba(16, 185, 129, 0.15); color: var(--primary); border: 1px solid rgba(16, 185, 129, 0.3);">Realtime Data</span>
                    </div>
                </div>
                
                <!-- BỘ CHỌN CHỦ ĐỀ NGÀNH HÀNG -->
                <div style="margin-bottom: 14px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 10px; padding: 12px 16px;">
                    <label style="font-size: 12.5px; font-weight: 800; color: var(--text-main); display: block; margin-bottom: 6px;">
                        🎯 CHỌN NGÀNH HÀNG / CHỦ ĐỀ NGHIÊN CỨU:
                    </label>
                    <select id="selectTopicMode" class="form-input" style="font-weight: 700; font-size: 13.5px; color: var(--primary); background: var(--bg-card); cursor: pointer;">
                        <option value="topic_1" selected>🌿 Chủ đề 1: Da Liễu & Dược Mỹ Phẩm (Da cơ thể, Mỹ phẩm, Thuốc da liễu)</option>
                        <option value="topic_2">⚡ Chủ đề 2: Đồ Điện Tử Gia Dụng (Thiết bị gia đình, đồ điện thông minh, nhà bếp)</option>
                    </select>
                    <div style="font-size: 11.5px; color: var(--text-muted); margin-top: 6px; line-height: 1.4;">
                        Tầng 1 cào xu hướng Google Trends theo Khối lượng tìm kiếm bạn chọn. Tầng 2 (Serper.dev) sẽ lọc chuẩn xác theo ngành hàng đã chọn và loại bỏ toàn bộ các trend không liên quan.
                    </div>
                </div>

                <!-- LƯỚI THIẾT LẬP THAM SỐ GOOGLE TRENDS -->
                <div style="display: grid; grid-template-columns: 1fr 1fr 1.2fr; gap: 16px; align-items: end;">
                    <div class="form-group">
                        <label style="font-size: 12px; font-weight: 700;">📊 Khối lượng tìm kiếm tối thiểu (Search Volume):</label>
                        <select id="selectMinVolume" class="form-input">
                            <option value="0">Tất cả xu hướng (Volume ≥ 0)</option>
                            <option value="500">≥ 500+ lượt tìm kiếm</option>
                            <option value="1000" selected>≥ 1.000+ lượt tìm kiếm (Khuyên dùng)</option>
                            <option value="2000">≥ 2.000+ lượt tìm kiếm</option>
                            <option value="5000">≥ 5.000+ lượt tìm kiếm</option>
                            <option value="10000">≥ 10.000+ (10 N+) lượt tìm kiếm</option>
                            <option value="20000">≥ 20.000+ (20 N+) lượt tìm kiếm</option>
                            <option value="50000">≥ 50.000+ (50 N+) lượt tìm kiếm</option>
                        </select>
                    </div>

                    <div class="form-group">
                        <label style="font-size: 12px; font-weight: 700;">⏱️ Khung thời gian Google Trends:</label>
                        <select id="selectTrendHours" class="form-input">
                            <option value="720">30 ngày qua (1 tháng - Toàn diện nhất)</option>
                            <option value="168" selected>7 ngày qua (Mặc định - 700+ xu hướng)</option>
                            <option value="48">48 giờ qua</option>
                            <option value="24">24 giờ qua</option>
                        </select>
                    </div>

                    <div class="slider-box" style="padding: 10px 14px;">
                        <div class="slider-header" style="margin-bottom: 6px;">
                            <span style="font-size: 12px;">Giới hạn phân tích AI (Tầng 3):</span>
                            <b id="valAi" style="font-size: 13px; color: var(--primary);">15 từ khóa</b>
                        </div>
                        <input type="range" id="sliderAi" min="5" max="40" step="5" value="15" oninput="document.getElementById('valAi').innerText = this.value + ' từ khóa'">
                    </div>
                </div>

                <!-- HÀNG NÚT BẤM BẮT ĐẦU -->
                <div style="display: flex; gap: 12px; margin-top: 18px; align-items: center;">
                    <button id="btnRunAll" class="btn btn-primary" style="font-size: 14px; padding: 12px 28px; font-weight: 800;" onclick="startFullPipeline()">
                        <span id="runSpinner" style="display: none;" class="spinner"></span>
                        <span id="runText">🚀 QUÉT GOOGLE TRENDING & CHẠY 4 TẦNG</span>
                    </button>
                    <button class="btn btn-secondary" onclick="exportCsv()">
                        📊 Xuất File CSV
                    </button>
                    <span style="font-size: 11.5px; color: var(--text-muted); margin-left: auto;">
                        💡 Không cần gõ Prompt — Hệ thống tự bắt sóng xu hướng & lọc chuẩn ngành Da liễu!
                    </span>
                </div>
            </div>

            <!-- TIẾN ĐỘ THỰC THI THỜI GIAN THỰC (PROGRESS BAR) -->
            <div id="trendProgressContainer" style="display: none; margin-bottom: 12px; background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 10px 14px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <span id="trendProgressText" style="font-size: 12px; font-weight: 700; color: var(--text-main);">Đang thu thập và phân tích xu hướng...</span>
                    <span id="trendProgressPercent" style="font-size: 12.5px; font-weight: 800; color: var(--primary);">0%</span>
                </div>
                <div style="width: 100%; height: 7px; background: var(--bg-input); border-radius: 4px; overflow: hidden;">
                    <div id="trendProgressBar" style="width: 0%; height: 100%; background: linear-gradient(90deg, #10b981, #06b6d4); transition: width 0.3s ease; border-radius: 4px;"></div>
                </div>
            </div>

            <div class="console-container">
                <div class="console-header">
                    <span>📋 NHẬT KÝ THỰC THI THỜI GIAN THỰC (LIVE ACTIVITY FEED):</span>
                    <div style="display: flex; gap: 8px;">
                        <button class="btn btn-secondary" style="padding: 3px 8px; font-size: 11px;" onclick="clearConsole()">Xóa Log</button>
                    </div>
                </div>
                <div id="consoleBody" class="console-body">
                    <div class="log-phase-banner t3">
                        <span class="phase-tag">SẴN SÀNG</span>
                        <span class="phase-title">=== HỆ THỐNG ĐÃ SẴN SÀNG • GEMINI 3.8 FLASH ===</span>
                    </div>
                    <div class="log-line">
                        <span class="log-time">INFO</span>
                        <span>Nhập Custom Prompt hoặc nhấn "CHẠY TOÀN BỘ 4 TẦNG" để bắt đầu quét và phân tích.</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- TAB 2: DEEP KEYWORD SEARCH (SERPER.DEV & REALTIME GEO) -->
        <div id="tab-deepsearch" class="tab-pane">
            <div class="control-card" style="margin-bottom: 16px;">
                <div class="control-header" style="margin-bottom: 12px;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 18px;">🔎</span>
                        <span style="font-weight: 800; font-size: 14px; color: var(--accent-blue);">NGHIÊN CỨU TỪ KHÓA SÂU (SERPER.DEV & GOOGLE REALTIME GEO)</span>
                        <span class="prompt-badge" style="background: rgba(56, 189, 248, 0.15); color: var(--accent-blue); border: 1px solid rgba(56, 189, 248, 0.3);">100% Số Liệu Thật</span>
                    </div>
                </div>

                <!-- Ô NHẬP TỪ KHÓA HẠT GIỐNG -->
                <div style="margin-bottom: 14px;">
                    <label style="font-size: 12.5px; font-weight: 800; color: var(--text-main); display: block; margin-bottom: 6px;">
                        🎯 NHẬP TỪ KHÓA HẠT GIỐNG CẦN ĐÀO SÂU (SEED KEYWORD):
                    </label>
                    <div style="display: flex; gap: 10px;">
                        <input type="text" id="inputDeepKeyword" class="form-input" style="flex: 1; font-weight: 700; font-size: 13.5px; padding: 10px 14px;" placeholder="Ví dụ: peel da, meso mụn phan thiết, trị nám tàn nhang, nồi chiên lock&lock...">
                        <button id="btnRunDeep" class="btn btn-primary" style="padding: 10px 22px; font-weight: 800; font-size: 13px; white-space: nowrap; background: linear-gradient(135deg, #0284c7, #0ea5e9);" onclick="startDeepSearchPipeline()">
                            <span id="deepRunSpinner" style="display:none;" class="spinner"></span>
                            <span id="deepRunText">🚀 ĐÀO ~100 TỪ KHÓA & PHÂN TÍCH</span>
                        </button>
                    </div>
                    <!-- GỢI Ý MẪU BẤM NHANH -->
                    <div style="display: flex; gap: 7px; margin-top: 8px; flex-wrap: wrap; align-items: center;">
                        <span style="font-size: 11px; color: var(--text-dim); font-weight: 700;">Gợi ý mẫu:</span>
                        <span class="quick-pill" onclick="setDeepSeed('peel da')">🌿 peel da</span>
                        <span class="quick-pill" onclick="setDeepSeed('meso mụn phan thiết')">📍 meso mụn phan thiết</span>
                        <span class="quick-pill" onclick="setDeepSeed('tiêm meso căng bóng')">✨ tiêm meso căng bóng</span>
                        <span class="quick-pill" onclick="setDeepSeed('trị sẹo rỗ chuẩn y khoa')">🔬 trị sẹo rỗ chuẩn y khoa</span>
                        <span class="quick-pill" onclick="setDeepSeed('nồi chiên không dầu hơi nước')">⚡ nồi chiên không dầu hơi nước</span>
                        <span class="quick-pill" onclick="setDeepSeed('máy lọc không khí bù ẩm')">💨 máy lọc không khí bù ẩm</span>
                    </div>
                </div>

                <!-- BỘ LỌC THAM SỐ 4 CỘT -->
                <div style="display: grid; grid-template-columns: 1.2fr 1fr 1fr 1.2fr; gap: 14px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px;">
                    <!-- 1. VỊ TRÍ ĐỊA LÝ -->
                    <div class="form-group">
                        <label style="font-size: 11.5px; font-weight: 700; color: var(--text-main); display: block; margin-bottom: 4px;">📍 Vị trí địa lý (Location / Geo):</label>
                        <select id="selectDeepLocation" class="form-input" style="font-size: 12.5px;">
                            <option value="Phan Thiet, Binh Thuan, Vietnam" selected>Phan Thiết, Bình Thuận (Địa phương cũ)</option>
                            <option value="Phan Thiet, Lam Dong, Vietnam">Phan Thiết, Lâm Đồng (Khu vực mở rộng mới)</option>
                            <option value="Vietnam">Toàn quốc Việt Nam (Toàn diện)</option>
                            <option value="Ho Chi Minh City, Vietnam">TP. Hồ Chí Minh</option>
                            <option value="Hanoi, Vietnam">Hà Nội</option>
                            <option value="Da Nang, Vietnam">Đà Nẵng</option>
                            <option value="Can Tho, Vietnam">Cần Thơ</option>
                            <option value="Hai Phong, Vietnam">Hải Phòng</option>
                            <option value="Nha Trang, Khanh Hoa, Vietnam">Nha Trang, Khánh Hòa</option>
                            <option value="Binh Duong, Vietnam">Bình Dương</option>
                            <option value="Dong Nai, Vietnam">Đồng Nai</option>
                            <option value="Vung Tau, Ba Ria - Vung Tau, Vietnam">Bà Rịa - Vũng Tàu</option>
                        </select>
                    </div>

                    <!-- 2. KHUNG THỜI GIAN GOOGLE -->
                    <div class="form-group">
                        <label style="font-size: 11.5px; font-weight: 700; color: var(--text-main); display: block; margin-bottom: 4px;">⏱️ Thời gian tìm kiếm:</label>
                        <select id="selectDeepTimeRange" class="form-input" style="font-size: 12.5px;">
                            <option value="" selected>Tất cả thời gian (Toàn diện nhất)</option>
                            <option value="qdr:m">1 tháng qua (Xu hướng mới)</option>
                            <option value="qdr:w">7 ngày qua (Mới nhất)</option>
                            <option value="qdr:d">24 giờ qua (Thời gian thực)</option>
                            <option value="qdr:y">1 năm qua (12 tháng qua)</option>
                        </select>
                    </div>

                    <!-- 3. MỤC TIÊU SỐ TỪ KHÓA -->
                    <div class="form-group">
                        <label style="font-size: 11.5px; font-weight: 700; color: var(--text-main); display: block; margin-bottom: 4px;">📊 Số từ khóa muốn thu thập:</label>
                        <select id="selectDeepLimit" class="form-input" style="font-size: 12.5px;">
                            <option value="100" selected>~100 từ khóa thật (Khuyên dùng)</option>
                            <option value="50">~50 từ khóa thật (Nhanh)</option>
                            <option value="150">~150 từ khóa thật</option>
                            <option value="200">~200 từ khóa thật (Sâu)</option>
                        </select>
                    </div>

                    <!-- 4. SLIDER GEMINI PHÂN TÍCH -->
                    <div class="slider-box" style="padding: 6px 12px; margin: 0; display: flex; flex-direction: column; justify-content: center;">
                        <div class="slider-header" style="margin-bottom: 4px;">
                            <span style="font-size: 11px; font-weight: 700;">🤖 AI Phân Tích Sâu:</span>
                            <span id="valDeepAiLimit" class="slider-value" style="font-size: 11.5px; color: var(--accent-blue);">25 từ khóa</span>
                        </div>
                        <input type="range" id="sliderDeepAi" min="10" max="50" step="5" value="25" oninput="document.getElementById('valDeepAiLimit').innerText = this.value + ' từ khóa'">
                    </div>
                </div>
            </div>

            <!-- TIẾN ĐỘ NGHIÊN CỨU SÂU (PROGRESS BAR) -->
            <div id="deepProgressContainer" style="display: none; margin-bottom: 12px; background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 10px 14px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <span id="deepProgressText" style="font-size: 12px; font-weight: 700; color: var(--text-main);">Đang khởi động phân tích từ khóa sâu...</span>
                    <span id="deepProgressPercent" style="font-size: 12.5px; font-weight: 800; color: var(--primary);">0%</span>
                </div>
                <div style="width: 100%; height: 7px; background: var(--bg-input); border-radius: 4px; overflow: hidden;">
                    <div id="deepProgressBar" style="width: 0%; height: 100%; background: linear-gradient(90deg, #10b981, #06b6d4); transition: width 0.3s ease; border-radius: 4px;"></div>
                </div>
            </div>

            <!-- ACTIVITY FEED / CONSOLE CHO DEEP SEARCH -->
            <div class="console-container">
                <div class="console-header">
                    <span>📋 NHẬT KÝ NGHIÊN CỨU TỪ KHÓA SÂU (LIVE ACTIVITY FEED):</span>
                    <div style="display: flex; gap: 8px;">
                        <button class="btn btn-secondary" style="padding: 3px 8px; font-size: 11px;" onclick="clearDeepConsole()">Xóa Log</button>
                    </div>
                </div>
                <div id="deepConsoleBody" class="console-body">
                    <div class="log-phase-banner t1">
                        <span class="phase-tag">SẴN SÀNG</span>
                        <span class="phase-title">=== TAB NGHIÊN CỨU TỪ KHÓA SÂU • 100% DỮ LIỆU THẬT TỪ GOOGLE & SERPER ===</span>
                    </div>
                    <div class="log-line">
                        <span class="log-time">INFO</span>
                        <span>Nhập từ khóa hạt giống (ví dụ: "peel da" hoặc "meso mụn phan thiết") và nhấn BẮT ĐẦU ĐÀO SÂU để cào ~100 từ khóa thực tế và phân tích cơ hội.</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- TAB 3: DATABASE VIEW -->
        <div id="tab-database" class="tab-pane">
            <div class="filter-row">
                <div class="filter-group-left">
                    <div class="topic-filter-box">
                        <span class="topic-label">📁 Chủ đề:</span>
                        <select id="selectTopicFilter" class="topic-dropdown" onchange="loadOpportunities()">
                            <option value="all">💎 Tất cả chủ đề (Toàn bộ kho dữ liệu)</option>
                        </select>
                    </div>
                    <div class="topic-filter-box">
                        <span class="topic-label">🎯 Ý định:</span>
                        <select id="selectIntentFilter" class="topic-dropdown" onchange="loadOpportunities()" style="min-width: 145px;">
                            <option value="all">🎯 Tất cả ý định</option>
                            <option value="TRANSACTIONAL">🛒 TRANSACTIONAL (Mua/Đặt lịch)</option>
                            <option value="COMMERCIAL">🔍 COMMERCIAL (So sánh/Uy tín)</option>
                            <option value="INFORMATIONAL">📖 INFORMATIONAL (Hỏi đáp)</option>
                        </select>
                    </div>
                    <input type="text" id="searchInput" class="search-input" placeholder="🔍 Tìm kiếm sản phẩm, từ khóa..." onkeyup="if(event.key === 'Enter') loadOpportunities()">
                </div>
                
                <div class="filter-group-right">
                    <span style="font-size: 12.5px; color: var(--text-muted); white-space: nowrap;">Điểm: <b id="valMinScore" style="color: var(--accent-gold)">≥ 6.0</b></span>
                    <input type="range" id="sliderScore" min="1" max="9" step="1" value="6" style="width: 90px;" oninput="document.getElementById('valMinScore').innerText = '≥ ' + this.value + '.0'; loadOpportunities()">
                    <button class="btn btn-secondary" onclick="loadOpportunities()">🔄 Làm Mới</button>
                    <button class="btn btn-secondary" style="color: var(--primary); border-color: rgba(16, 185, 129, 0.4); font-weight: 700;" onclick="copyAllOpportunitiesText()">📋 Copy Toàn Bộ TXT</button>
                    <button class="btn btn-primary" onclick="exportCsv()">📊 Xuất File Excel/CSV</button>
                    <button class="btn btn-secondary rename-topic-btn" title="Đổi tên chủ đề đang chọn" onclick="renameCurrentTopic()" style="font-weight: 700; color: var(--accent-blue); border-color: rgba(56, 189, 248, 0.4);">✏️ Đổi Tên Chủ Đề</button>
                    <button class="btn btn-secondary delete-topic-btn" title="Xóa đợt quét đang chọn" onclick="deleteCurrentTopic()">🗑️ Xóa Đợt Này</button>
                </div>
            </div>

            <div id="cardsList" class="cards-list">
                <!-- Danh sách sản phẩm load động -->
            </div>
        </div>

        <!-- TAB 3: CÀI ĐẶT HỆ THỐNG -->
        <div id="tab-settings" class="tab-pane">
            <div class="settings-card">
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 12px;">
                    <div>
                        <h3 style="color: var(--primary); font-size: 17px; font-weight: 800; margin: 0;">⚙️ CẤU HÌNH PIPELINE & KHÓA API</h3>
                        <p style="font-size: 12.5px; color: var(--text-muted); margin: 4px 0 0 0;">Tầng 1 chạy tự động 100% miễn phí (Deep Google Suggest Matrix). Khóa API được lưu vĩnh viễn trong User AppData trên máy tính.</p>
                    </div>
                    <span style="font-size: 11.5px; background: rgba(16, 185, 129, 0.12); color: var(--primary); padding: 5px 12px; border-radius: 20px; border: 1px solid rgba(16, 185, 129, 0.3); font-weight: 700;">
                        🛡️ Local Persistent Storage
                    </span>
                </div>

                <!-- LƯỚI 2 CỘT CÂN ĐỐI CHO SERPER & GEMINI -->
                <div class="settings-grid">
                    <!-- CỘT 1: SERPER.DEV -->
                    <div class="settings-api-card">
                        <div class="api-card-header">
                            <span class="api-card-title" style="color: #9333ea;">🔎 SERPER.DEV API (TẦNG 2)</span>
                            <button id="btnTestSerper" class="btn btn-secondary" style="font-size: 11px; padding: 4px 10px; color: #9333ea; border-color: rgba(147, 51, 234, 0.4);" onclick="testSerperKey()">⚡ Test Serper</button>
                        </div>
                        <div class="api-card-hint">Trích xuất Top 5 SERP Google thực tế, thẩm định đối thủ thị trường và đào sâu Related Queries. Nếu để trống, Gemini sẽ dùng Google Search Grounding.</div>
                        <div class="form-group">
                            <label style="font-size: 12px;">Serper.dev API Key:</label>
                            <input type="text" id="inputSerperKey" class="form-input" placeholder="Ví dụ: a63c95bc392ddb9c0c591...">
                        </div>
                        <div style="font-size: 11px; color: var(--text-muted); margin-top: auto; padding-top: 10px; border-top: 1px dashed var(--border);">
                            💡 Đăng ký nhận <b>2.500 lượt tìm kiếm miễn phí</b> tại website <a href="https://serper.dev" target="_blank" style="color: var(--primary); text-decoration: none;">serper.dev</a>
                        </div>
                    </div>

                    <!-- CỘT 2: GOOGLE GEMINI AI -->
                    <div class="settings-api-card">
                        <div class="api-card-header">
                            <span class="api-card-title" style="color: var(--primary);">🧠 GOOGLE GEMINI AI (TẦNG 3)</span>
                            <button id="btnTestKey" class="btn btn-secondary" style="font-size: 11px; padding: 4px 10px; color: var(--primary); border-color: rgba(16, 185, 129, 0.4);" onclick="testGeminiKey()">⚡ Test Gemini</button>
                        </div>
                        <div class="api-card-hint">Mô hình AI bóc tách công thức hoạt chất, góc USP, phân tích đối thủ và chấm điểm cơ hội thương mại (>= 7.0 điểm).</div>
                        <div class="form-group">
                            <label style="font-size: 12px;">Google Gemini API Key:</label>
                            <div class="input-row">
                                <input type="password" id="inputGeminiKey" class="form-input" placeholder="AIzaSy...">
                                <button class="btn btn-secondary" onclick="togglePassword('inputGeminiKey')">Hiện</button>
                            </div>
                        </div>
                        <div class="form-group">
                            <label style="font-size: 12px;">Mô hình AI mặc định (Model):</label>
                            <select id="selectModel" class="form-input">
                                <option value="gemini-3.8-flash" selected>Gemini 3.8 Flash (High) - [Mặc định]</option>
                                <option value="gemini-2.5-flash">Gemini 2.5 Flash</option>
                                <option value="gemini-2.0-flash">Gemini 2.0 Flash</option>
                            </select>
                        </div>
                        <div style="font-size: 11px; color: var(--text-muted); margin-top: auto; padding-top: 10px; border-top: 1px dashed var(--border);">
                            💡 Lấy khóa API miễn phí từ Google AI Studio (<a href="https://aistudio.google.com" target="_blank" style="color: var(--primary); text-decoration: none;">aistudio.google.com</a>)
                        </div>
                    </div>
                </div>

                <!-- KHỐI DƯỚI: VỊ TRÍ DB & CÁC NÚT THAO TÁC -->
                <div style="display: flex; justify-content: space-between; align-items: center; background: var(--bg-input); border: 1px solid var(--border); border-radius: 12px; padding: 14px 20px; flex-wrap: wrap; gap: 12px;">
                    <div>
                        <div style="font-size: 12px; font-weight: 700; color: var(--text-main);">📁 Lưu trữ Dữ liệu SQLite Cục bộ:</div>
                        <div class="form-hint" id="dbPathHint" style="font-size: 11.5px; color: var(--text-muted); margin-top: 2px;">Vị trí SQLite: product_opportunities.db</div>
                    </div>
                    <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                        <button id="btnSaveSettings" class="btn btn-primary" onclick="saveSettings()">💾 Lưu Cài Đặt (Vĩnh Viễn)</button>
                        <button class="btn btn-secondary" onclick="openDatabaseFolder()">📂 Mở Thư Mục Báo Cáo / DB</button>
                        <button class="btn btn-secondary" style="color: var(--danger); border-color: rgba(239, 68, 68, 0.3);" onclick="resetDatabase()">🗑️ Xóa Trắng Toàn Bộ DB</button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Export Success Modal -->
    <div id="exportModal" class="modal-overlay">
        <div class="modal-card">
            <div class="modal-header">
                <div class="modal-title">
                    <span>✅</span>
                    <span>XUẤT BÁO CÁO THÀNH CÔNG!</span>
                </div>
                <button class="modal-close-btn" onclick="closeExportModal()">✕</button>
            </div>
            
            <p style="font-size: 13px; color: var(--text-muted);">Dữ liệu cơ hội từ khóa đã được xuất đầy đủ ra file CSV chuẩn UTF-8 BOM (tương thích 100% với Excel).</p>
            
            <div class="modal-path-box">
                <span class="path-label">📁 Thư mục lưu trữ:</span>
                <span id="exportFolderText" class="path-text">...</span>
            </div>

            <div class="modal-path-box">
                <span class="path-label">📄 Tên file đã xuất:</span>
                <span id="exportFileText" class="path-text" style="color: var(--primary); font-weight: 700;">...</span>
            </div>

            <div class="modal-actions">
                <button class="btn btn-secondary" onclick="closeExportModal()">Đóng</button>
                <button class="btn btn-secondary" onclick="openExportFolder()">📂 Mở Thư Mục</button>
                <button class="btn btn-primary" onclick="openExportedFile()">📊 Mở File Excel Ngay</button>
            </div>
        </div>
    </div>

    <script>
        let isRunning = false;
        let activeSessionId = 'all';
        let latestExportedPath = '';
        let latestExportedFolder = '';
        let logPollTimer = null;

        function isApiReady() {
            return !!(window.pywebview && window.pywebview.api && (
                typeof window.pywebview.api.save_settings === 'function' ||
                typeof window.pywebview.api.get_settings === 'function'
            ));
        }

        let currentOpportunitiesList = [];

        function copyToClipboard(text, successMsg) {
            try {
                if (navigator.clipboard && window.isSecureContext) {
                    navigator.clipboard.writeText(text).then(() => {
                        alert('✅ ' + successMsg);
                    }).catch(() => fallbackCopy(text, successMsg));
                } else {
                    fallbackCopy(text, successMsg);
                }
            } catch (e) {
                fallbackCopy(text, successMsg);
            }
        }

        function fallbackCopy(text, successMsg) {
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.position = 'fixed';
            ta.style.left = '-9999px';
            document.body.appendChild(ta);
            ta.focus();
            ta.select();
            try {
                document.execCommand('copy');
                alert('✅ ' + successMsg);
            } catch (e) {
                alert('Lỗi sao chép: ' + e);
            }
            document.body.removeChild(ta);
        }

        function copyAllOpportunitiesText() {
            if (!currentOpportunitiesList || currentOpportunitiesList.length === 0) {
                alert('Chưa có cơ hội nào trong danh sách để sao chép!');
                return;
            }
            let text = `=== BÁO CÁO CƠ HỘI SẢN PHẨM DƯỢC MỸ PHẨM & DA LIỄU ===\n`;
            text += `Tổng số cơ hội: ${currentOpportunitiesList.length}\n`;
            text += `Thời gian xuất: ${new Date().toLocaleString('vi-VN')}\n`;
            text += `====================================================\n\n`;

            currentOpportunitiesList.forEach((it, idx) => {
                text += `[#${idx + 1}] SẢN PHẨM: ${it.entity_name || 'Chưa rõ tên'} (Điểm: ${it.opportunity_score.toFixed(1)}/10)\n`;
                text += `- Từ khóa: "${it.keyword}"\n`;
                text += `- Phân loại: ${it.category} | Ý định: ${it.search_intent}\n`;
                if (it.topic) text += `- Đợt quét: ${it.topic}\n`;
                text += `- Tóm tắt & Góc USP: ${it.ai_summary}\n`;
                text += `----------------------------------------------------\n\n`;
            });

            copyToClipboard(text, `Đã sao chép toàn bộ ${currentOpportunitiesList.length} cơ hội sản phẩm dạng TXT vào Clipboard!`);
        }

        function copySingleCardText(idx) {
            if (!currentOpportunitiesList || !currentOpportunitiesList[idx]) return;
            const it = currentOpportunitiesList[idx];
            let text = `SẢN PHẨM: ${it.entity_name || 'Chưa rõ tên'} (Điểm: ${it.opportunity_score.toFixed(1)}/10)\n`;
            text += `- Từ khóa: "${it.keyword}"\n`;
            text += `- Phân loại: ${it.category} | Ý định: ${it.search_intent}\n`;
            text += `- Tóm tắt & Góc USP: ${it.ai_summary}\n`;

            copyToClipboard(text, `Đã sao chép cơ hội "${it.entity_name}" vào Clipboard!`);
        }

        // Chuyển đổi giao diện Sáng / Tối
        function toggleTheme() {
            const root = document.documentElement;
            const currentTheme = root.getAttribute('data-theme') || 'dark';
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            
            root.setAttribute('data-theme', newTheme);
            localStorage.setItem('derm_theme', newTheme);

            const icon = document.getElementById('themeIcon');
            const text = document.getElementById('themeText');
            if (newTheme === 'dark') {
                icon.innerText = '☀️';
                text.innerText = 'Giao diện Sáng';
            } else {
                icon.innerText = '🌙';
                text.innerText = 'Giao diện Tối';
            }
        }

        (function initTheme() {
            const saved = localStorage.getItem('derm_theme') || 'dark';
            document.documentElement.setAttribute('data-theme', saved);
            window.addEventListener('DOMContentLoaded', () => {
                const icon = document.getElementById('themeIcon');
                const text = document.getElementById('themeText');
                if (saved === 'dark') {
                    if (icon) icon.innerText = '☀️';
                    if (text) text.innerText = 'Giao diện Sáng';
                } else {
                    if (icon) icon.innerText = '🌙';
                    if (text) text.innerText = 'Giao diện Tối';
                }
            });
        })();

        // CHUYỂN TAB TRỰC TIẾP QUA ID - 100% KHÔNG BAO GIỜ BỊ ĐỨNG
        function switchTab(tabId) {
            try {
                document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
                document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));
                
                const activeBtn = document.getElementById('nav-btn-' + tabId);
                if (activeBtn) activeBtn.classList.add('active');
                
                const targetPane = document.getElementById('tab-' + tabId);
                if (targetPane) targetPane.classList.add('active');

                if (tabId === 'dashboard') {
                    refreshStats();
                } else if (tabId === 'database') {
                    loadTopics().then(() => loadOpportunities()).catch(err => console.error(err));
                }
            } catch (err) {
                console.error('Error switching tab:', err);
            }
        }

        function getTimeStr() {
            const d = new Date();
            return d.toTimeString().split(' ')[0];
        }

        // PARSER & FORMATTER: BIẾN CONSOLE RAW TEXT THÀNH GIAO DIỆN HTML ĐẸP MẮT
        function appendLog(rawText) {
            try {
                if (!rawText || typeof rawText !== 'string' || !rawText.trim()) return;
                const el = document.getElementById('consoleBody');
                if (!el) return;
                const lines = rawText.split('\n');

                lines.forEach(line => {
                    const trimmed = line.trim();
                    if (!trimmed) return;

                    const time = getTimeStr();

                    // 1. Phân tầng Pipeline Banners
                    if (trimmed.includes('[TẦNG 1')) {
                        el.insertAdjacentHTML('beforeend', `
                            <div class="log-phase-banner t1">
                                <span class="phase-tag">TẦNG 1</span>
                                <span class="phase-title">🔥 DATA INGESTION: THU THẬP TỪ KHÓA THÔ TỪ GOOGLE TRENDS VN</span>
                            </div>
                        `);
                        return;
                    }
                    if (trimmed.includes('[TẦNG 2')) {
                        el.insertAdjacentHTML('beforeend', `
                            <div class="log-phase-banner t2">
                                <span class="phase-tag">TẦNG 2</span>
                                <span class="phase-title">🔎 SERPER AUDIT: THẨM ĐỊNH & LỌC TỪ KHÓA THEO CHỦ ĐỀ MỤC TIÊU</span>
                            </div>
                        `);
                        return;
                    }
                    if (trimmed.includes('[TẦNG 3 - AI INTELLIGENCE]')) {
                        el.insertAdjacentHTML('beforeend', `
                            <div class="log-phase-banner t3">
                                <span class="phase-tag">TẦNG 3</span>
                                <span class="phase-title">🤖 AI INTELLIGENCE: GEMINI FLASH PHÂN TÍCH BÓC TÁCH CƠ HỘI</span>
                            </div>
                        `);
                        return;
                    }
                    if (trimmed.includes('HOÀN TẤT TOÀN BỘ PIPELINE 4 TẦNG THÀNH CÔNG')) {
                        const pBar = document.getElementById('trendProgressBar');
                        const pText = document.getElementById('trendProgressText');
                        const pPct = document.getElementById('trendProgressPercent');
                        if (pBar) pBar.style.width = '100%';
                        if (pPct) pPct.innerText = '100%';
                        if (pText) pText.innerText = '🎉 Hoàn tất toàn bộ 4 tầng! Đã cất cơ hội vào kho SQLite.';
                        el.insertAdjacentHTML('beforeend', `
                            <div class="log-phase-banner done">
                                <span class="phase-tag">HOÀN TẤT</span>
                                <span class="phase-title">🎉 TOÀN BỘ PIPELINE 4 TẦNG ĐÃ XONG! CÁC CƠ HỘI MỚI ĐÃ CẤT VÀO SQLITE</span>
                            </div>
                        `);
                        return;
                    }

                    // 2. Custom Prompt notification
                    if (trimmed.includes('[CUSTOM PROMPT]') || trimmed.includes('[PROMPT ĐỊNH HƯỚNG]') || trimmed.includes('[ĐỊNH HƯỚNG BỞI USER]')) {
                        const cleanP = trimmed.replace(/.*\[.*?\]:?/, '').replace(/["']/g, '').trim();
                        el.insertAdjacentHTML('beforeend', `
                            <div class="log-prompt-box">
                                <span>🎯</span>
                                <span><b>Định hướng chủ đề:</b> "${cleanP}"</span>
                            </div>
                        `);
                        return;
                    }

                    // 3. AI Opportunity Evaluated Row
                    const oppMatch = trimmed.match(/\[(\d+\/\d+)\]\s*'([^']+)'\s*->\s*Score:\s*([\d\.]+)\/10\s*\|\s*(.*?)\|\s*(.*)/);
                    if (oppMatch) {
                        const idx = oppMatch[1];
                        const kw = oppMatch[2];
                        const score = parseFloat(oppMatch[3]);
                        const sellText = oppMatch[4].trim();
                        const entity = oppMatch[5].trim();
                        const isSell = sellText.includes('BÁN ĐƯỢC');

                        const [cIdx, cTot] = idx.split('/').map(Number);
                        if (cTot > 0) {
                            const pct = Math.min(100, Math.round((cIdx / cTot) * 100));
                            const pBar = document.getElementById('trendProgressBar');
                            const pText = document.getElementById('trendProgressText');
                            const pPct = document.getElementById('trendProgressPercent');
                            if (pBar) pBar.style.width = pct + '%';
                            if (pPct) pPct.innerText = pct + '%';
                            if (pText) pText.innerText = `Đang phân tích cơ hội: ${cIdx} / ${cTot} từ khóa (${pct}%)`;
                        }

                        let scoreClass = 'orange';
                        if (score >= 8.0) scoreClass = 'green';
                        else if (score < 6.0) scoreClass = 'red';

                        el.insertAdjacentHTML('beforeend', `
                            <div class="log-opp-row">
                                <span class="log-idx">[#${idx}]</span>
                                <span class="log-kw">"${kw}"</span>
                                <span style="color: var(--text-dim);">➔</span>
                                <span class="log-score ${scoreClass}">⭐ ${score.toFixed(1)}/10</span>
                                <span class="log-sell-tag ${isSell ? 'sell-yes' : 'sell-no'}">${isSell ? '✓ BÁN ĐƯỢC' : '✗ KHÔNG BÁN'}</span>
                                <span class="log-entity" title="${entity}">${entity}</span>
                            </div>
                        `);
                        return;
                    }

                    // 4. Seed suggestions harvest row
                    const seedMatch = trimmed.match(/\[(\d+\/\d+)\]\s*Seed:\s*'([^']+)'\s*->\s*Thu được\s*(\d+)\s*gợi ý\s*\((\d+)\s*mới\)/);
                    if (seedMatch) {
                        el.insertAdjacentHTML('beforeend', `
                            <div class="log-seed-row">
                                <span class="seed-idx">[Seed ${seedMatch[1]}]</span>
                                <span class="seed-text">"${seedMatch[2]}"</span>
                                <span style="color: var(--text-dim);">➔</span>
                                <span class="seed-badge">+${seedMatch[4]} từ khóa mới</span>
                            </div>
                        `);
                        return;
                    }

                    // 5. Pre-filtering stats
                    if (trimmed.includes('Số từ khóa vượt qua vòng lọc') || trimmed.includes('Số từ khóa bị loại bỏ')) {
                        el.insertAdjacentHTML('beforeend', `
                            <div style="background: rgba(168, 85, 247, 0.08); padding: 5px 10px; border-radius: 6px; font-size: 11.5px; color: #d8b4fe;">
                                ${trimmed}
                            </div>
                        `);
                        return;
                    }

                    // 6. Generic system line
                    el.insertAdjacentHTML('beforeend', `
                        <div class="log-line">
                            <span class="log-time">${time}</span>
                            <span>${trimmed}</span>
                        </div>
                    `);
                });

                el.scrollTop = el.scrollHeight;
            } catch (err) {
                console.error('Error in appendLog:', err);
            }
        }

        function clearConsole() {
            document.getElementById('consoleBody').innerHTML = `
                <div class="log-phase-banner t3">
                    <span class="phase-tag">CLEARED</span>
                    <span class="phase-title">=== ĐÃ LÀM SẠCH NHẬT KÝ THỜI GIAN THỰC ===</span>
                </div>
            `;
        }

        function togglePassword(id) {
            const input = document.getElementById(id);
            input.type = input.type === 'password' ? 'text' : 'password';
        }

        async function refreshStats() {
            try {
                if (!isApiReady()) return;
                const res = await window.pywebview.api.get_stats(activeSessionId);
                if (res) {
                    document.getElementById('mRaw').innerText = (res.total_raw_keywords || 0).toLocaleString();
                    document.getElementById('mFiltered').innerText = ((res.total_raw_keywords || 0) - (res.filtered_out || 0)).toLocaleString();
                    document.getElementById('mAnalyzed').innerText = (res.analyzed_opportunities || 0).toLocaleString();
                    document.getElementById('mGems').innerText = (res.sweet_spot_gems || 0).toLocaleString();
                }
            } catch (e) {
                console.error('Error refreshStats:', e);
            }
        }

        async function loadSettings() {
            try {
                if (!isApiReady()) return;
                const cfg = await window.pywebview.api.get_settings();
                if (cfg) {
                    document.getElementById('inputGeminiKey').value = cfg.gemini_key || '';
                    document.getElementById('selectModel').value = cfg.gemini_model || 'gemini-3.8-flash';
                    document.getElementById('inputSerperKey').value = cfg.serper_key || '';
                    document.getElementById('dbPathHint').innerText = 'Vị trí SQLite: ' + (cfg.db_path || 'product_opportunities.db');

                    const badge = document.getElementById('statusBadge');
                    const txt = document.getElementById('statusText');
                    if (cfg.gemini_key) {
                        badge.className = 'nav-status';
                        txt.innerText = 'Gemini 3.8 Flash: Sẵn Sàng';
                    } else {
                        badge.className = 'nav-status dry';
                        txt.innerText = 'Chế độ Dry-Run (Chưa nhập key)';
                    }
                }
            } catch (e) {
                console.error('Error loadSettings:', e);
            }
        }

        async function waitForApi(maxMs = 5000) {
            if (isApiReady()) return true;
            const start = Date.now();
            while (Date.now() - start < maxMs) {
                if (isApiReady()) return true;
                await new Promise(r => setTimeout(r, 100));
            }
            return isApiReady();
        }

        async function saveSettings() {
            const btn = document.getElementById('btnSaveSettings');
            try {
                if (btn) btn.innerText = '⏳ Đang lưu...';
                const ready = await waitForApi(5000);
                if (!ready) {
                    alert('Hệ thống nền chưa kết nối xong với WebView2. Vui lòng bấm thử lại!');
                    return;
                }
                const key = document.getElementById('inputGeminiKey').value.trim();
                const model = document.getElementById('selectModel').value;
                const serper = document.getElementById('inputSerperKey').value.trim();

                await window.pywebview.api.save_settings(key, model, serper);
                alert('✅ Đã lưu cấu hình vĩnh viễn vào User AppData thành công!');
                loadSettings();
            } catch (e) {
                alert('❌ Lỗi lưu cài đặt: ' + e);
            } finally {
                if (btn) btn.innerText = '💾 Lưu Cài Đặt (Vĩnh Viễn)';
            }
        }

        async function testSerperKey() {
            const btn = document.getElementById('btnTestSerper');
            const serper = document.getElementById('inputSerperKey').value.trim();

            if (!serper) {
                alert('Vui lòng nhập Serper.dev API Key trước khi kiểm tra!');
                document.getElementById('inputSerperKey').focus();
                return;
            }

            try {
                if (btn) {
                    btn.disabled = true;
                    btn.innerText = '⏳ Đang test...';
                }
                const ready = await waitForApi(5000);
                if (!ready) {
                    alert('Hệ thống nền chưa kết nối xong với WebView2. Vui lòng bấm thử lại!');
                    return;
                }

                const res = await window.pywebview.api.test_serper_connection(serper);
                if (res.success) {
                    alert('✅ ' + res.message);
                } else {
                    alert('❌ ' + res.message);
                }
            } catch (err) {
                alert('❌ Lỗi khi kiểm tra Serper: ' + err);
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.innerText = '⚡ Test Serper';
                }
            }
        }

        async function testGeminiKey() {
            const btn = document.getElementById('btnTestKey');
            const key = document.getElementById('inputGeminiKey').value.trim();
            const model = document.getElementById('selectModel').value;

            if (!key) {
                alert('Vui lòng nhập Google Gemini API Key vào ô trước khi kiểm tra!');
                document.getElementById('inputGeminiKey').focus();
                return;
            }

            try {
                if (btn) {
                    btn.disabled = true;
                    btn.innerText = '⏳ Đang test...';
                }
                const ready = await waitForApi(5000);
                if (!ready) {
                    alert('Hệ thống nền chưa kết nối xong với WebView2. Vui lòng bấm thử lại!');
                    return;
                }

                const res = await window.pywebview.api.test_gemini_connection(key, model);
                if (res.success) {
                    alert('✅ ' + res.message);
                    const badge = document.getElementById('statusBadge');
                    const txt = document.getElementById('statusText');
                    if (badge) badge.className = 'nav-status';
                    if (txt) txt.innerText = `${model}: Sẵn Sàng`;
                } else {
                    alert('❌ ' + res.message);
                    const badge = document.getElementById('statusBadge');
                    const txt = document.getElementById('statusText');
                    if (badge) badge.className = 'nav-status dry';
                    if (txt) txt.innerText = 'Lỗi kết nối Gemini API';
                }
            } catch (err) {
                alert('❌ Lỗi khi kiểm tra: ' + err);
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.innerText = '⚡ Test Gemini';
                }
            }
        }

        // LOAD TOPIC / SESSIONS VÀO DROPDOWN
        async function loadTopics() {
            try {
                if (!isApiReady()) return;
                const topics = await window.pywebview.api.get_topics();
                const dropdown = document.getElementById('selectTopicFilter');
                if (!dropdown) return;
                dropdown.innerHTML = '<option value="all">💎 Tất cả chủ đề (Toàn bộ kho dữ liệu)</option>';

                if (Array.isArray(topics)) {
                    topics.forEach((t, idx) => {
                        const opt = document.createElement('option');
                        opt.value = t.session_id;
                        const isNewest = idx === 0 ? ' [Mới nhất]' : '';
                        opt.innerText = `🎯${isNewest} ${t.topic_name} (${t.total_items} cơ hội)`;
                        dropdown.appendChild(opt);
                    });
                }

                if (activeSessionId && activeSessionId !== 'all') {
                    dropdown.value = activeSessionId;
                }
            } catch (e) {
                console.error('Error loadTopics:', e);
            }
        }

        async function loadOpportunities() {
            try {
                if (!isApiReady()) return;
                const minScore = parseFloat(document.getElementById('sliderScore').value);
                const query = document.getElementById('searchInput').value.trim();
                const selectVal = document.getElementById('selectTopicFilter').value;
                activeSessionId = selectVal;

                const intentEl = document.getElementById('selectIntentFilter');
                const intentVal = intentEl ? intentEl.value : 'all';

                const items = await window.pywebview.api.get_opportunities(minScore, query, selectVal, intentVal);
                currentOpportunitiesList = items || [];
                const container = document.getElementById('cardsList');
                if (!container) return;
                container.innerHTML = '';

                if (!items || items.length === 0) {
                    container.innerHTML = `
                        <div style="text-align: center; padding: 50px 20px; color: var(--text-muted); background: var(--bg-card); border-radius: 12px; border: 1px dashed var(--border);">
                            <div style="font-size: 28px; margin-bottom: 8px;">🔍</div>
                            <div style="font-size: 14px; font-weight: 600; color: var(--text-main);">Không tìm thấy cơ hội nào thuộc bộ lọc này</div>
                            <div style="font-size: 12px; margin-top: 4px;">Hãy thử giảm mức điểm tối thiểu, chọn "Tất cả chủ đề", hoặc sang Tab 1 chạy quét đợt mới.</div>
                        </div>
                    `;
                    return;
                }

                items.forEach((it, idx) => {
                    const score = parseFloat(it.opportunity_score) || 0;
                    let scoreClass = 'orange';
                    if (score >= 8.0) scoreClass = 'green';
                    else if (score < 6.0) scoreClass = 'red';

                    const card = document.createElement('div');
                    card.className = 'opp-card';
                    card.innerHTML = `
                        <div class="opp-card-header">
                            <div class="opp-title-box">
                                <span class="badge-score ${scoreClass}">⭐ ${score.toFixed(1)}/10</span>
                                <span class="opp-entity-name">${it.entity_name || 'Chưa rõ tên'}</span>
                            </div>
                            <div class="opp-badges" style="display: flex; gap: 6px; align-items: center;">
                                ${it.topic ? `<span class="badge-topic">🏷️ ${it.topic}</span>` : ''}
                                <span class="badge-tag">${it.category}</span>
                                <span class="badge-tag" style="color: var(--accent-blue);">${it.search_intent}</span>
                                <button class="btn btn-secondary" style="padding: 3px 8px; font-size: 11px; margin-left: 6px;" title="Copy văn bản cơ hội này" onclick="copySingleCardText(${idx})">📋 Copy TXT</button>
                            </div>
                        </div>
                        <div class="opp-keyword">🔍 Từ khóa: "${it.keyword}"</div>
                        <div class="opp-summary">${it.ai_summary}</div>
                    `;
                    container.appendChild(card);
                });
            } catch (e) {
                console.error('Error loadOpportunities:', e);
            }
        }

        async function deleteCurrentTopic() {
            try {
                const dropdown = document.getElementById('selectTopicFilter');
                const sessId = dropdown.value;
                if (sessId === 'all') {
                    alert('Vui lòng chọn một chủ đề cụ thể trong dropdown để xóa!');
                    return;
                }

                const topicName = dropdown.options[dropdown.selectedIndex].text;
                if (confirm(`Bạn có chắc chắn muốn xóa toàn bộ từ khóa và sản phẩm thuộc đợt:\n"${topicName}"?`)) {
                    await window.pywebview.api.delete_topic(sessId);
                    activeSessionId = 'all';
                    await loadTopics();
                    await loadOpportunities();
                    refreshStats();
                    alert('Đã xóa thành công đợt quét!');
                }
            } catch (e) {
                alert('Lỗi xóa: ' + e);
            }
        }

        async function renameCurrentTopic() {
            try {
                if (!isApiReady()) return;
                const dropdown = document.getElementById('selectTopicFilter');
                const sessId = dropdown.value;
                if (!sessId || sessId === 'all') {
                    alert('Vui lòng chọn một chủ đề cụ thể trong dropdown để đổi tên!');
                    return;
                }

                const currentText = dropdown.options[dropdown.selectedIndex].text;
                // Loại bỏ icon và số cơ hội ở đuôi
                const currentName = currentText.replace(/^🎯\s*(\[Mới nhất\]\s*)?/, '').replace(/\s*\(\d+.*?\)$/, '').trim();
                const newName = prompt('Nhập tên mới cho chủ đề này:', currentName);
                if (!newName || !newName.trim() || newName.trim() === currentName) {
                    return;
                }

                const ok = await window.pywebview.api.rename_topic(sessId, newName.trim());
                if (ok) {
                    activeSessionId = sessId;
                    await loadTopics();
                    dropdown.value = sessId;
                    await loadOpportunities();
                    refreshStats();
                } else {
                    alert('Đổi tên chủ đề thất bại!');
                }
            } catch (err) {
                alert('Lỗi khi đổi tên: ' + err);
            }
        }

        async function startFullPipeline() {
            if (isRunning) return;
            isRunning = true;
            document.getElementById('runSpinner').style.display = 'inline-block';
            document.getElementById('runText').innerText = 'ĐANG CÀO TRENDS & XỬ LÝ...';
            document.getElementById('btnRunAll').disabled = true;

            const pCont = document.getElementById('trendProgressContainer');
            if (pCont) pCont.style.display = 'block';
            document.getElementById('trendProgressBar').style.width = '0%';
            document.getElementById('trendProgressPercent').innerText = '0%';
            document.getElementById('trendProgressText').innerText = 'Đang khởi động cào Google Trends...';

            const minVolume = parseInt(document.getElementById('selectMinVolume').value) || 0;
            const trendHours = parseInt(document.getElementById('selectTrendHours').value) || 168;
            const aiLimit = parseInt(document.getElementById('sliderAi').value) || 15;
            const topicMode = document.getElementById('selectTopicMode') ? document.getElementById('selectTopicMode').value : 'topic_1';

            await window.pywebview.api.start_pipeline(minVolume, trendHours, aiLimit, topicMode);

            // BẮT ĐẦU POLLING LOG TỰ ĐỘNG - 100% KHÔNG BAO GIỜ DEADLOCK
            if (logPollTimer) clearInterval(logPollTimer);
            logPollTimer = setInterval(async () => {
                try {
                    if (!window.pywebview || !window.pywebview.api) return;
                    const logs = await window.pywebview.api.pop_logs();
                    if (logs && logs.length > 0) {
                        logs.forEach(msg => appendLog(msg));
                    }
                    const status = await window.pywebview.api.check_pipeline_status();
                    if (status && !status.is_running && status.finished_info) {
                        clearInterval(logPollTimer);
                        onPipelineFinished(status.finished_info.session_id, status.finished_info.topic);
                    }
                } catch (err) {
                    console.error('Poll error:', err);
                }
            }, 200);
        }

        function onPipelineFinished(newSessionId, newTopic) {
            isRunning = false;
            document.getElementById('runSpinner').style.display = 'none';
            document.getElementById('runText').innerText = '▶ CHẠY TOÀN BỘ 4 TẦNG';
            document.getElementById('btnRunAll').disabled = false;
            activeSessionId = newSessionId;
            refreshStats();

            const el = document.getElementById('consoleBody');
            if (el) {
                el.insertAdjacentHTML('beforeend', `
                    <div class="log-switch-card">
                        <div>
                            <div style="font-weight: 700; color: var(--primary);">🎯 Đã phân tích xong chủ đề: "${newTopic}"</div>
                            <div style="font-size: 11.5px; color: var(--text-muted); margin-top: 2px;">Dữ liệu đã được lưu trữ riêng biệt, không bị lẫn với các từ khóa cũ.</div>
                        </div>
                        <button class="btn btn-primary" onclick="openAndSelectTopic('${newSessionId}')">👉 Mở Kho Cơ Hội Xem Ngay</button>
                    </div>
                `);
                el.scrollTop = el.scrollHeight;
            }
        }

        // DEEP KEYWORD SEARCH PIPELINE HANDLERS
        function setDeepSeed(term) {
            const input = document.getElementById('inputDeepKeyword');
            if (input) {
                input.value = term;
                input.focus();
            }
        }

        function clearDeepConsole() {
            const el = document.getElementById('deepConsoleBody');
            if (el) {
                el.innerHTML = `
                    <div class="log-phase-banner t1">
                        <span class="phase-tag">CLEARED</span>
                        <span class="phase-title">=== ĐÃ LÀM SẠCH NHẬT KÝ NGHIÊN CỨU TỪ KHÓA SÂU ===</span>
                    </div>
                `;
            }
        }

        async function startDeepSearchPipeline() {
            if (isRunning) return;
            const input = document.getElementById('inputDeepKeyword');
            const seed = input ? input.value.trim() : '';
            if (!seed) {
                alert('Vui lòng nhập từ khóa hạt giống cần nghiên cứu (ví dụ: "peel da" hoặc "meso mụn phan thiết")!');
                if (input) input.focus();
                return;
            }

            isRunning = true;
            document.getElementById('deepRunSpinner').style.display = 'inline-block';
            document.getElementById('deepRunText').innerText = 'ĐANG ĐÀO SÂU TỪ KHÓA...';
            document.getElementById('btnRunDeep').disabled = true;

            const location = document.getElementById('selectDeepLocation').value;
            const timeRange = document.getElementById('selectDeepTimeRange').value;
            const targetCount = parseInt(document.getElementById('selectDeepLimit').value) || 100;
            const aiLimit = parseInt(document.getElementById('sliderDeepAi').value) || 25;

            clearDeepConsole();
            const pCont = document.getElementById('deepProgressContainer');
            if (pCont) pCont.style.display = 'block';
            document.getElementById('deepProgressBar').style.width = '0%';
            document.getElementById('deepProgressPercent').innerText = '0%';
            document.getElementById('deepProgressText').innerText = 'Đang cào dữ liệu Google & Serper.dev...';

            appendDeepLog(`>>> BẮT ĐẦU PIPELINE NGHIÊN CỨU TỪ KHÓA SÂU (SERPER.DEV & AI) <<<`);
            appendDeepLog(`[TẦNG 1 - DATA MINING]: Đang cào dữ liệu Google SERP, Suggestions và Autocomplete cho "${seed}" (${location})...`);

            try {
                await window.pywebview.api.start_deep_pipeline(seed, location, timeRange, targetCount, aiLimit, "all");
            } catch (err) {
                alert('Lỗi khởi động Deep Search Pipeline: ' + err);
                isRunning = false;
                document.getElementById('deepRunSpinner').style.display = 'none';
                document.getElementById('deepRunText').innerText = '🚀 ĐÀO ~100 TỪ KHÓA & PHÂN TÍCH';
                document.getElementById('btnRunDeep').disabled = false;
                return;
            }

            if (logPollTimer) clearInterval(logPollTimer);
            logPollTimer = setInterval(async () => {
                try {
                    if (!window.pywebview || !window.pywebview.api) return;
                    const logs = await window.pywebview.api.pop_logs();
                    if (logs && logs.length > 0) {
                        logs.forEach(msg => {
                            appendLog(msg);
                            appendDeepLog(msg);
                        });
                    }
                    const status = await window.pywebview.api.check_pipeline_status();
                    if (status && !status.is_running && status.finished_info) {
                        clearInterval(logPollTimer);
                        onDeepPipelineFinished(status.finished_info.session_id, status.finished_info.topic);
                    }
                } catch (err) {
                    console.error('Deep Poll error:', err);
                }
            }, 200);
        }

        function appendDeepLog(rawText) {
            try {
                if (!rawText || typeof rawText !== 'string' || !rawText.trim()) return;
                const el = document.getElementById('deepConsoleBody');
                if (!el) return;
                const lines = rawText.split('\n');

                lines.forEach(line => {
                    const trimmed = line.trim();
                    if (!trimmed) return;

                    if (trimmed.includes('>>> BẮT ĐẦU PIPELINE NGHIÊN CỨU')) {
                        el.insertAdjacentHTML('beforeend', `
                            <div class="log-phase-banner t1">
                                <span class="phase-tag">KHỞI ĐỘNG</span>
                                <span class="phase-title">🚀 NGHIÊN CỨU TỪ KHÓA SÂU: GOOGLE SERP & REALTIME SUGGESTIONS</span>
                            </div>
                        `);
                        return;
                    }
                    if (trimmed.includes('[TẦNG 1 - DATA MINING]')) {
                        el.insertAdjacentHTML('beforeend', `
                            <div class="log-phase-banner t1">
                                <span class="phase-tag">TẦNG 1</span>
                                <span class="phase-title">🔎 DATA MINING: THU THẬP TỪ KHÓA THẬT QUA SERPER.DEV & GOOGLE AUTOCOMPLETE</span>
                            </div>
                        `);
                        return;
                    }
                    if (trimmed.includes('[TẦNG 2 & 3 - AI INTELLIGENCE]')) {
                        el.insertAdjacentHTML('beforeend', `
                            <div class="log-phase-banner t3">
                                <span class="phase-tag">TẦNG 2 & 3</span>
                                <span class="phase-title">🤖 AI INTELLIGENCE: SERPER AUDIT ĐỐI THỦ & GEMINI 3.8 FLASH BÓC TÁCH CƠ HỘI</span>
                            </div>
                        `);
                        return;
                    }
                    if (trimmed.includes('HOÀN TẤT TOÀN BỘ PIPELINE NGHIÊN CỨU TỪ KHÓA')) {
                        const pBar = document.getElementById('deepProgressBar');
                        const pText = document.getElementById('deepProgressText');
                        const pPct = document.getElementById('deepProgressPercent');
                        if (pBar) pBar.style.width = '100%';
                        if (pPct) pPct.innerText = '100%';
                        if (pText) pText.innerText = '🎉 Hoàn tất 100% nghiên cứu sâu! Dữ liệu đã cất vào Kho Cơ Hội Vàng.';
                        el.insertAdjacentHTML('beforeend', `
                            <div class="log-phase-banner done">
                                <span class="phase-tag">HOÀN TẤT</span>
                                <span class="phase-title">🎉 HOÀN THÀNH NGHIÊN CỨU SÂU! ĐÃ CẤT TẤT CẢ CƠ HỘI VÀO SQLITE & BÁO CÁO CSV</span>
                            </div>
                        `);
                        return;
                    }

                    if (trimmed.startsWith('[#') && trimmed.includes('->')) {
                        const deepMatch = trimmed.match(/\[#(\d+\/\d+)\]\s*'([^']+)'\s*->\s*⭐?\s*([\d\.]+)\/10\s*\|\s*(.*?)\|\s*(.*)/);
                        if (deepMatch) {
                            const idx = deepMatch[1];
                            const kw = deepMatch[2];
                            const score = parseFloat(deepMatch[3]) || 0;
                            const sellText = deepMatch[4].trim();
                            const entity = deepMatch[5].trim();
                            const isSell = sellText.includes('THƯƠNG MẠI') || sellText.includes('BÁN ĐƯỢC');

                            const [cIdx, cTot] = idx.split('/').map(Number);
                            if (cTot > 0) {
                                const pct = Math.min(100, Math.round((cIdx / cTot) * 100));
                                const pBar = document.getElementById('deepProgressBar');
                                const pText = document.getElementById('deepProgressText');
                                const pPct = document.getElementById('deepProgressPercent');
                                if (pBar) pBar.style.width = pct + '%';
                                if (pPct) pPct.innerText = pct + '%';
                                if (pText) pText.innerText = `Gemini AI đang bóc tách cơ hội: ${cIdx} / ${cTot} từ khóa (${pct}%)`;
                            }

                            let scoreClass = 'orange';
                            if (score >= 8.0) scoreClass = 'green';
                            else if (score < 6.0) scoreClass = 'red';

                            el.insertAdjacentHTML('beforeend', `
                                <div class="log-opp-row">
                                    <span class="log-idx">[#${idx}]</span>
                                    <span class="log-kw">"${kw}"</span>
                                    <span style="color: var(--text-dim);">➔</span>
                                    <span class="log-score ${scoreClass}">⭐ ${score.toFixed(1)}/10</span>
                                    <span class="log-sell-tag ${isSell ? 'sell-yes' : 'sell-no'}">${sellText}</span>
                                    <span class="log-entity" title="${entity}">${entity}</span>
                                </div>
                            `);
                            return;
                        } else {
                            const scoreMatch = trimmed.match(/⭐\s*([\d.]+)\/10/);
                            const score = scoreMatch ? parseFloat(scoreMatch[1]) : 7.0;
                            let scoreClass = 'orange';
                            if (score >= 8.0) scoreClass = 'green';
                            else if (score < 6.0) scoreClass = 'red';

                            el.insertAdjacentHTML('beforeend', `
                                <div class="log-opp-row">
                                    <span class="log-kw">${trimmed}</span>
                                    <span class="log-score ${scoreClass}" style="margin-left: auto;">⭐ ${score.toFixed(1)}/10</span>
                                </div>
                            `);
                            return;
                        }
                    }

                    el.insertAdjacentHTML('beforeend', `
                        <div class="log-line">
                            <span class="log-time">${getTimeStr()}</span>
                            <span>${trimmed}</span>
                        </div>
                    `);
                });

                el.scrollTop = el.scrollHeight;
            } catch (err) {
                console.error('appendDeepLog error:', err);
            }
        }

        function onDeepPipelineFinished(newSessionId, newTopic) {
            isRunning = false;
            document.getElementById('deepRunSpinner').style.display = 'none';
            document.getElementById('deepRunText').innerText = '🚀 ĐÀO ~100 TỪ KHÓA & PHÂN TÍCH';
            document.getElementById('btnRunDeep').disabled = false;
            activeSessionId = newSessionId;
            refreshStats();

            const el = document.getElementById('deepConsoleBody');
            if (el) {
                el.insertAdjacentHTML('beforeend', `
                    <div class="log-switch-card">
                        <div>
                            <div style="font-weight: 800; color: var(--primary); font-size: 13.5px;">✅ Đã hoàn tất nghiên cứu: "${newTopic}"</div>
                            <div style="font-size: 11.5px; color: var(--text-muted); margin-top: 2px;">Dữ liệu ~100 từ khóa thật đã được phân tích và lưu riêng vào Kho Cơ Hội Vàng.</div>
                        </div>
                        <button class="btn btn-primary" onclick="openAndSelectTopic('${newSessionId}')">💎 Mở Kho Cơ Hội Xem Ngay</button>
                    </div>
                `);
                el.scrollTop = el.scrollHeight;
            }
        }

        async function openAndSelectTopic(sessionId) {
            switchTab('database');
            await loadTopics();
            const dropdown = document.getElementById('selectTopicFilter');
            if (dropdown && sessionId) {
                dropdown.value = sessionId;
            }
            await loadOpportunities();
        }

        // XUẤT CSV VÀ HIỂN THỊ MODAL ĐƯỜNG DẪN RÕ RÀNG
        async function exportCsv() {
            try {
                const dropdown = document.getElementById('selectTopicFilter');
                const sessId = dropdown ? dropdown.value : activeSessionId;
                let topicName = '';
                if (dropdown && dropdown.selectedIndex >= 0 && sessId !== 'all') {
                    topicName = dropdown.options[dropdown.selectedIndex].text.replace(/^[🎯💎\s]+/, '').split('(')[0].trim();
                }

                const res = await window.pywebview.api.export_csv(sessId, topicName);
                latestExportedPath = res.filepath;
                latestExportedFolder = res.folder;

                document.getElementById('exportFolderText').innerText = res.folder;
                document.getElementById('exportFileText').innerText = `${res.filename} (${res.count} cơ hội sản phẩm)`;
                document.getElementById('exportModal').classList.add('show');
            } catch (e) {
                alert('Lỗi xuất file: ' + e);
            }
        }

        function closeExportModal() {
            document.getElementById('exportModal').classList.remove('show');
        }

        async function openExportFolder() {
            if (latestExportedFolder) {
                await window.pywebview.api.open_folder(latestExportedFolder);
            }
        }

        async function openExportedFile() {
            if (latestExportedPath) {
                await window.pywebview.api.open_file(latestExportedPath);
            }
        }

        async function openDatabaseFolder() {
            await window.pywebview.api.open_folder();
        }

        async function resetDatabase() {
            if (confirm('Bạn có chắc chắn muốn xóa toàn bộ từ khóa và sản phẩm trong SQLite?')) {
                await window.pywebview.api.reset_db();
                activeSessionId = 'all';
                await loadTopics();
                refreshStats();
                loadOpportunities();
                alert('Đã làm sạch database!');
            }
        }

        let isAppInitialized = false;

        async function initApp() {
            if (isAppInitialized || !isApiReady()) return;
            isAppInitialized = true;
            try {
                await loadSettings();
                await refreshStats();
            } catch (e) {
                console.error('Lỗi khi nạp dữ liệu ban đầu:', e);
            }
        }

        function startApp() {
            if (isApiReady()) {
                initApp();
            } else {
                window.addEventListener('pywebviewready', () => {
                    initApp();
                });
                let count = 0;
                const poll = setInterval(() => {
                    count++;
                    if (isApiReady()) {
                        clearInterval(poll);
                        initApp();
                    } else if (count > 50) {
                        clearInterval(poll);
                    }
                }, 80);
            }
        }

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', startApp);
        } else {
            startApp();
        }
    </script>
</body>
</html>
"""

class WebviewAPI:
    """Cầu nối Python cung cấp cho JavaScript gọi trực tiếp qua Webview2."""
    def __init__(self):
        self._window = None
        self._is_pipeline_running = False
        self._finished_info = None

    def get_stats(self, session_id="all"):
        return get_stats(session_id=session_id)

    def get_topics(self):
        return get_all_topics()

    def delete_topic(self, session_id):
        return delete_session(session_id)

    def get_settings(self):
        return {
            "gemini_key": getattr(config, "GEMINI_API_KEY", ""),
            "gemini_model": getattr(config, "GEMINI_MODEL", "gemini-3.8-flash"),
            "serper_key": getattr(config, "SERPER_API_KEY", ""),
            "db_path": getattr(config, "DATABASE_PATH", "product_opportunities.db")
        }

    def save_settings(self, gemini_key, gemini_model, serper_key):
        config.save_env_config(
            gemini_key=gemini_key,
            gemini_model=gemini_model,
            serper_key=serper_key
        )
        return True

    def test_serper_connection(self, api_key=""):
        try:
            from pipeline.serp_fetcher import test_serper_connection
            return test_serper_connection(api_key)
        except Exception as e:
            return {"success": False, "message": f"Lỗi kiểm tra Serper: {e}"}

    def test_gemini_connection(self, api_key="", model=""):
        active_key = (api_key or config.GEMINI_API_KEY).strip()
        active_model = (model or config.GEMINI_MODEL or "gemini-3.8-flash").strip()
        if not active_key:
            return {"success": False, "message": "Vui lòng nhập Google Gemini API Key trước khi kiểm tra!"}
        try:
            from google import genai
            client = genai.Client(api_key=active_key)
            res = client.models.generate_content(
                model=active_model,
                contents="Hello, reply with 'OK' only."
            )
            reply = res.text.strip() if res and res.text else "OK"
            return {
                "success": True,
                "model": active_model,
                "message": f"Kết nối Gemini API thành công! Mô hình '{active_model}' hoạt động tốt."
            }
        except Exception as e:
            err_msg = str(e)
            if "API key not valid" in err_msg:
                err_msg = "API Key không hợp lệ. Vui lòng kiểm tra lại trên Google AI Studio!"
            elif "RESOURCE_EXHAUSTED" in err_msg:
                err_msg = "Khóa API đã hết hạn mức (Quota Exceeded). Vui lòng đổi model hoặc thử key khác!"
            return {
                "success": False,
                "model": active_model,
                "message": f"Lỗi kết nối Gemini API: {err_msg}"
            }

    def get_opportunities(self, min_score=6.0, search_query="", session_id="all", search_intent="all"):
        return get_top_opportunities(
            min_score=min_score,
            limit=500,
            session_id=session_id,
            search_query=search_query,
            search_intent=search_intent
        )

    def pop_logs(self):
        return app_logger.pop_all()

    def check_pipeline_status(self):
        return {
            "is_running": self._is_pipeline_running,
            "finished_info": self._finished_info
        }

    def export_csv(self, session_id="all", topic_name=""):
        res = export_to_csv(session_id=session_id, topic_name=topic_name)
        try:
            import subprocess
            subprocess.Popen(f'explorer.exe /select,"{res["filepath"]}"')
        except Exception:
            pass
        return res

    def open_folder(self, folder_path=None):
        import subprocess
        target = folder_path or str(Path(config.BASE_DIR) / "Bao_Cao_Xuat")
        Path(target).mkdir(parents=True, exist_ok=True)
        subprocess.Popen(f'explorer.exe "{target}"')
        return True

    def open_file(self, file_path):
        try:
            os.startfile(file_path)
        except Exception:
            import subprocess
            subprocess.Popen(f'notepad.exe "{file_path}"')
        return True

    def reset_db(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM raw_keywords;")
        cursor.execute("DELETE FROM product_opportunities;")
        conn.commit()
        conn.close()
        return True

    def start_pipeline(self, min_volume=1000, trend_hours=168, ai_limit=15, topic_mode="topic_1"):
        session_id = datetime.datetime.now().strftime("sess_%Y%m%d_%H%M%S")
        topic_short = "Đồ Điện Tử Gia Dụng" if topic_mode == "topic_2" else "Da Liễu & Dược Mỹ Phẩm"
        topic = f"{topic_short} (Vol >= {int(min_volume):,} | {trend_hours}h)"

        self._is_pipeline_running = True
        self._finished_info = None

        def worker():
            class StdoutInterceptor:
                def write(self, s):
                    s_clean = s.rstrip()
                    if s_clean:
                        app_logger.log(s_clean)
                def flush(self):
                    pass

            old_out = sys.stdout
            sys.stdout = StdoutInterceptor()

            try:
                print("\n" + "=" * 60)
                print(f">>> BẮT ĐẦU CHẠY PIPELINE 4 TẦNG TỰ ĐỘNG - {topic_short.upper()} <<<")
                print(f"🔥 [NGUỒN GOOGLE TRENDS VN]: Lọc Volume >= {int(min_volume):,} | {trend_hours} giờ qua")
                print(f"📁 [CHỦ ĐỀ ĐỢT QUÉT]: {topic}")
                print("=" * 60 + "\n")
                
                # Tầng 1: Cào Google Trends VN + Deep Suggest Matrix
                harvest_all_raw_keywords(
                    min_volume=int(min_volume),
                    trend_hours=int(trend_hours),
                    topic_mode=topic_mode,
                    session_id=session_id,
                    topic=topic
                )
                # Tầng 2: Serper.dev thẩm định & Lọc theo ngành hàng đã chọn
                run_pre_filtering(session_id=session_id, topic_mode=topic_mode)
                # Tầng 3: Gemini 3.8 Flash R&D & Chấm điểm cơ hội
                run_gemini_analysis_batch(
                    limit=int(ai_limit),
                    api_key=config.GEMINI_API_KEY,
                    topic_mode=topic_mode,
                    session_id=session_id,
                    topic=topic
                )
                # Tầng 4: Lưu SQLite & Xuất CSV
                export_to_csv(session_id=session_id, topic_name=topic)
                print("\n[✓] HOÀN TẤT TOÀN BỘ PIPELINE 4 TẦNG THÀNH CÔNG!\n")
            except Exception as e:
                print(f"\n[!] LỖI THỰC THI: {e}\n")
            finally:
                sys.stdout = old_out
                self._is_pipeline_running = False
                self._finished_info = {"session_id": session_id, "topic": topic}

        threading.Thread(target=worker, daemon=True).start()
        return True

    def rename_topic(self, session_id, new_name):
        return rename_topic(session_id, new_name)

    def start_deep_pipeline(self, seed_keyword, location="Vietnam", time_range="", target_count=100, ai_limit=25, traffic_priority="all"):
        session_id = datetime.datetime.now().strftime("deep_%Y%m%d_%H%M%S")
        self._is_pipeline_running = True
        self._finished_info = None

        def worker():
            class StdoutInterceptor:
                def write(self, s):
                    s_clean = s.rstrip()
                    if s_clean:
                        app_logger.log(s_clean)
                def flush(self):
                    pass

            old_out = sys.stdout
            sys.stdout = StdoutInterceptor()

            try:
                res = run_deep_keyword_pipeline(
                    seed_keyword=seed_keyword,
                    location=location,
                    time_range=time_range,
                    target_count=int(target_count),
                    ai_limit=int(ai_limit),
                    traffic_priority=traffic_priority,
                    session_id=session_id
                )
                self._finished_info = {"session_id": session_id, "topic": res.get("topic", seed_keyword)}
            except Exception as e:
                print(f"\n[!] LỖI THỰC THI DEEP PIPELINE: {e}\n")
                self._finished_info = {"session_id": session_id, "topic": seed_keyword}
            finally:
                sys.stdout = old_out
                self._is_pipeline_running = False

        threading.Thread(target=worker, daemon=True).start()
        return True

def main():
    init_db()

    api = WebviewAPI()

    window = webview.create_window(
        title="Derm Keyword Hunter - Desktop Pro (Gemini 3.8 Flash & SQLite)",
        html=APP_HTML,
        width=1240,
        height=830,
        min_size=(980, 660),
        resizable=True,
        js_api=api
    )
    api._window = window

    webview.start()

if __name__ == "__main__":
    main()
