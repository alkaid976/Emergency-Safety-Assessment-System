import platform
import sys
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import threading
import time
import datetime
import requests
import base64
import io
import os
import difflib

try:
    import cv2 as cv
    import numpy as np

    OPENCV_AVAILABLE = True
except ImportError:
    cv = None
    np = None
    OPENCV_AVAILABLE = False
    print("警告: 未安装OpenCV，将无法处理视频")
from PIL import Image, ImageTk
import webbrowser
import subprocess

# =========================================================================
#                                 配置区域
# =========================================================================

# --- API 设置 ---
OCR_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
OCR_MODEL_ID = "glm-4.6v-flash"

VLM_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
VLM_MODEL_ID = "glm-4.6v-flash"

# 这里需要设置您的API密钥
# 获取方式：访问 https://open.bigmodel.cn/ 注册并创建API密钥
API_KEY = "4cfe13a13d6143cf83bde33ec0355302.30RHJZUpDG1dIkvK"  # 请在此处填入您的API密钥

# --- 运行参数 ---
FRAME_INTERVAL = 2.5  # 采样间隔 (秒)
BATCH_SIZE = 4  # 4帧拼接 (约10秒)
SUMMARY_TRIGGER_BATCHES = 6  # 6次批处理后触发阶段回顾 (约60秒)

# --- 自适应分辨率 ---
OCR_TARGET_WIDTH = 1024
VLM_MAX_DIMENSION = 1560

# =========================================================================
#                         消防演习动作判断提示词
# =========================================================================

PROMPT_OCR = (
    "你是一个专门的字幕读取程序。这张图片是同一位置、不同时间的字幕区域截图，被纵向拼接在一起。\n"
    "【去重任务】\n"
    "1. 合并重复项：如果连续多行文字内容相同（或仅有微小OCR误差），请只输出一次。\n"
    "2. 忽略无效内容：不输出水印、台标、纯符号或非中文内容。\n"
    "3. 输出格式：直接输出净化后的中文字幕文本，忽略日语和英语,不要加任何序号或前缀。如果全图无中文内容，回复\"无\"。"
)

PROMPT_ACTION_ANALYSIS = (
    "你是专业的消防演习评估专家。正在分析一段约10秒的消防演习视频片段。\n"
    "【历史上下文（前20秒）】：\n{history}\n\n"
    "【当前输入】：\n"
    "1. 图片：由4个连续时刻画面按2x2拼接而成，显示消防演习的连续动作。\n"
    "2. 字幕文本（如有指令或口令）：\n{subtitles}\n\n"
    "【评估要求】：\n"
    "1. 动作识别：描述画面中人员在做什么（如：使用灭火器、连接消防水带、疏散人员、佩戴呼吸器等）。\n"
    "2. 正确性判断：根据消防演习标准，判断每个动作是否正确。\n"
    "3. 错误纠正：如果动作不正确，明确指出错误点并提供正确的操作步骤。\n"
    "4. 安全评估：检查是否存在安全隐患（如：站位不当、防护缺失、操作顺序错误等）。\n"
    "5. 输出格式：\n"
    "   ✅ 正确动作：[描述正确执行的动作]\n"
    "   ❌ 错误动作：[描述错误点]\n"
    "   💡 纠正建议：[具体纠正步骤]\n"
    "   ⚠️ 安全隐患：[如有，列出]\n"
    "6. 字数限制：200字以内。"
)

PROMPT_PHASE_SUMMARY = (
    "你是消防演习总教官。请对最近1分钟的消防演习进行回顾评估。\n"
    "【整体训练进度（所有已评估阶段）】：\n{past_summaries}\n\n"
    "【最近1分钟的详细评估记录】：\n{recent_logs}\n\n"
    "【任务】：\n"
    "1. 技能掌握度：评估受训人员对当前训练项目的掌握程度。\n"
    "2. 常见错误：总结本阶段出现的主要错误类型和频率。\n"
    "3. 进步情况：与前阶段相比，是否有改进。\n"
    "4. 训练建议：针对薄弱环节，提出下一阶段的训练重点。\n"
    "5. 输出格式：\n"
    "   📊 掌握程度：[百分比评估]\n"
    "   🔄 主要问题：[列出1-3个]\n"
    "   📈 改进建议：[具体训练建议]\n"
    "6. 字数限制：300字以内。"
)

PROMPT_FINAL_SUMMARY = (
    "你是消防演习评估专家。整个消防演习已结束，请根据所有阶段记录，撰写最终评估报告。\n"
    "【要求】\n"
    "1. 整体评价：对演习整体表现进行评分（百分制）。\n"
    "2. 优点总结：列出表现良好的方面。\n"
    "3. 问题分析：系统性地总结存在的各类问题。\n"
    "4. 改进方案：针对每个问题提供具体的改进建议。\n"
    "5. 训练建议：制定后续训练计划。\n"
    "6. 输出格式：\n"
    "   🎯 综合评分：[分数]/100\n"
    "   ✅ 表现亮点：[分点列出]\n"
    "   ❌ 存在问题：[分点列出]\n"
    "   💪 改进建议：[分点列出]\n"
    "   📅 训练计划：[具体计划]\n"
    "7. 字数限制：800字左右。"
)

