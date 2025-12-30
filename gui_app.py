import tkinter as tk
from tkinter import scrolledtext, ttk, filedialog, simpledialog, messagebox
import threading
import os
import sys
import json
import datetime
import time
import random
from PIL import Image, ImageTk, ImageDraw
from openai import OpenAI
import shutil

# Try to import data processor for history updates
try:
    import data_processor
except ImportError:
    data_processor = None

# --- Configuration & Constants ---
CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "user_nickname": "我",
    "agent_nickname": "Yy",
    "user_avatar": "",  # Path to image
    "agent_avatar": "", # Path to image
    "bg_image": "",     # Path to image
    "bg_color": "#f0f0f0",
    "bubble_user_color": "#95ec69",
    "bubble_agent_color": "#ffffff",
    "font_size": 10
}

API_KEY = "sk-dc4c6988c52c46d88d8f1d742e099721"
MODEL_NAME = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"
CONTEXT_FILENAME = "deepseek_context.txt"

def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def load_context():
    try:
        if os.path.exists(CONTEXT_FILENAME):
            with open(CONTEXT_FILENAME, "r", encoding="utf-8") as f:
                return f.read()
        bundled_path = get_resource_path(CONTEXT_FILENAME)
        if os.path.exists(bundled_path):
            with open(bundled_path, "r", encoding="utf-8") as f:
                return f.read()
    except Exception:
        pass
    return ""

LONG_CONTEXT = load_context()
client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
chat_history = []

