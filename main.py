import flet as ft
import asyncio
import json
import os
import datetime
import random
import urllib.request

# --- Configuration & Constants ---
DEFAULT_CONFIG = {
    "user_nickname": "我",
    "agent_nickname": "Yy",
    "bg_color": "#f0f0f0",
    "bubble_user_color": "#95ec69",
    "bubble_agent_color": "#ffffff",
    "font_size": 14
}

API_KEY = "sk-dc4c6988c52c46d88d8f1d742e099721"
MODEL_NAME = "deepseek-chat"
BASE_URL = "https://api.deepseek.com/chat/completions"
CONTEXT_FILENAME = "deepseek_context.txt"

LONG_CONTEXT = ""
chat_history = []

def load_context():
    global LONG_CONTEXT
    try:
        # On Android, current working directory might not be where assets are.
        # But Flet usually unpacks assets to a temp dir or handles paths relative to main.py
        if os.path.exists(CONTEXT_FILENAME):
            with open(CONTEXT_FILENAME, "r", encoding="utf-8") as f:
                LONG_CONTEXT = f.read()
    except Exception as e:
        print(f"Error loading context: {e}")
        pass

async def call_deepseek_api(messages):
    """
    Call DeepSeek API using standard library (urllib) to avoid dependency issues on Android.
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    data = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": 1.3,
        "max_tokens": 500
    }
    
    def _make_request():
        req = urllib.request.Request(BASE_URL, data=json.dumps(data).encode('utf-8'), headers=headers)
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
            
    # Run network request in a separate thread to keep UI responsive
    loop = asyncio.get_running_loop()
    response_json = await loop.run_in_executor(None, _make_request)
    return response_json['choices'][0]['message']['content']

async def main(page: ft.Page):
    # --- Setup ---
    # Load config from ClientStorage (safer for Mobile than file system)
    try:
        await page.client_storage.get_async("app_config") # Check if async works, or use sync
        # Flet client_storage is synchronous usually, but let's use standard get
        stored_config = page.client_storage.get("app_config")
    except Exception:
        stored_config = None
        
    config = DEFAULT_CONFIG.copy()
    if stored_config:
        try:
            # ensure it's a dict
            if isinstance(stored_config, str):
                stored_config = json.loads(stored_config)
            config.update(stored_config)
        except:
            pass

    load_context()
    
    page.title = f"数字分身 - {config['agent_nickname']}"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 0
    page.bgcolor = config['bg_color']
    
    # --- State ---
    pending_user_messages = []
    response_task = None

    # --- UI Components ---
    
    # Chat List (ListView)
    chat_list = ft.ListView(
        expand=True,
        spacing=10,
        padding=20,
        auto_scroll=True,
    )

    def create_bubble(text, is_user):
        """Create a chat bubble control"""
        bubble_color = config['bubble_user_color'] if is_user else config['bubble_agent_color']
        alignment = ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START
        
        # Avatar placeholder (Initials)
        name = config['user_nickname'] if is_user else config['agent_nickname']
        initial = name[0] if name else "?"
        
        avatar = ft.CircleAvatar(
            content=ft.Text(initial),
            color=ft.colors.WHITE,
            bgcolor=ft.colors.BLUE if is_user else ft.colors.ORANGE,
            radius=16,
        )
        
        content = ft.Container(
            content=ft.Text(text, color="black", size=config['font_size']),
            bgcolor=bubble_color,
            border_radius=10,
            padding=10,
            width=None, # Auto width
            maw=300,    # Max width
        )
        
        row_controls = []
        if is_user:
            row_controls = [content, ft.Container(width=5), avatar]
        else:
            row_controls = [avatar, ft.Container(width=5), content]
            
        return ft.Row(
            controls=row_controls,
            alignment=alignment,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

    def add_message(text, is_user):
        chat_list.controls.append(create_bubble(text, is_user))
        page.update()

    def add_system_message(text):
        chat_list.controls.append(
            ft.Row(
                controls=[ft.Text(text, size=10, color="grey")],
                alignment=ft.MainAxisAlignment.CENTER
            )
        )
        page.update()

    # --- Logic ---
    
    async def process_ai_response(full_message):
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        system_prompt = f"""You are a digital clone of '{config['agent_nickname']}'.
Your task is to roleplay as {config['agent_nickname']} and chat with '{config['user_nickname']}' (the user).
Current Time: {current_time}

Below is a large collection of your past chat history. 
Mimic {config['agent_nickname']}'s tone, vocabulary, sentence length, and emoji usage EXACTLY based on this history.
Do not act like an AI. Act like a real person.