# 常见消防动作标准库
FIRE_DRILL_STANDARDS = {
    "灭火器使用": {
        "正确步骤": ["检查压力表", "拔掉安全销", "对准火焰根部", "保持安全距离", "喷射时左右摆动"],
        "常见错误": ["未检查压力", "风向站位错误", "距离过近", "未对准根部", "喷射时间过短"]
    },
    "消防水带连接": {
        "正确步骤": ["展开水带", "连接消火栓", "连接水枪头", "确认牢固", "缓慢打开阀门"],
        "常见错误": ["水带扭曲", "连接不牢", "阀门开太快", "水带打结", "接口漏水"]
    },
    "疏散引导": {
        "正确步骤": ["保持冷静", "指示方向", "防止踩踏", "检查房间", "清点人数"],
        "常见错误": ["自己先慌", "指示不清", "遗漏人员", "堵塞通道", "返回危险区"]
    },
    "呼吸器佩戴": {
        "正确步骤": ["检查气瓶", "背上装备", "戴上面罩", "检查气密性", "打开气阀"],
        "常见错误": ["面罩漏气", "气瓶未开", "佩戴过慢", "未检查压力", "气管扭曲"]
    }
}

# 样式配置
STYLES = {
    "primary_color": "#2c3e50",  # 深蓝色
    "secondary_color": "#3498db",  # 亮蓝色
    "success_color": "#27ae60",  # 绿色
    "danger_color": "#e74c3c",  # 红色
    "warning_color": "#f39c12",  # 黄色
    "info_color": "#3498db",  # 信息蓝
    "light_bg": "#ecf0f1",  # 浅灰背景
    "dark_bg": "#2c3e50",  # 深色背景
    "text_light": "#ffffff",  # 白色文字
    "text_dark": "#2c3e50",  # 深色文字
}


# =========================================================================
#                                 主程序逻辑
# =========================================================================

class SubtitleDeduplicator:
    def __init__(self, max_history=10):
        self.history = []
        self.max_history = max_history

    def process(self, raw_text):
        if not raw_text or "无" in raw_text:
            return ""
        lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
        unique_lines = []
        for line in lines:
            if len(line) < 2:
                continue
            is_dup = False
            for old in self.history:
                if difflib.SequenceMatcher(None, line, old).ratio() > 0.85:
                    is_dup = True
                    break
            if not is_dup:
                unique_lines.append(line)
                self.history.append(line)
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
        return " ".join(unique_lines)


class FireDrillAnalyzerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🚒 消防演习智能评估系统 V4.0")
        self.root.geometry("1600x1000")

        # 先初始化关键属性
        self.txt_stream = None
        self.txt_summary = None
        self.final_report_text = ""

        # 设置窗口图标
        self.set_window_icon()

        # 设置样式
        self.setup_styles()

        # 窗口居中
        self.center_window()

        self.is_running = False
        self.video_path = None
        self.cap = None
        self.fps = 0
        self.total_frames = 0
        self.video_duration = 0
        self.video_info = tk.StringVar(value="📁 未选择视频文件")
        self.status_text = tk.StringVar(value="✅ 就绪")
        self.log_filename = ""

        # 进度相关变量
        self.progress_var = tk.DoubleVar(value=0.0)
        self.buffer_var = tk.DoubleVar(value=0.0)

        # 分析数据
        self.frame_buffer = []
        self.subtitle_buffer = []
        self.analysis_logs = []
        self.phase_summaries = []
        self.deduplicator = SubtitleDeduplicator()

        # 统计变量
        self.correct_actions = 0
        self.incorrect_actions = 0
        self.total_actions = 0
        self.processed_frames = 0

        self.setup_ui()

    def setup_styles(self):
        """设置自定义样式"""
        style = ttk.Style()

        # 设置主题
        style.theme_use('clam')

        # 配置颜色
        style.configure("TFrame", background=STYLES["light_bg"])
        style.configure("TLabel", background=STYLES["light_bg"], font=("Microsoft YaHei", 10))
        style.configure("Header.TLabel", font=("Microsoft YaHei", 14, "bold"),
                        foreground=STYLES["primary_color"])
        style.configure("Status.TLabel", font=("Consolas", 10),
                        foreground=STYLES["dark_bg"])

        # 按钮样式
        style.configure("Primary.TButton", font=("Microsoft YaHei", 10, "bold"),
                        background=STYLES["secondary_color"], foreground=STYLES["text_light"])
        style.map("Primary.TButton",
                  background=[('active', STYLES["primary_color"])])

        style.configure("Success.TButton", font=("Microsoft YaHei", 10, "bold"),
                        background=STYLES["success_color"], foreground=STYLES["text_light"])

        style.configure("Danger.TButton", font=("Microsoft YaHei", 10, "bold"),
                        background=STYLES["danger_color"], foreground=STYLES["text_light"])

        style.configure("Warning.TButton", font=("Microsoft YaHei", 10, "bold"),
                        background=STYLES["warning_color"], foreground=STYLES["text_light"])

    def set_window_icon(self):
        """设置窗口图标（如果可用）"""
        try:
            # 尝试加载图标文件
            self.root.iconbitmap('fire_icon.ico')
        except:
            pass  # 如果没有图标文件，继续

    def center_window(self):
        """窗口居中显示"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')

    def setup_ui(self):
        # 主容器
        main_container = ttk.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # 标题栏
        header_frame = ttk.Frame(main_container)
        header_frame.pack(fill=tk.X, pady=(0, 20))

        ttk.Label(header_frame, text="🚒 消防演习智能评估系统 V4.0",
                  style="Header.TLabel").pack(side=tk.LEFT)

        # 工具栏
        toolbar = ttk.Frame(main_container)
        toolbar.pack(fill=tk.X, pady=(0, 20))

        # 按钮组
        button_frame = ttk.Frame(toolbar)
        button_frame.pack(side=tk.LEFT)

        ttk.Button(button_frame, text="📁 上传视频", command=self.upload_video,
                   style="Primary.TButton", width=15).pack(side=tk.LEFT, padx=5)

        self.btn_start = ttk.Button(button_frame, text="▶ 开始分析", command=self.start_analysis,
                                    state=tk.DISABLED, style="Success.TButton", width=15)
        self.btn_start.pack(side=tk.LEFT, padx=5)

        self.btn_stop = ttk.Button(button_frame, text="■ 停止分析", command=self.stop_analysis,
                                   state=tk.DISABLED, style="Danger.TButton", width=15)
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        ttk.Button(button_frame, text="📂 打开报告", command=self.open_report_folder,
                   style="Primary.TButton", width=15).pack(side=tk.LEFT, padx=5)

        # 视频信息
        info_frame = ttk.Frame(toolbar)
        info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=20)

        ttk.Label(info_frame, textvariable=self.video_info,
                  foreground=STYLES["secondary_color"], font=("Microsoft YaHei", 10, "bold")).pack()

        # 统计信息
        stats_frame = ttk.Frame(toolbar)
        stats_frame.pack(side=tk.RIGHT)

        self.lbl_stats = ttk.Label(stats_frame,
                                   text="✅ 正确: 0  ❌ 错误: 0  📊 总计: 0",
                                   foreground=STYLES["success_color"],
                                   font=("Microsoft YaHei", 10, "bold"))
        self.lbl_stats.pack()

        # 主内容区域
        content_pane = ttk.PanedWindow(main_container, orient=tk.HORIZONTAL)
        content_pane.pack(fill=tk.BOTH, expand=True)

        # 左侧面板 (40%)
        left_panel = ttk.Frame(content_pane)
        content_pane.add(left_panel, weight=4)

        # 视频预览区域
        preview_group = ttk.LabelFrame(left_panel, text="🎬 视频预览", padding=10)
        preview_group.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.video_canvas = tk.Canvas(preview_group, bg=STYLES["dark_bg"],
                                      highlightthickness=0, relief='sunken')
        self.video_canvas.pack(fill=tk.BOTH, expand=True)
        self.video_canvas.create_text(200, 150, text="视频预览区域",
                                      fill="#7f8c8d", font=("Microsoft YaHei", 12))

        # 进度区域
        progress_frame = ttk.LabelFrame(left_panel, text="📈 分析进度", padding=10)
        progress_frame.pack(fill=tk.X, pady=(0, 10))

        # 总体进度
        progress_row1 = ttk.Frame(progress_frame)
        progress_row1.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(progress_row1, text="总体进度:", width=10).pack(side=tk.LEFT)
        self.progress_bar = ttk.Progressbar(progress_row1, variable=self.progress_var,
                                            maximum=100, mode='determinate')
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))

        self.lbl_progress = ttk.Label(progress_row1, text="0%", width=6)
        self.lbl_progress.pack(side=tk.LEFT, padx=(10, 0))

        # 批处理进度
        progress_row2 = ttk.Frame(progress_frame)
        progress_row2.pack(fill=tk.X)

        ttk.Label(progress_row2, text="批处理:", width=10).pack(side=tk.LEFT)
        self.batch_bar = ttk.Progressbar(progress_row2, variable=self.buffer_var,
                                         maximum=BATCH_SIZE, mode='determinate')
        self.batch_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))

        self.lbl_batch = ttk.Label(progress_row2, text=f"0/{BATCH_SIZE}", width=6)
        self.lbl_batch.pack(side=tk.LEFT, padx=(10, 0))

        # 消防标准库
        standards_group = ttk.LabelFrame(left_panel, text="📋 消防动作标准", padding=10)
        standards_group.pack(fill=tk.BOTH, expand=True)

        # 创建Notebook标签页
        standards_notebook = ttk.Notebook(standards_group)
        standards_notebook.pack(fill=tk.BOTH, expand=True)

        for action, steps in FIRE_DRILL_STANDARDS.items():
            frame = ttk.Frame(standards_notebook)
            standards_notebook.add(frame, text=action)

            # 正确步骤
            correct_frame = ttk.LabelFrame(frame, text="✅ 正确步骤", padding=5)
            correct_frame.pack(fill=tk.X, pady=(0, 10), padx=5)

            for i, step in enumerate(steps["正确步骤"], 1):
                ttk.Label(correct_frame, text=f"{i}. {step}",
                          foreground=STYLES["success_color"]).pack(anchor='w', padx=10, pady=2)

            # 常见错误
            error_frame = ttk.LabelFrame(frame, text="❌ 常见错误", padding=5)
            error_frame.pack(fill=tk.X, padx=5)

            for i, error in enumerate(steps["常见错误"], 1):
                ttk.Label(error_frame, text=f"{i}. {error}",
                          foreground=STYLES["danger_color"]).pack(anchor='w', padx=10, pady=2)

        # 中间面板 (40%)
        center_panel = ttk.Frame(content_pane)
        content_pane.add(center_panel, weight=4)

        # 实时评估
        eval_group = ttk.LabelFrame(center_panel, text="📝 实时动作评估", padding=10)
        eval_group.pack(fill=tk.BOTH, expand=True)

        # 添加工具栏
        eval_toolbar = ttk.Frame(eval_group)
        eval_toolbar.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(eval_toolbar, text="清空", command=self.clear_evaluation,
                   width=8).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(eval_toolbar, text="导出", command=self.export_evaluation,
                   width=8).pack(side=tk.LEFT)

        # 创建文本区域
        self.txt_stream = scrolledtext.ScrolledText(eval_group, font=("Microsoft YaHei UI", 10),
                                                    state='disabled', wrap=tk.WORD)
        self.txt_stream.pack(fill=tk.BOTH, expand=True)

        # 右侧面板 (20%)
        right_panel = ttk.Frame(content_pane)
        content_pane.add(right_panel, weight=2)

        # 阶段报告
        summary_group = ttk.LabelFrame(right_panel, text="📊 阶段评估报告", padding=10)
        summary_group.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # 阶段报告工具栏
        summary_toolbar = ttk.Frame(summary_group)
        summary_toolbar.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(summary_toolbar, text="查看阶段", command=self.show_phase_summaries,
                   width=10).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(summary_toolbar, text="查看最终", command=self.show_final_report,
                   width=10).pack(side=tk.LEFT)

        # 创建报告文本区域
        self.txt_summary = scrolledtext.ScrolledText(summary_group, font=("Microsoft YaHei UI", 10),
                                                     state='disabled', wrap=tk.WORD, height=20)
        self.txt_summary.pack(fill=tk.BOTH, expand=True)

        # 状态栏
        status_frame = ttk.Frame(main_container, relief='sunken')
        status_frame.pack(fill=tk.X, pady=(20, 0))

        self.status_label = ttk.Label(status_frame, textvariable=self.status_text,
                                      foreground=STYLES["secondary_color"],
                                      font=("Microsoft YaHei", 9))
        self.status_label.pack(side=tk.LEFT, padx=10, pady=5)

        ttk.Label(status_frame, text="🚒 消防演习智能评估系统 | 安全第一，预防为主",
                  foreground=STYLES["text_dark"]).pack(side=tk.RIGHT, padx=10, pady=5)

        # 现在设置文本标签样式
        self.setup_text_tags()

        # 初始显示提示
        self.show_welcome_message()

        # 绑定窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_text_tags(self):
        """配置文本标签样式"""
        # 实时评估文本框
        if self.txt_stream:
            self.txt_stream.tag_config("time", foreground="#7f8c8d", font=("Consolas", 9))
            self.txt_stream.tag_config("header", foreground=STYLES["primary_color"],
                                       font=("Microsoft YaHei UI", 10, "bold"))
            self.txt_stream.tag_config("action", foreground=STYLES["info_color"],
                                       font=("Microsoft YaHei UI", 10))
            self.txt_stream.tag_config("correct", foreground=STYLES["success_color"],
                                       font=("Microsoft YaHei UI", 10))
            self.txt_stream.tag_config("error", foreground=STYLES["danger_color"],
                                       font=("Microsoft YaHei UI", 10))
            self.txt_stream.tag_config("suggestion", foreground=STYLES["warning_color"],
                                       font=("Microsoft YaHei UI", 10))
            self.txt_stream.tag_config("danger", foreground="#e67e22",
                                       font=("Microsoft YaHei UI", 10, "bold"))

        # 报告文本框
        if self.txt_summary:
            self.txt_summary.tag_config("header", background=STYLES["light_bg"],
                                        foreground=STYLES["primary_color"],
                                        font=("Microsoft YaHei UI", 11, "bold"))
            self.txt_summary.tag_config("score", foreground=STYLES["success_color"],
                                        font=("Microsoft YaHei UI", 10, "bold"))
            self.txt_summary.tag_config("problem", foreground=STYLES["danger_color"],
                                        font=("Microsoft YaHei UI", 10))
            self.txt_summary.tag_config("suggestion", foreground=STYLES["info_color"],
                                        font=("Microsoft YaHei UI", 10))
            self.txt_summary.tag_config("highlight", background="#fffacd",
                                        font=("Microsoft YaHei UI", 10))

    def show_welcome_message(self):
        """显示欢迎消息"""
        if self.txt_summary:
            self.txt_summary.config(state='normal')
            self.txt_summary.delete(1.0, tk.END)

            welcome_text = """🚒 消防演习智能评估系统 V4.0