class ChatApp:
    def __init__(self, root):
        self.root = root
        self.config = self.load_config()
        self.root.title(f"数字分身 - {self.config['agent_nickname']}")
        self.root.geometry("500x700")
        
        # Debounce and multi-message handling
        self.response_timer = None
        self.pending_user_messages = []
        
        # Images cache to prevent GC
        self.images = {}
        
        self.setup_menu()
        self.setup_ui()
        
        # Load avatars
        self.load_avatars()
        
        # Initial greeting
        self.append_system_message(f"系统已加载。记忆库大小: {len(LONG_CONTEXT)} 字符。")

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return {**DEFAULT_CONFIG, **json.load(f)}
            except:
                pass
        return DEFAULT_CONFIG.copy()

    def save_config(self):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=4, ensure_ascii=False)

    def setup_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File Menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="导入聊天记录 (docx/txt)", command=self.import_history)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.root.quit)
        
        # Settings Menu
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="设置", menu=settings_menu)
        settings_menu.add_command(label="个人资料设置", command=self.open_settings)
        settings_menu.add_command(label="更改背景", command=self.change_background)

    def setup_ui(self):
        # Chat Area (Canvas + Scrollbar)
        self.chat_frame = tk.Frame(self.root)
        self.chat_frame.pack(fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(self.chat_frame, bg=self.config['bg_color'])
        self.scrollbar = ttk.Scrollbar(self.chat_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Container for messages (to use scrollregion)
        self.messages_frame = tk.Frame(self.canvas, bg=self.config['bg_color'])
        self.canvas_window = self.canvas.create_window((0, 0), window=self.messages_frame, anchor="nw")
        
        self.messages_frame.bind("<Configure>", self.on_frame_configure)
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        
        # Load Background Image if exists
        self.update_background_image()

        # Input Area
        input_frame = ttk.Frame(self.root)
        input_frame.pack(padx=10, pady=10, fill=tk.X)
        
        self.user_input = tk.Entry(input_frame, font=("Microsoft YaHei", 12))
        self.user_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.user_input.bind("<Return>", self.send_message)
        
        self.send_btn = ttk.Button(input_frame, text="发送", command=self.send_message)
        self.send_btn.pack(side=tk.RIGHT)

    def on_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def update_background_image(self):
        bg_path = self.config.get('bg_image')
        if bg_path and os.path.exists(bg_path):
            try:
                img = Image.open(bg_path)
                pass
            except Exception as e:
                print(f"Error loading bg: {e}")
        
        # For this version, we stick to bg_color for the frame to ensure readability
        self.canvas.config(bg=self.config['bg_color'])
        self.messages_frame.config(bg=self.config['bg_color'])

    def load_avatars(self):
        def process_avatar(path):
            if path and os.path.exists(path):
                try:
                    img = Image.open(path).resize((40, 40), Image.Resampling.LANCZOS)
                    return ImageTk.PhotoImage(img)
                except:
                    pass
            # Default avatar (colored box)
            img = Image.new('RGB', (40, 40), color='#cccccc')
            return ImageTk.PhotoImage(img)

        self.user_avatar_img = process_avatar(self.config['user_avatar'])
        self.agent_avatar_img = process_avatar(self.config['agent_avatar'])

    def append_system_message(self, text):
        lbl = tk.Label(self.messages_frame, text=text, fg="gray", bg=self.config['bg_color'], font=("Arial", 8))
        lbl.pack(pady=5, anchor="center")
        self.scroll_to_bottom()

    def append_message(self, text, is_user):
        container = tk.Frame(self.messages_frame, bg=self.config['bg_color'])
        container.pack(fill=tk.X, pady=5, padx=10)
        
        avatar_img = self.user_avatar_img if is_user else self.agent_avatar_img
        bubble_color = self.config['bubble_user_color'] if is_user else self.config['bubble_agent_color']
        
        if is_user:
            # Avatar Right
            av_lbl = tk.Label(container, image=avatar_img, bg=self.config['bg_color'])
            av_lbl.pack(side=tk.RIGHT, anchor="ne")
            
            # Bubble Right
            bubble = tk.Label(container, text=text, bg=bubble_color, fg="black", 
                              font=("Microsoft YaHei", self.config['font_size']),
                              wraplength=350, justify=tk.LEFT, padx=10, pady=5, relief="solid", borderwidth=0)
            bubble.pack(side=tk.RIGHT, padx=5, anchor="ne")
        else:
            # Avatar Left
            av_lbl = tk.Label(container, image=avatar_img, bg=self.config['bg_color'])
            av_lbl.pack(side=tk.LEFT, anchor="nw")
            
            # Bubble Left
            bubble = tk.Label(container, text=text, bg=bubble_color, fg="black",
                              font=("Microsoft YaHei", self.config['font_size']),
                              wraplength=350, justify=tk.LEFT, padx=10, pady=5, relief="solid", borderwidth=0)
            bubble.pack(side=tk.LEFT, padx=5, anchor="nw")
            
        self.scroll_to_bottom()

    def scroll_to_bottom(self):
        self.root.update_idletasks()
        self.canvas.yview_moveto(1.0)

    def send_message(self, event=None):
        message = self.user_input.get().strip()
        if not message: return
        
        self.user_input.delete(0, tk.END)
        self.append_message(message, is_user=True)
        
        # Debounce logic: don't trigger AI immediately
        self.pending_user_messages.append(message)
        
        if self.response_timer:
            self.root.after_cancel(self.response_timer)
            
        # Wait 1.5 seconds for more input before triggering AI
        self.response_timer = self.root.after(1500, self.trigger_ai_response)

    def trigger_ai_response(self):
        if not self.pending_user_messages: return
        
        # Combine messages
        full_message = " ".join(self.pending_user_messages)
        self.pending_user_messages = [] # Clear buffer
        
        # Start processing in thread
        threading.Thread(target=self.get_ai_response, args=(full_message,)).start()

    def get_ai_response(self, user_message):
        global chat_history, LONG_CONTEXT
        
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        system_prompt = f"""You are a digital clone of '{self.config['agent_nickname']}'.
Your task is to roleplay as {self.config['agent_nickname']} and chat with '{self.config['user_nickname']}' (the user).
Current Time: {current_time}

Below is a large collection of your past chat history. 
Mimic {self.config['agent_nickname']}'s tone, vocabulary, sentence length, and emoji usage EXACTLY based on this history.
Do not act like an AI. Act like a real person.

INSTRUCTIONS:
1. You can send multiple short messages instead of one long block. To do this, separate your messages with '|||'.
   Example: "Haha true." ||| "Wait, are you serious?"
2. If the user asks multiple questions, answer them naturally.
3. Be casual.

--- BEGIN CHAT HISTORY ---
{LONG_CONTEXT}
--- END CHAT HISTORY ---

Now, reply to the latest message from {self.config['user_nickname']}.
"""
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(chat_history)
        messages.append({"role": "user", "content": user_message})

        try:
            # Simulate "Reading/Thinking" delay based on input length
            time.sleep(random.uniform(1.0, 2.5))
            
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                temperature=1.3,
                max_tokens=500
            )
            reply = response.choices[0].message.content
            
            chat_history.append({"role": "user", "content": user_message})
            chat_history.append({"role": "assistant", "content": reply})
            if len(chat_history) > 20: chat_history = chat_history[-20:]

            self.root.after(0, lambda: self.finish_response(reply))
            
        except Exception as e:
            self.root.after(0, lambda: self.finish_response(f"Error: {str(e)}", error=True))

    def finish_response(self, reply, error=False):
        if error:
            self.append_system_message(reply)
            return

        # Split multiple bubbles
        parts = reply.split("|||")
        
        def show_next_part(index):
            if index < len(parts):
                part = parts[index].strip()
                if part:
                    self.append_message(part, is_user=False)
                    # Delay before next bubble (simulate typing)
                    typing_delay = min(len(part) * 0.05 + 0.5, 2.0)
                    self.root.after(int(typing_delay * 1000), lambda: show_next_part(index + 1))
                else:
                    show_next_part(index + 1)
        
        show_next_part(0)

    # --- Settings & Features ---
    def open_settings(self):
        top = tk.Toplevel(self.root)
        top.title("个人资料设置")
        top.geometry("400x400")
        
        tk.Label(top, text="你的昵称:").pack(pady=5)
        user_nick = tk.Entry(top)
        user_nick.insert(0, self.config['user_nickname'])
        user_nick.pack(fill=tk.X, padx=20)
        
        tk.Label(top, text="对象昵称:").pack(pady=5)
        agent_nick = tk.Entry(top)
        agent_nick.insert(0, self.config['agent_nickname'])
        agent_nick.pack(fill=tk.X, padx=20)
        
        def pick_user_avatar():
            path = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg")])
            if path: self.config['user_avatar'] = path
            
        def pick_agent_avatar():
            path = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg")])
            if path: self.config['agent_avatar'] = path
            
        tk.Button(top, text="选择你的头像", command=pick_user_avatar).pack(pady=10)
        tk.Button(top, text="选择对象头像", command=pick_agent_avatar).pack(pady=5)
        
        def save():
            self.config['user_nickname'] = user_nick.get()
            self.config['agent_nickname'] = agent_nick.get()
            self.save_config()
            self.load_avatars() # Reload avatars
            self.root.title(f"数字分身 - {self.config['agent_nickname']}")
            top.destroy()
            messagebox.showinfo("成功", "设置已保存！")
            
        tk.Button(top, text="保存", command=save, bg="blue", fg="white").pack(pady=20)

    def change_background(self):
        # Simple color picker or file picker
        choice = messagebox.askyesno("更改背景", "你想使用图片作为背景吗？(是=选择图片，否=选择颜色)")
        if choice:
            path = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg")])
            if path:
                self.config['bg_image'] = path
                self.save_config()
                messagebox.showinfo("提示", "背景图片已保存，请重启应用以获得最佳效果。")
        else:
            # Color picker
            from tkinter.colorchooser import askcolor
            color = askcolor(title="选择背景颜色")[1]
            if color:
                self.config['bg_color'] = color
                self.save_config()
                self.canvas.config(bg=color)
                self.messages_frame.config(bg=color)
                # Need to update existing bubbles? Too complex for now.
                messagebox.showinfo("提示", "背景颜色已更新。")

    def import_history(self):
        path = filedialog.askopenfilename(filetypes=[("Documents", "*.docx;*.txt")])
        if not path: return
        
        if not data_processor:
            messagebox.showerror("错误", "未找到数据处理模块 (data_processor)。")
            return

        threading.Thread(target=self.run_import, args=(path,)).start()

    def run_import(self, path):
        self.root.after(0, lambda: self.append_system_message("正在处理历史记录... 这可能需要几分钟。"))
        try:
            global LONG_CONTEXT
            if path.endswith(".docx"):
                # Use data_processor logic
                raw_msgs = data_processor.extract_conversations(path)
                data_processor.process_history_smartly(raw_msgs, CONTEXT_FILENAME)
            else:
                # Assuming txt is already processed or raw
                shutil.copy(path, CONTEXT_FILENAME)
            
            # Reload context
            with open(CONTEXT_FILENAME, 'r', encoding='utf-8') as f:
                LONG_CONTEXT = f.read()
            
            self.root.after(0, lambda: self.append_system_message(f"记录已更新！新记忆库大小: {len(LONG_CONTEXT)} 字符。"))
        except Exception as e:
            self.root.after(0, lambda: self.append_system_message(f"导入失败: {str(e)}"))

if __name__ == "__main__":
    root = tk.Tk()
    app = ChatApp(root)
    root.mainloop()