INSTRUCTIONS:
1. You can send multiple short messages instead of one long block. To do this, separate your messages with '|||'.
   Example: "Haha true." ||| "Wait, are you serious?"
2. If the user asks multiple questions, answer them naturally.
3. Be casual.

--- BEGIN CHAT HISTORY ---
{LONG_CONTEXT}
--- END CHAT HISTORY ---

Now, reply to the latest message from {config['user_nickname']}."""

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(chat_history)
        messages.append({"role": "user", "content": full_message})

        try:
            # Thinking delay
            await asyncio.sleep(random.uniform(1.0, 2.5))
            
            # Call API using our robust function
            reply = await call_deepseek_api(messages)
            
            chat_history.append({"role": "user", "content": full_message})
            chat_history.append({"role": "assistant", "content": reply})
            if len(chat_history) > 20: 
                # keep it a list, not slice assignment if global
                # actually chat_history is global list, so slice assignment is good
                chat_history[:] = chat_history[-20:]

            # Handle multi-bubble response
            parts = reply.split("|||")
            for part in parts:
                p = part.strip()
                if p:
                    add_message(p, is_user=False)
                    # Typing delay based on length
                    delay = min(len(p) * 0.05 + 0.5, 2.0)
                    await asyncio.sleep(delay)
                    
        except Exception as e:
            add_system_message(f"Error: {str(e)}")
            print(f"API Error: {e}")

    async def trigger_ai_response():
        nonlocal pending_user_messages
        if not pending_user_messages: return
        
        full_message = " ".join(pending_user_messages)
        pending_user_messages = []
        
        await process_ai_response(full_message)

    async def send_click(e):
        if not txt_input.value: return
        
        msg = txt_input.value
        txt_input.value = ""
        page.update()
        
        add_message(msg, is_user=True)
        pending_user_messages.append(msg)
        
        # Debounce logic
        nonlocal response_task
        if response_task:
            response_task.cancel()
        
        try:
            # Wait 1.5s for more input
            response_task = asyncio.create_task(asyncio.sleep(1.5))
            await response_task
            await trigger_ai_response()
        except asyncio.CancelledError:
            pass # Timer reset

    # --- Settings Dialog ---
    
    def open_settings(e):
        
        def save_settings(e):
            config['user_nickname'] = user_nick.value
            config['agent_nickname'] = agent_nick.value
            
            # Save to client storage
            page.client_storage.set("app_config", config)
            
            page.title = f"数字分身 - {config['agent_nickname']}"
            page.dialog.open = False
            page.update()
            
        user_nick = ft.TextField(label="你的昵称", value=config['user_nickname'])
        agent_nick = ft.TextField(label="对象昵称", value=config['agent_nickname'])
        
        dlg = ft.AlertDialog(
            title=ft.Text("设置"),
            content=ft.Column([
                user_nick,
                agent_nick,
                ft.Text("注意：手机端暂不支持更换背景图片，请使用纯色。", size=12, color="grey")
            ], height=200, tight=True),
            actions=[
                ft.TextButton("保存", on_click=save_settings),
                ft.TextButton("取消", on_click=lambda e: setattr(page.dialog, 'open', False) or page.update()),
            ],
        )
        page.dialog = dlg
        dlg.open = True
        page.update()

    # --- Layout Assembly ---
    
    txt_input = ft.TextField(
        hint_text="发送消息...",
        expand=True,
        border_radius=20,
        filled=True,
        bgcolor="white",
        on_submit=send_click
    )
    
    send_btn = ft.IconButton(
        icon=ft.icons.SEND_ROUNDED,
        icon_color="blue",
        on_click=send_click
    )
    
    input_bar = ft.Container(
        content=ft.Row([txt_input, send_btn]),
        padding=10,
        bgcolor="#ffffff",
    )

    # App Bar
    page.appbar = ft.AppBar(
        leading=ft.Icon(ft.icons.CHAT_BUBBLE),
        leading_width=40,
        title=ft.Text(f"与 {config['agent_nickname']} 聊天"),
        center_title=False,
        bgcolor=ft.colors.SURFACE_VARIANT,
        actions=[
            ft.IconButton(ft.icons.SETTINGS, on_click=open_settings),
        ],
    )

    page.add(
        ft.Column(
            [
                chat_list,
                input_bar,
            ],
            expand=True,
        )
    )
    
    add_system_message(f"系统已加载。记忆库大小: {len(LONG_CONTEXT)} 字符。")

ft.app(target=main)