欢迎使用消防演习智能评估系统！

使用方法：
1. 点击【上传视频】选择消防演习视频
2. 点击【开始分析】启动评估
3. 查看实时评估结果
4. 查看阶段评估报告
5. 分析完成后查看最终评估报告

注意：使用前需要设置API密钥
请将您的智谱AI API密钥填入代码顶部的 API_KEY 变量中
获取API密钥：https://open.bigmodel.cn/

请上传视频开始分析...
"""
            self.txt_summary.insert(tk.END, welcome_text)
            self.txt_summary.config(state='disabled')

    def upload_video(self):
        """上传视频文件"""
        if not OPENCV_AVAILABLE:
            messagebox.showerror("错误", "未安装OpenCV，无法处理视频文件。\n请运行: pip install opencv-python")
            return

        file_path = filedialog.askopenfilename(
            title="选择消防演习视频文件",
            filetypes=[
                ("视频文件", "*.mp4 *.avi *.mov *.mkv *.wmv *.flv"),
                ("所有文件", "*.*")
            ]
        )

        if not file_path:
            return

        self.video_path = file_path

        try:
            # 打开视频文件获取基本信息
            self.cap = cv.VideoCapture(file_path)
            if not self.cap.isOpened():
                raise Exception("无法打开视频文件")

            self.fps = self.cap.get(cv.CAP_PROP_FPS)
            self.total_frames = int(self.cap.get(cv.CAP_PROP_FRAME_COUNT))
            self.video_duration = self.total_frames / self.fps if self.fps > 0 else 0

            # 获取第一帧作为预览
            ret, frame = self.cap.read()
            if ret:
                self.update_preview(frame)
                self.cap.set(cv.CAP_PROP_POS_FRAMES, 0)  # 重置到开头

            file_name = os.path.basename(file_path)
            duration_str = time.strftime('%M:%S', time.gmtime(self.video_duration))
            self.video_info.set(f"📹 {file_name} ({duration_str}, {self.fps:.1f}fps)")

            self.btn_start.config(state=tk.NORMAL)
            self.update_status(f"✅ 已加载视频: {file_name}")

            # 在报告区域显示视频信息
            if self.txt_summary:
                self.txt_summary.config(state='normal')
                self.txt_summary.delete(1.0, tk.END)
                info_text = f"""📹 视频信息
文件: {file_name}
时长: {duration_str}
帧率: {self.fps:.1f} fps
总帧数: {self.total_frames}

点击【开始分析】按钮开始评估...
"""
                self.txt_summary.insert(tk.END, info_text, "header")
                self.txt_summary.config(state='disabled')

        except Exception as e:
            messagebox.showerror("错误", f"无法加载视频文件: {str(e)}")
            self.video_path = None
            self.cap = None

    def update_preview(self, frame):
        """更新视频预览"""
        if frame is None:
            return

        try:
            # 转换颜色空间 BGR -> RGB
            frame_rgb = cv.cvtColor(frame, cv.COLOR_BGR2RGB)

            # 转换为PIL图像
            pil_image = Image.fromarray(frame_rgb)

            # 计算缩放比例
            canvas_width = self.video_canvas.winfo_width() or 400
            canvas_height = self.video_canvas.winfo_height() or 300

            if canvas_width <= 1 or canvas_height <= 1:
                canvas_width, canvas_height = 400, 300

            # 缩放图片以适应画布
            img_width, img_height = pil_image.size
            scale = min(canvas_width / img_width, canvas_height / img_height)
            new_width = int(img_width * scale)
            new_height = int(img_height * scale)

            if scale < 1:
                pil_image = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # 转换为Tkinter PhotoImage
            self.preview_photo = ImageTk.PhotoImage(pil_image)

            # 清除画布并显示新图片
            self.video_canvas.delete("all")
            self.video_canvas.create_image(canvas_width // 2, canvas_height // 2,
                                           image=self.preview_photo, anchor=tk.CENTER)
            self.video_canvas.create_rectangle(2, 2, canvas_width - 2, canvas_height - 2,
                                               outline=STYLES["secondary_color"], width=2)

        except Exception as e:
            print(f"预览更新失败: {e}")

    def update_statistics(self, analysis_text):
        """更新动作统计"""
        if "✅" in analysis_text:
            self.correct_actions += 1
        if "❌" in analysis_text:
            self.incorrect_actions += 1
        if "✅" in analysis_text or "❌" in analysis_text:
            self.total_actions += 1

        self.lbl_stats.config(
            text=f"✅ 正确: {self.correct_actions}  ❌ 错误: {self.incorrect_actions}  📊 总计: {self.total_actions}"
        )

    def clear_evaluation(self):
        """清空评估内容"""
        if self.txt_stream:
            self.txt_stream.config(state='normal')
            self.txt_stream.delete(1.0, tk.END)
            self.txt_stream.config(state='disabled')

    def export_evaluation(self):
        """导出评估内容"""
        if not self.analysis_logs:
            messagebox.showinfo("提示", "没有评估内容可导出")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )

        if file_path:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("消防演习评估记录\n")
                f.write("=" * 50 + "\n\n")
                for log in self.analysis_logs:
                    f.write(log + "\n")
            messagebox.showinfo("成功", f"评估记录已保存到: {file_path}")

    def open_report_folder(self):
        """打开报告文件夹"""
        if self.log_filename and os.path.exists(self.log_filename):
            # 在文件管理器中打开文件所在目录
            folder_path = os.path.dirname(os.path.abspath(self.log_filename))
            try:
                if sys.platform == "win32":
                    os.startfile(folder_path)
                elif sys.platform == "darwin":
                    subprocess.run(["open", folder_path])
                else:
                    subprocess.run(["xdg-open", folder_path])
            except:
                messagebox.showinfo("报告位置", f"报告文件保存在:\n{self.log_filename}")
        else:
            messagebox.showinfo("提示", "尚未生成报告文件")

    def show_phase_summaries(self):
        """显示阶段总结"""
        if not self.phase_summaries:
            messagebox.showinfo("提示", "尚未生成阶段总结")
            return

        if self.txt_summary:
            self.txt_summary.config(state='normal')
            self.txt_summary.delete(1.0, tk.END)

            for i, summary in enumerate(self.phase_summaries, 1):
                self.txt_summary.insert(tk.END, f"=== 第 {i} 阶段总结 ===\n", "header")
                self.txt_summary.insert(tk.END, f"{summary}\n\n")

            self.txt_summary.see(tk.END)
            self.txt_summary.config(state='disabled')

    def show_final_report(self):
        """显示最终报告"""
        if not self.final_report_text:
            messagebox.showinfo("提示", "尚未生成最终报告")
            return

        if self.txt_summary:
            self.txt_summary.config(state='normal')
            self.txt_summary.delete(1.0, tk.END)

            # 计算统计数据
            correct_rate = (self.correct_actions / max(self.total_actions, 1)) * 100 if self.total_actions > 0 else 0

            # 添加统计头部
            stats_text = f"""📊 统计汇总
✅ 正确动作次数: {self.correct_actions}
❌ 错误动作次数: {self.incorrect_actions}
📊 总动作次数: {self.total_actions}
🎯 正确率: {correct_rate:.1f}%
"""
            self.txt_summary.insert(tk.END, stats_text, "header")
            self.txt_summary.insert(tk.END, "\n" + "=" * 50 + "\n\n")

            # 添加最终报告
            self.txt_summary.insert(tk.END, self.final_report_text)

            self.txt_summary.see(tk.END)
            self.txt_summary.config(state='disabled')

    def start_analysis(self):
        """开始分析视频"""
        if not self.video_path or not self.cap:
            messagebox.showwarning("警告", "请先上传视频文件")
            return

        # 检查API密钥
        if not API_KEY or API_KEY.strip() == "":
            messagebox.showerror("错误", "请先设置API密钥\n\n在代码顶部的 API_KEY 变量中填入您的智谱AI API密钥")
            return

        self.is_running = True
        self.frame_buffer = []
        self.subtitle_buffer = []
        self.analysis_logs = []
        self.phase_summaries = []
        self.deduplicator = SubtitleDeduplicator()

        # 重置统计
        self.correct_actions = 0
        self.incorrect_actions = 0
        self.total_actions = 0
        self.processed_frames = 0
        self.progress_var.set(0.0)
        self.buffer_var.set(0.0)
        self.final_report_text = ""

        self.lbl_stats.config(text="✅ 正确: 0  ❌ 错误: 0  📊 总计: 0")
        self.lbl_progress.config(text="0%")
        self.lbl_batch.config(text="0/4")

        # 清空文本框
        if self.txt_stream:
            self.txt_stream.config(state='normal')
            self.txt_stream.delete(1.0, tk.END)
            self.txt_stream.insert(tk.END, "🚀 开始分析消防演习视频...\n\n", "header")
            self.txt_stream.config(state='disabled')

        if self.txt_summary:
            self.txt_summary.config(state='normal')
            self.txt_summary.delete(1.0, tk.END)
            self.txt_summary.insert(tk.END, "⏳ 正在分析中，请稍候...\n", "header")
            self.txt_summary.config(state='disabled')

        # 创建日志文件
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        video_name = os.path.splitext(os.path.basename(self.video_path))[0]
        self.log_filename = f"fire_drill_{video_name}_{timestamp}.txt"

        # 写入日志头部
        with open(self.log_filename, "w", encoding="utf-8") as f:
            f.write("消防演习评估报告\n")
            f.write("=" * 50 + "\n")
            f.write(f"视频文件: {self.video_path}\n")
            f.write(f"视频时长: {self.video_duration:.1f}秒\n")
            f.write(f"帧率: {self.fps:.1f} fps\n")
            f.write(f"开始时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 50 + "\n\n")

        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.update_status("⏳ 开始分析视频...")

        # 重置视频到开头
        self.cap.set(cv.CAP_PROP_POS_FRAMES, 0)

        # 在新线程中开始分析
        threading.Thread(target=self.analysis_loop, daemon=True).start()

    def stop_analysis(self):
        """停止分析"""
        self.is_running = False
        self.update_status("⏳ 正在停止分析...")

    def analysis_loop(self):
        """分析循环"""
        batch_counter = 0
        frame_interval_frames = int(self.fps * FRAME_INTERVAL)

        if frame_interval_frames < 1:
            frame_interval_frames = 1

        frame_index = 0

        while self.is_running and self.cap.isOpened():
            # 计算进度
            if self.total_frames > 0:
                progress = (frame_index / self.total_frames) * 100
                self.root.after(0, lambda p=progress: self.progress_var.set(p))
                self.root.after(0, lambda p=progress: self.lbl_progress.config(text=f"{p:.1f}%"))

            # 读取指定帧
            self.cap.set(cv.CAP_PROP_POS_FRAMES, frame_index)
            ret, frame = self.cap.read()

            if not ret:
                break

            # 更新预览（每批更新一次）
            if len(self.frame_buffer) == 0:
                self.root.after(0, lambda f=frame.copy(): self.update_preview(f))

            # 转换BGR到RGB
            frame_rgb = cv.cvtColor(frame, cv.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)

            # 存储到缓冲区
            self.frame_buffer.append(pil_image)

            # 提取字幕区域（假设字幕在底部1/5区域）
            w, h = pil_image.size
            sub_h = int(h / 5)
            self.subtitle_buffer.append(pil_image.crop((0, h - sub_h, w, h)))

            # 更新缓冲区进度
            buffer_len = len(self.frame_buffer)
            self.root.after(0, lambda v=buffer_len: self.buffer_var.set(v))
            self.root.after(0, lambda v=buffer_len: self.lbl_batch.config(text=f"{v}/{BATCH_SIZE}"))
            self.root.after(0, lambda: self.update_status(f"⏳ 处理中: {buffer_len}/{BATCH_SIZE} 帧"))

            # 当缓冲区满时，进行处理
            if buffer_len >= BATCH_SIZE:
                # 快照数据
                frames_snapshot = list(self.frame_buffer)
                subs_snapshot = list(self.subtitle_buffer)
                current_batch_index = batch_counter

                # 启动分析线程
                threading.Thread(
                    target=self.process_batch_async,
                    args=(current_batch_index, frames_snapshot, subs_snapshot)
                ).start()

                # 清空缓冲区
                self.frame_buffer = []
                self.subtitle_buffer = []
                self.root.after(0, lambda: self.buffer_var.set(0))
                self.root.after(0, lambda: self.lbl_batch.config(text="0/4"))

                batch_counter += 1
                self.processed_frames += BATCH_SIZE

                # 阶段回顾
                if batch_counter % SUMMARY_TRIGGER_BATCHES == 0:
                    self.process_phase_summary()

            # 前进到下一帧
            frame_index += frame_interval_frames

            # 检查是否到达视频末尾
            if frame_index >= self.total_frames:
                break

            # 短暂暂停，避免UI冻结
            time.sleep(0.01)

        # 处理剩余帧
        if self.frame_buffer and self.is_running:
            frames_snapshot = list(self.frame_buffer)
            subs_snapshot = list(self.subtitle_buffer)
            threading.Thread(
                target=self.process_batch_async,
                args=(batch_counter, frames_snapshot, subs_snapshot)
            ).start()
            batch_counter += 1

        # 等待所有分析完成
        time.sleep(2)

        # 生成最终报告
        if self.is_running:
            self.process_final_report()

        # 清理
        self.is_running = False
        self.root.after(0, lambda: self.btn_start.config(state=tk.NORMAL))
        self.root.after(0, lambda: self.btn_stop.config(state=tk.DISABLED))

        if self.cap:
            self.cap.release()
            self.cap = None

    def process_batch_async(self, index, frames, subs):
        """异步处理单批次分析"""
        try:
            # 1. OCR (使用快照数据)
            stitched_sub = self.stitch_images_vertical(subs)
            clean_subs = "无"
            if stitched_sub:
                stitched_sub = self.adaptive_resize_for_ocr(stitched_sub)
                raw = self.call_llm(OCR_API_URL, OCR_MODEL_ID, [
                    {"role": "system", "content": PROMPT_OCR},
                    {"role": "user",
                     "content": [{"type": "image_url", "image_url": {"url": self.image_to_base64(stitched_sub)}}]}
                ], max_tokens=150)
                clean_subs = self.deduplicator.process(raw)

            # 2. 动作分析 (使用快照数据)
            stitched_plot = self.stitch_images_grid_2x2(frames)
            if stitched_plot:
                stitched_plot = self.adaptive_resize_for_vlm(stitched_plot)

                # 访问共享资源 analysis_logs
                history_context = "\n".join(self.analysis_logs[-2:]) if self.analysis_logs else "（无历史记录）"

                prompt = PROMPT_ACTION_ANALYSIS.format(
                    history=history_context,
                    subtitles=clean_subs if clean_subs else "（无指令）"
                )

                action_analysis = self.call_llm(VLM_API_URL, VLM_MODEL_ID, [
                    {"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": self.image_to_base64(stitched_plot)}}
                    ]}
                ], max_tokens=400)

                if action_analysis:
                    entry = f"【批次 {index} | 时间 {index * 10}s+】\n指令：{clean_subs}\n评估：{action_analysis}\n"
                    # 写入共享资源
                    self.analysis_logs.append(entry)
                    self.log_stream(index, clean_subs, action_analysis)
                    self.write_file(entry)

                    # 更新统计
                    self.root.after(0, lambda: self.update_statistics(action_analysis))
                    self.root.after(0, lambda: self.update_status(f"✅ 完成批次 {index} 分析"))

        except Exception as e:
            print(f"批次处理错误: {e}")
            self.root.after(0, lambda: self.update_status(f"❌ 批次{index}处理失败: {str(e)}", is_error=True))

    def process_phase_summary(self):
        """阶段回顾"""
        self.root.after(0, lambda: self.update_status("🤖 AI 生成阶段评估中..."))

        past_summaries = "\n".join(self.phase_summaries) if self.phase_summaries else "（暂无先前阶段）"
        recent_logs = "\n".join(self.analysis_logs[-SUMMARY_TRIGGER_BATCHES:])

        prompt = PROMPT_PHASE_SUMMARY.format(
            past_summaries=past_summaries,
            recent_logs=recent_logs
        )

        summary = self.call_llm(VLM_API_URL, VLM_MODEL_ID, [
            {"role": "user", "content": prompt}
        ], max_tokens=600)

        if summary:
            self.phase_summaries.append(summary)
            self.log_summary(f"第 {len(self.phase_summaries)} 阶段评估", summary)
            self.write_file(f"\n=== 阶段评估 ===\n{summary}\n")

    def process_final_report(self):
        """生成最终报告"""
        self.root.after(0, lambda: self.update_status("📄 生成最终评估报告..."))

        # 如果有未处理的批次，先处理
        if len(self.analysis_logs) % SUMMARY_TRIGGER_BATCHES != 0:
            self.process_phase_summary()

        # 计算整体统计数据
        correct_rate = (self.correct_actions / max(self.total_actions, 1)) * 100 if self.total_actions > 0 else 0

        stats_section = f"""【统计汇总】
✅ 正确动作次数: {self.correct_actions}
❌ 错误动作次数: {self.incorrect_actions}
📊 总动作次数: {self.total_actions}
🎯 正确率: {correct_rate:.1f}%
        """

        context = "\n".join([f"阶段{i + 1}: {s}" for i, s in enumerate(self.phase_summaries)])

        # 在最终报告中加入统计数据
        final_context = stats_section + "\n\n" + context

        # 调用LLM生成最终报告
        try:
            final_report = self.call_llm(VLM_API_URL, VLM_MODEL_ID, [
                {"role": "system", "content": PROMPT_FINAL_SUMMARY},
                {"role": "user", "content": f"评估数据：\n{final_context}"}
            ], max_tokens=2500)

            if final_report:
                self.final_report_text = final_report

                # 保存完整的报告文件
                complete_report = f"""消防演习评估报告
{"=" * 50}
视频文件: {self.video_path}
视频时长: {self.video_duration:.1f}秒
帧率: {self.fps:.1f} fps
分析时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{"=" * 50}

{stats_section}

{"=" * 50}
阶段评估报告
{"=" * 50}
{context}

{"=" * 50}
最终评估报告
{"=" * 50}
{final_report}
"""

                # 覆盖保存完整报告
                with open(self.log_filename, "w", encoding="utf-8") as f:
                    f.write(complete_report)

                # 显示最终报告
                self.root.after(0, self.show_final_report)

                # 显示评估结果对话框
                self.root.after(0, lambda: messagebox.showinfo(
                    "✅ 分析完成",
                    f"消防演习评估完成！\n\n"
                    f"✅ 正确动作: {self.correct_actions} 次\n"
                    f"❌ 错误动作: {self.incorrect_actions} 次\n"
                    f"🎯 正确率: {correct_rate:.1f}%\n"
                    f"📄 报告已保存到: {self.log_filename}\n\n"
                    f"请在右侧面板查看完整报告。"
                ))

                self.root.after(0, lambda: self.update_status("✅ 分析完成！"))
            else:
                self.root.after(0, lambda: self.update_status("❌ 生成报告失败", is_error=True))
                self.root.after(0, lambda: messagebox.showerror("错误", "生成最终报告失败，请检查网络连接和API设置。"))

        except Exception as e:
            self.root.after(0, lambda: self.update_status(f"❌ 报告生成错误: {str(e)}", is_error=True))
            self.root.after(0, lambda: messagebox.showerror("错误", f"生成报告时发生错误: {str(e)}"))

    # ================= 图像处理工具函数 =================

    def adaptive_resize_for_vlm(self, img):
        w, h = img.size
        if w > VLM_MAX_DIMENSION or h > VLM_MAX_DIMENSION:
            ratio = min(VLM_MAX_DIMENSION / w, VLM_MAX_DIMENSION / h)
            return img.resize((int(w * ratio), int(h * ratio)), Image.Resampling.LANCZOS)
        return img

    def adaptive_resize_for_ocr(self, img):
        w, h = img.size
        ratio = OCR_TARGET_WIDTH / w
        return img.resize((OCR_TARGET_WIDTH, int(h * ratio)), Image.Resampling.LANCZOS)

    def stitch_images_grid_2x2(self, images):
        if len(images) != 4:
            return None
        w, h = images[0].size
        cw, ch = w // 2, h // 2
        target = Image.new('RGB', (w, h))
        target.paste(images[0].resize((cw, ch)), (0, 0))
        target.paste(images[1].resize((cw, ch)), (cw, 0))
        target.paste(images[2].resize((cw, ch)), (0, ch))
        target.paste(images[3].resize((cw, ch)), (cw, ch))
        return target

    def stitch_images_vertical(self, images):
        if not images:
            return None
        w, h = images[0].size
        target = Image.new('RGB', (w, h * len(images)))
        for i, img in enumerate(images):
            target.paste(img, (0, i * h))
        return target

    def image_to_base64(self, img):
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=85)
        return f"data:image/jpeg;base64,{base64.b64encode(buffered.getvalue()).decode()}"

    def call_llm(self, url, model, messages, max_tokens=200):
        try:
            headers = {
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            }

            resp = requests.post(url, json={
                "model": model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": max_tokens
            }, headers=headers, timeout=90)

            if resp.status_code == 200:
                return resp.json()['choices'][0]['message']['content']
            else:
                print(f"API调用失败: {resp.status_code}, {resp.text}")
                if resp.status_code == 401:
                    messagebox.showerror("API错误", "API密钥无效，请检查您的API密钥设置")
                return None
        except requests.exceptions.Timeout:
            print("API调用超时")
            return None
        except Exception as e:
            print(f"API Error: {e}")
            return None

    def update_status(self, msg, is_error=False):
        self.status_text.set(msg)
        if is_error:
            self.status_label.config(foreground=STYLES["danger_color"])
        else:
            self.status_label.config(foreground=STYLES["secondary_color"])

    def log_stream(self, index, sub, analysis):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.root.after(0, lambda: self._insert_stream(timestamp, sub, analysis))

    def _insert_stream(self, ts, sub, analysis):
        if not self.txt_stream:
            return

        self.txt_stream.config(state='normal')
        self.txt_stream.insert(tk.END, f"[{ts}] 评估节点 #{int(ts.split(':')[1]) // 10 + 1}\n", "time")

        if sub and sub != "无":
            self.txt_stream.insert(tk.END, f"📢 指令: {sub}\n", "action")

        # 根据不同类型的内容使用不同的标签
        lines = analysis.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if "✅" in line:
                self.txt_stream.insert(tk.END, f"{line}\n", "correct")
            elif "❌" in line:
                self.txt_stream.insert(tk.END, f"{line}\n", "error")
            elif "💡" in line:
                self.txt_stream.insert(tk.END, f"{line}\n", "suggestion")
            elif "⚠️" in line:
                self.txt_stream.insert(tk.END, f"{line}\n", "danger")
            elif line.startswith("动作描述"):
                self.txt_stream.insert(tk.END, f"🎬 {line}\n", "action")
            elif "评估完成" in line or "分析" in line:
                self.txt_stream.insert(tk.END, f"{line}\n", "header")
            else:
                self.txt_stream.insert(tk.END, f"{line}\n")

        self.txt_stream.insert(tk.END, "-" * 50 + "\n", "time")
        self.txt_stream.see(tk.END)
        self.txt_stream.config(state='disabled')

    def log_summary(self, title, content):
        self.root.after(0, lambda: self._insert_summary(title, content))

    def _insert_summary(self, title, content):
        if not self.txt_summary:
            return

        self.txt_summary.config(state='normal')
        self.txt_summary.insert(tk.END, f"\n🔔 {title}\n", "header")

        # 根据内容类型使用不同标签
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if "掌握程度" in line or "正确率" in line or "评分" in line:
                self.txt_summary.insert(tk.END, f"📊 {line}\n", "score")
            elif "问题" in line or "错误" in line or "常见错误" in line:
                self.txt_summary.insert(tk.END, f"❌ {line}\n", "problem")
            elif "建议" in line or "改进" in line or "训练重点" in line:
                self.txt_summary.insert(tk.END, f"💡 {line}\n", "suggestion")
            elif "亮点" in line or "优点" in line:
                self.txt_summary.insert(tk.END, f"✅ {line}\n", "highlight")
            else:
                self.txt_summary.insert(tk.END, f"{line}\n")

        self.txt_summary.see(tk.END)
        self.txt_summary.config(state='disabled')

    def write_file(self, text):
        if self.log_filename:
            with open(self.log_filename, "a", encoding="utf-8") as f:
                f.write(text + "\n")

    def on_closing(self):
        """窗口关闭时的清理"""
        self.is_running = False
        if self.cap:
            self.cap.release()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = FireDrillAnalyzerApp(root)
    root.mainloop()